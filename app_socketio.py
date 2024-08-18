import os
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, join_room, leave_room
from dotenv import load_dotenv
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions, DeepgramClientOptions
from llm import batch, save_in_mongo_clear_redis, store_in_redis
from text_to_speech import text_to_speech, text_to_speech_cartesia
import time
from threading import Timer, Lock
from utils import log_event as log_event_sync
from config import Config
from models import db
from log_config import setup_logging
import logging
from concurrent.futures import ThreadPoolExecutor
from analytics.speech_analytics import upload_file  


# Load environment variables from .env file
load_dotenv()

# Get the API keys from environment variables
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Initialize Flask and SocketIO
app_socketio = Flask("app_socketio")
app_socketio.config.from_object(Config)
db.init_app(app_socketio)
socketio = SocketIO(app_socketio, cors_allowed_origins='*')

# Define a Thread Pool Executor
executor = ThreadPoolExecutor(max_workers=3)

def configure_app(use_cloudwatch):
    with app_socketio.app_context():
        db.create_all()
    
    # Set up logging
    logger = setup_logging(use_cloudwatch)
    
    # Configure Flask to use our logger
    app_socketio.logger.handlers = logger.handlers
    app_socketio.logger.setLevel(logger.level)

# Initialize Deepgram client
config = DeepgramClientOptions(
    verbose=logging.WARN,
    options={"keepalive": "true"}
)
deepgram = DeepgramClient(DEEPGRAM_API_KEY, config)

# Global variables
dg_connection = None
buffer_lock = Lock()
transcript_buffer = ""
buffer_timer = None

rate = 44100
stream = None

# Buffer transcripts and process them after a delay
def buffer_transcripts(transcript, sessionId):
    global transcript_buffer, buffer_timer

    with buffer_lock:
        transcript_buffer += transcript
        # Restart timer for processing buffered transcripts
        if buffer_timer is not None:
            buffer_timer.cancel()
        buffer_timer = Timer(1, process_transcripts, [sessionId])
        buffer_timer.start()

# Process buffered transcripts and convert them to speech
def process_transcripts(sessionId):
    global transcript_buffer, buffer_timer

    with buffer_lock:
        if len(transcript_buffer) > 0:
            app_socketio.logger.info(f"Processing buffered transcripts: {transcript_buffer}")
            resp = batch(sessionId, transcript_buffer)
            app_socketio.logger.info(f"Batch response: {resp}")

            starttime = time.time()
            response = text_to_speech(resp)
            if response.status_code == 200:
                socketio.emit('transcription_update', {'audioBinary': response.content,'user': transcript_buffer, 'transcription': resp, 'sessionId': sessionId}, to=sessionId)
            else:
                socketio.emit('transcription_update', {'transcription': resp, 'user': transcript_buffer, 'sessionId': sessionId}, to=sessionId)

            endtime = time.time() - starttime
            app_socketio.logger.info(f"It took {endtime} seconds for text to speech")

            transcript_buffer = ""
            buffer_timer = None

# Asynchronous wrapper for log_event
def async_log_event(event_type, event_data):
    executor.submit(log_event_sync, event_type, event_data)

# Initialize Deepgram connection for a session
def initialize_deepgram_connection(sessionId,email):
    global dg_connection
    app_socketio.logger.info("Initializing Deepgram connection")
    dg_connection = deepgram.listen.websocket.v("1")

    def on_open(self, open, **kwargs):
        async_log_event('UserMicOn', {'page': 'index','email' : email})
        logging.info(f"Deepgram connection opened: {open}")
        socketio.emit('deepgram_connection_opened', {'message': 'Deepgram connection opened'}, room=sessionId)

    def on_message(self, result, **kwargs):
        transcript = result.channel.alternatives[0].transcript
        if len(transcript) > 0:
            logging.info(f"Received transcript: {transcript}")
            buffer_transcripts(transcript, sessionId)
    
    def on_metadata(self, metadata, **kwargs):
        logging.info(f"Received metadata: {metadata}")

    def on_close(self, close, **kwargs):
        async_log_event('UserMicOff', {'page': 'index','email' : email})
        logging.info(f"Deepgram connection closed: {close}")

    def on_error(self, error, **kwargs):
        logging.error(f"Deepgram connection error: {error}")

    def on_utterance_end(self, end, **kwargs):
        logging.info(f"Utterance end detected: {end}")
        process_transcripts(sessionId)

    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
    # dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)

    options = LiveOptions(model="nova-2", language="en", endpointing=1000)  

    if not dg_connection.start(options):
        logging.error("Failed to start Deepgram connection")
        exit()

# Handle incoming audio streams
@socketio.on('audio_stream')
def handle_audio_stream(data):
    sessionId = data.get("sessionId")
    logging.info(f"Received audio stream for session ID: {sessionId}")
    if dg_connection:
        dg_connection.send(data.get("data"))
        logging.info(f"Audio sent for session ID: {sessionId}")

# Handle transcription toggle events
@socketio.on('toggle_transcription')
def handle_toggle_transcription(data):
    app_socketio.logger.info(f"Received toggle_transcription event: {data}")
    action = data.get("action")
    sessionId = data.get("sessionId")
    email = data.get("email")
    if action == "start":
        app_socketio.logger.info("Starting Deepgram connection")
        # log_event('UserMicOn', {'page': 'index'})
        initialize_deepgram_connection(sessionId,email)

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
    logging.info(f"Room has been created for sessionId {room_name}")
    room = room_name
    join_room(room)
    store_in_redis(data['sessionId'])
    socketio.send(f'sessionId {room} has entered the room.', room=room)

# Handle room leave events
@socketio.on('leave')
def on_leave(data):
    room = data['sessionId']
    leave_room(room)
    save_in_mongo_clear_redis(data['sessionId'])
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

configure_app(use_cloudwatch=True)
# Run the SocketIO server
if __name__ == '__main__':
    logging.info("Starting SocketIO server.")
    socketio.run(app_socketio, debug=True, allow_unsafe_werkzeug=True, port=5001, host='0.0.0.0')
