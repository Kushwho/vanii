import os
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room
from dotenv import load_dotenv
from deepgram import  LiveTranscriptionEvents,LiveOptions
from llm import save_in_mongo_clear_redis, store_in_redis,streaming
from text_to_speech import  text_to_speech_cartesia,text_to_speech_stream,text_to_speech_cartesia_batch
import time
from threading import Timer
from utils import log_event 
from utils import store_audio_chunk,log_function_call
from config import Config
from models import db
from log_config import setup_logging
import logging
from concurrent.futures import ThreadPoolExecutor
from analytics.speech_analytics import upload_file  
import sentry_sdk 
import json
from DeepgramClient import DeepgramService
import threading
import asyncio

# Load environment variables from .env file
load_dotenv()

sentry_sdk.init(
    dsn="https://2cb44a9801b505d2d34b29d4e36df73d@o4507851145084928.ingest.de.sentry.io/4507851149279312",
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for tracing.
    traces_sample_rate=1.0,
    # Set profiles_sample_rate to 1.0 to profile 100%
    # of sampled transactions.
    # We recommend adjusting this value in production.
    profiles_sample_rate=1.0,
)

deepgram_service = DeepgramService()
deepgram = deepgram_service.get_client()


# Initialize Flask and SocketIO
cors_allowed_origins = os.getenv("CORS")
app_socketio = Flask("app_socketio")
app_socketio.config.from_object(Config)
db.init_app(app_socketio)
socketio = SocketIO(app_socketio, cors_allowed_origins=cors_allowed_origins)

# Initialize a dictionary to store Deepgram connections
dg_connections = {}

# Initialize a dictionary to store transcript buffers
transcript_buffers = {}

# Initialize a dictionary to store buffer timers
buffer_timers = {}

# Define a Thread Pool Executor
executor = ThreadPoolExecutor(max_workers=3)

# Global dictionary to store audio buffers
audio_buffers = {}

# Maximum time to wait before storing a partial chunk (in seconds)
MAX_WAIT_TIME = 5

def configure_app(use_cloudwatch):
    with app_socketio.app_context():
        db.create_all()
    
    # Set up logging
    logger = setup_logging(use_cloudwatch)
    
    # Configure Flask to use our logger
    app_socketio.logger.handlers = logger.handlers
    app_socketio.logger.setLevel(logger.level)



# # Asynchronous wrapper for log_event
# def async_log_event(event_type, event_data):
#     executor.submit(log_event_sync, event_type, event_data)

# Thread-safe buffer for transcripts
def buffer_transcripts(transcript, sessionId):
    if sessionId not in transcript_buffers:
        transcript_buffers[sessionId] = ""
    
    transcript_buffers[sessionId] += transcript
    
    # Restart timer for processing buffered transcripts
    if sessionId in buffer_timers and buffer_timers[sessionId] is not None:
        buffer_timers[sessionId].cancel()
    
    buffer_timers[sessionId] = Timer(1, process_transcripts, [sessionId])
    buffer_timers[sessionId].start()

# Process buffered transcripts and convert them to speech
def process_transcripts(sessionId):
    if sessionId in transcript_buffers and len(transcript_buffers[sessionId]) > 0:
        start = time.time()
        transcript = transcript_buffers[sessionId]
        app_socketio.logger.info(f"Processing buffered transcripts for session {sessionId}: {transcript}")
        
        # resp = batch(sessionId, transcript)
        resp_stream = ''
        for chunk in streaming(session_id=sessionId,transcript=transcript) :
            resp_stream += chunk.content
        app_socketio.logger.info(f"Streamed response: {resp_stream}")
        voice = 'Deepgram'
        if dg_connections[sessionId] : 
            voice = dg_connections[sessionId].get("voice", "Deepgram")
            logging.info(f"Voice for user with {sessionId} is {voice}")
        if voice == "Deepgram":
            response = text_to_speech_stream(resp_stream)
            socketio.emit('transcription_update', {'audioBinary': response, 'user': transcript, 'transcription': resp_stream, 'sessionId': sessionId}, to=sessionId)
        else:
            try:
                response = text_to_speech_cartesia_batch(resp_stream)
                socketio.emit('transcription_update', {'audioBinary': response, 'user': transcript, 'transcription': resp_stream, 'sessionId': sessionId}, to=sessionId)
            except Exception as e:
                socketio.emit('transcription_update', {'transcription': resp_stream, 'user': transcript, 'sessionId': sessionId}, to=sessionId)
        
        endtime = time.time() - start
        app_socketio.logger.info(f"It took {endtime} seconds for total response")
        transcript_buffers[sessionId] = ""
        buffer_timers[sessionId] = None


