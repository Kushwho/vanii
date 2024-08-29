import os
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room
from dotenv import load_dotenv
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions, DeepgramClientOptions
from llm import batch, save_in_mongo_clear_redis, store_in_redis,streaming
from text_to_speech import text_to_speech, text_to_speech_cartesia,text_to_speech_stream
import time
from threading import Timer
from utils import log_event as log_event_sync
from utils import store_audio_chunk,log_function_call
from config import Config
from models import db
from log_config import setup_logging
import logging
from concurrent.futures import ThreadPoolExecutor
from analytics.speech_analytics import upload_file  
import sentry_sdk 
import json

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


# Get the API keys from environment variables
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

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

def configure_app(use_cloudwatch):
    with app_socketio.app_context():
        db.create_all()
    
    # Set up logging
    logger = setup_logging(use_cloudwatch)
    
    # Configure Flask to use our logger
    app_socketio.logger.handlers = logger.handlers
    app_socketio.logger.setLevel(logger.level)

config = DeepgramClientOptions(
    verbose=logging.WARN,
    options={"keepalive": "true"}
)
deepgram = DeepgramClient(DEEPGRAM_API_KEY, config)

# Asynchronous wrapper for log_event
def async_log_event(event_type, event_data):
    executor.submit(log_event_sync, event_type, event_data)

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
        transcript = transcript_buffers[sessionId]
        app_socketio.logger.info(f"Processing buffered transcripts for session {sessionId}: {transcript}")
        
        # resp = batch(sessionId, transcript)
        resp_stream = ''
        for chunk in streaming(session_id=sessionId,transcript=transcript) :
            resp_stream += chunk.content
        app_socketio.logger.info(f"Streamed response: {resp_stream}")

        starttime = time.time()
        voice = 'Deepgram'
        if dg_connections[sessionId] : 
            voice = dg_connections[sessionId].get('voice', 'Deepgram')
        
        if voice == "Deepgram":
            response = text_to_speech_stream(resp_stream)
            # if response.status_code == 200:
            #     socketio.emit('transcription_update', {'audioBinary': response.content, 'user': transcript, 'transcription': resp_stream, 'sessionId': sessionId}, to=sessionId)
                
            # else:
            #     socketio.emit('transcription_update', {'transcription': resp_stream, 'user': transcript, 'sessionId': sessionId}, to=sessionId)
            socketio.emit('transcription_update', {'audioBinary': response, 'user': transcript, 'transcription': resp_stream, 'sessionId': sessionId}, to=sessionId)
        else:
            try:
                response = text_to_speech_cartesia(resp_stream)
                socketio.emit('transcription_update', {'audioBinary': response, 'user': transcript, 'transcription': resp_stream, 'sessionId': sessionId}, to=sessionId)
            except Exception as e:
                socketio.emit('transcription_update', {'transcription': resp_stream, 'user': transcript, 'sessionId': sessionId}, to=sessionId)
        
        endtime = time.time() - starttime
        app_socketio.logger.info(f"It took {endtime} seconds for text to speech")

        transcript_buffers[sessionId] = ""
        buffer_timers[sessionId] = None