def send_heartbeat(sessionId):
    try:
        while sessionId in dg_connections:
            dg_connections[sessionId]['connection'].send(json.dumps({"type" : "KeepAlive"}))
            logging.info(f"Heartbeat sent for session {sessionId}")
            time.sleep(2)  # Wait for 2 seconds before sending the next heartbeat
    except Exception as e:
        logging.error(f"Error in sending heartbeat for session {sessionId}: {e}")

def start_heartbeat_loop(sessionId):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_heartbeat(sessionId))

# Initialize Deepgram connection for a session
def initialize_deepgram_connection(sessionId, email, voice):
    app_socketio.logger.info(f"Initializing Deepgram connection for session {sessionId}")
    dg_connection = deepgram.listen.websocket.v("1")

    def on_open(self, open, **kwargs):
        log_event('UserMicOn', {'page': '/record'}, 'user_id': sessionId})
        logging.info(f"Deepgram connection opened for session {sessionId}: {open}")
        socketio.emit('deepgram_connection_opened', {'message': 'Deepgram connection opened'}, room=sessionId)

    def on_message(self, result, **kwargs):
        # nonlocal utterance
        transcript = result.channel.alternatives[0].transcript
        # logging.info(result.speech_final)
        # logging.info(f"\n\n{result}\n\n")
        if len(transcript) > 0:
            logging.info(f"Received transcript for session {sessionId}: {transcript}")
            buffer_transcripts(transcript, sessionId)
        # utterance = False

    def on_metadata(self, metadata, **kwargs):
        logging.info(f"Received metadata for session {sessionId}: {metadata}")

    def on_close(self, close, **kwargs):
        log_event('UserMicOff', {'page': '/record'}, 'user_id': sessionId)
        logging.info(f"Deepgram connection closed for session {sessionId}: {close}")

    def on_error(self, error, **kwargs):
        logging.error(f"Deepgram connection error for session {sessionId}: {error}")

    def on_speech_started(self, speech_started, **kwargs):
        socketio.emit("speech_started",{'is_started' : True},to=sessionId)
        logging.info(f"\n\nSpeech has been started{speech_started}\n\n")


    
    # def on_utterance_end(self, utterance_end, **kwargs):
    #     nonlocal utterance
    #     utterance = True
    #     logging.info(f"\n\n{utterance_end}\n\n")




    # Register Deepgram event handlers
    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
    # dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
    dg_connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)

    # Options for the Deepgram connection
    options = LiveOptions(model="nova-2", language="en-IN", filler_words=True, smart_format=True, no_delay=True, keywords=["vaanii:5"], endpointing=1000, numerals=True)

    if not dg_connection.start(options):
        logging.error(f"Failed to start Deepgram connection for session {sessionId}")
        return None

    # Store the Deepgram connection
    dg_connections[sessionId] = {'connection': dg_connection, 'voice': voice}

    heartbeat_thread = threading.Thread(target=start_heartbeat_loop, args=(sessionId,))
    heartbeat_thread.start()
    return dg_connection

@log_function_call
def collate_and_store_audio(session_id, audio_data):
    current_time = time.time()
    
    if session_id not in audio_buffers:
        audio_buffers[session_id] = {
            "data": [],
            "last_update": current_time,
            "last_size": 0
        }
    
    buffer_info = audio_buffers[session_id]
    if audio_data:
        new_size = buffer_info["last_size"] + len(audio_data)
        if new_size > buffer_info["last_size"]:
            buffer_info["data"].append(audio_data)
            buffer_info["last_update"] = current_time
            buffer_info["last_size"] = new_size
    
    buffer_duration = len(buffer_info["data"])
    time_since_last_update = current_time - buffer_info["last_update"]
    
    if (buffer_duration > 0 and time_since_last_update >= MAX_WAIT_TIME):
        audio_chunk = b''.join(buffer_info["data"])
        chunk_duration = buffer_duration
        
        if buffer_info["last_size"] > 0:
            store_audio_chunk(session_id, audio_chunk, chunk_duration)
            logging.info(f"Stored audio chunk for session {session_id}, duration: {chunk_duration}s, size: {buffer_info['last_size']} bytes")
        else:
            logging.info(f"Discarded empty audio chunk for session {session_id}")
        
        # Reset the buffer
        audio_buffers[session_id] = {
            "data": [],
            "last_update": current_time,
            "last_size": 0
        }

# Handle incoming audio streams
@socketio.on('audio_stream')
def handle_audio_stream(data):
    sessionId = data.get("sessionId")
    if sessionId in dg_connections:
        dg_connections[sessionId]['connection'].send(data.get("data"))
    else:
        logging.warning(f"No active Deepgram connection for session ID: {sessionId}")
    
    executor.submit(collate_and_store_audio, sessionId, data.get("data"))


# Function to close Deepgram connection
def close_deepgram_connection(sessionId):
    if sessionId in dg_connections:
        try:
            dg_connections[sessionId]['connection'].send(json.dumps({"type" : "CloseStream"}))
            del dg_connections[sessionId]
            app_socketio.logger.info(f"Closed Deepgram connection for session {sessionId}")
        except Exception as e:
            app_socketio.logger.error(f"Error closing Deepgram connection for session {sessionId}: {str(e)}")
    
    # Clean up related resources
    if sessionId in transcript_buffers:
        del transcript_buffers[sessionId]
    if sessionId in buffer_timers:
        if buffer_timers[sessionId]:
            buffer_timers[sessionId].cancel()
        del buffer_timers[sessionId]

# Handle client connections
@socketio.on('connect')
def server_connect():
    logging.info('Client connected')

# Handle session start events
@socketio.on('session_start')
def handle_session_start(data):
    sessionId = data['sessionId']
    logging.info(f"Session started with session ID: {sessionId}")

# Handle room join events
@socketio.on('join')
def join(data):
    room_name = data['sessionId']
    email = data['email']
    voice = data['voice']
    logging.info(f"Room has been created for sessionId {room_name}")
    join_room(room_name)
    store_in_redis(data['sessionId'])
    if voice == "Deepgram":
            response = text_to_speech_stream("Hello , I am Vanii, press the mic button to start talking")
            if response :
                socketio.emit('transcription_update', {'audioBinary': response, 'user': 'Hii', 'transcription': "Hello , I am Vanii, press the mic button to start talking", 'sessionId': room_name}, to=room_name)
                
            else:
                socketio.emit('transcription_update', {'transcription': "Hello , I am Vanii, press the mic button to start talking", 'user': "Hii", 'sessionId': room_name}, to=room_name)
            
            log_event('RecordPage', {'page': '/record'}, 'user_id': room_name)
    else:
        try:
            response = text_to_speech_cartesia("Hello , I am Vanii, press the mic button to start talking")
            socketio.emit('transcription_update', {'audioBinary': response, 'user': "Hii", 'transcription': "Hello , I am Vanii, press the mic button to start talking", 'sessionId': room_name}, to=room_name)
        except Exception as e:
                socketio.emit('transcription_update', {'transcription': "Hello , I am Vanii, press the mic button to start talking", 'user': "Hii", 'sessionId': room_name}, to=room_name)
    if room_name not in dg_connections :
            initialize_deepgram_connection(room_name, email, voice)
    else:
        socketio.emit('deepgram_connection_opened', {'message': 'Deepgram connection opened'}, room=room_name)
        app_socketio.logger.info(f"Deepgram connection already exists for session {room_name}")
    socketio.send(f'sessionId {room_name} has entered the room.', room=room_name)


# Handle room leave events
@socketio.on('leave')
def on_leave(data):
    room = data['sessionId']
    leave_room(room)
    save_in_mongo_clear_redis(data['sessionId'])
    close_deepgram_connection(room)  # Close the Deepgram connection when user leaves
    log_event('ConversationEnd', {'page': '/record'}, 'user_id': room)
    logging.info(f"Client left room: {room}")

@app_socketio.route('/analytics', methods=['POST'])
def handle_upload():
    if 'audio' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    try:
        file = request.files['audio']
        logging.info('File sent for uploading')
        result = upload_file(file)
        return jsonify(result)
    except Exception as e:
            logging.error(f"Error processing audio: {str(e)}")

# Configure the app (keep your existing configuration function)
configure_app(use_cloudwatch=True)

# Run the SocketIO server
if __name__ == '__main__':
    logging.info("Starting SocketIO server.")
    socketio.run(app_socketio, debug=True, allow_unsafe_werkzeug=True, port=5001, host='0.0.0.0')