# Initialize Deepgram connection for a session
def initialize_deepgram_connection(sessionId, email, voice):
    app_socketio.logger.info(f"Initializing Deepgram connection for session {sessionId}")
    
    dg_connection = deepgram.listen.websocket.v("1")

    def on_open(self, open, **kwargs):
        async_log_event('UserMicOn', {'page': 'index', 'email': email})
        logging.info(f"Deepgram connection opened for session {sessionId}: {open}")
        socketio.emit('deepgram_connection_opened', {'message': 'Deepgram connection opened'}, room=sessionId)

    def on_message(self, result, **kwargs):
        transcript = result.channel.alternatives[0].transcript
        if len(transcript) > 0:
            logging.info(f"Received transcript for session {sessionId}: {transcript}")
            buffer_transcripts(transcript, sessionId)
    
    def on_metadata(self, metadata, **kwargs):
        logging.info(f"Received metadata for session {sessionId}: {metadata}")

    def on_close(self, close, **kwargs):
        async_log_event('UserMicOff', {'page': 'index', 'email': email})
        logging.info(f"Deepgram connection closed for session {sessionId}: {close}")

    def on_error(self, error, **kwargs):
        logging.error(f"Deepgram connection error for session {sessionId}: {error}")

    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)

    options = LiveOptions(model="nova-2", language="en", endpointing=1000)  

    if not dg_connection.start(options):
        logging.error(f"Failed to start Deepgram connection for session {sessionId}")
        return None

    dg_connections[sessionId] = {'connection': dg_connection, 'voice': voice}
    return dg_connection

@log_function_call
def collate_and_store_audio(session_id, audio_data):
    if session_id not in audio_buffers:
        audio_buffers[session_id] = []

    audio_buffers[session_id].append(audio_data)
   
    if len(audio_buffers[session_id]) >= 10:  # 10 chunks of 1 second each
        audio_chunk = b''.join(audio_buffers[session_id])
        audio_buffers[session_id] = []  # Clear the buffer
        store_audio_chunk(session_id, audio_chunk)

# Handle incoming audio streams
@socketio.on('audio_stream')
def handle_audio_stream(data):
    sessionId = data.get("sessionId")
    logging.info(f"Received audio stream for session ID: {sessionId}")
    if sessionId in dg_connections:
        dg_connections[sessionId]['connection'].send(data.get("data"))
        logging.info(f"Audio sent for session ID: {sessionId}")
    else:
        # socketio.emit('deepgram_connection_opened', {'message': 'Deepgram connection opened'}, room=sessionId)
        logging.warning(f"No active Deepgram connection for session ID: {sessionId}")
    
    # Use the executor to run the collate_and_store_audio function
    executor.submit(collate_and_store_audio, sessionId, data.get("data"))

# Handle transcription toggle events
# @socketio.on('toggle_transcription')
# def handle_toggle_transcription(data):
#     app_socketio.logger.info(f"Received toggle_transcription event: {data}")
#     action = data.get("action")
#     sessionId = data.get("sessionId")
#     email = data.get("email")
#     voice = data.get("voice")
    
#     if action == "start":
#         app_socketio.logger.info(f"Starting Deepgram connection for session {sessionId}")
#         if sessionId not in dg_connections:
#             initialize_deepgram_connection(sessionId, email, voice)
#         else:
#             app_socketio.logger.info(f"Deepgram connection already exists for session {sessionId}")
#     elif action == "stop":
#         app_socketio.logger.info(f"Stopping Deepgram connection for session {sessionId}")
        # close_deepgram_connection(sessionId)

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
    email = data.get("email")
    voice = data.get("voice")
    logging.info(f"Room has been created for sessionId {room_name}")
    join_room(room_name)
    store_in_redis(data['sessionId'])
    if voice == "Deepgram":
            response = text_to_speech("Hello , I am Vaanii")
            if response.status_code == 200:
                socketio.emit('transcription_update', {'audioBinary': response.content, 'user': 'Hii', 'transcription': "Hello , I am Vanii", 'sessionId': room_name}, to=room_name)
                
            else:
                socketio.emit('transcription_update', {'transcription': "Hello , I am Vanii", 'user': "Hii", 'sessionId': room_name}, to=room_name)
    else:
        try:
            response = text_to_speech_cartesia("Hello , I am Vaanii")
            socketio.emit('transcription_update', {'audioBinary': response, 'user': "Hii", 'transcription': "Hello , I am Vanii", 'sessionId': room_name}, to=room_name)
        except Exception as e:
                socketio.emit('transcription_update', {'transcription': "Hello , I am Vanii", 'user': "Hii", 'sessionId': room_name}, to=room_name)
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
