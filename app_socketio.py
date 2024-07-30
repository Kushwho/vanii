import logging
import os
from flask import Flask
from flask_socketio import SocketIO, join_room, leave_room
from dotenv import load_dotenv
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions, DeepgramClientOptions
from llm import batch, streaming
import time
from threading import Timer, Lock
from text_to_speech import text_to_speech_cartesia



logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("app_socketio.log"),
        logging.StreamHandler()
    ]
)


# Load environment variables from .env file
load_dotenv()

# Get the API keys from environment variables
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


# Initialize Flask and SocketIO
app_socketio = Flask("app_socketio")
socketio = SocketIO(app_socketio, cors_allowed_origins='*')

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
        buffer_timer = Timer(1.5, process_transcripts, [sessionId])
        buffer_timer.start()

# Process buffered transcripts and convert them to speech
def process_transcripts(sessionId):
    global transcript_buffer, buffer_timer

    with buffer_lock:
        if len(transcript_buffer) > 0:
            try:
                response = batch(sessionId,transcript_buffer)
                if response :
                    audio_data = text_to_speech_cartesia(response)


                    socketio.emit('transcription_update', {
                        'audioBinary': audio_data,
                        'transcription': response,
                        'sessionId': sessionId
                    }, to=sessionId)

            except Exception as e:
                socketio.emit('transcription_update', {
                    'transcription': response,
                    'sessionId': sessionId
                }, to=sessionId)
                logging.error(f"Error in speech synthesis: {str(e)}")

            transcript_buffer = ""
            buffer_timer = None

# Initialize Deepgram connection for a session
def initialize_deepgram_connection(sessionId):
    global dg_connection
    logging.info("Initializing Deepgram connection")
    dg_connection = deepgram.listen.websocket.v("1")

    def on_open(self, open, **kwargs):
        logging.info(f"Deepgram connection opened: {open}")

    def on_message(self, result, **kwargs):
        transcript = result.channel.alternatives[0].transcript
        if len(transcript) > 0:
            logging.info(f"Received transcript: {transcript}")
            buffer_transcripts(transcript, sessionId)

    def on_metadata(self, metadata, **kwargs):
        logging.info(f"\n\n{metadata}\n\n")

    def on_close(self, close, **kwargs):
        logging.info(f"Deepgram connection closed: {close}")
    
    def on_warning(self,warning,**kwargs):
        logging.info(f"Deepgram warning: {warning}")

    def on_error(self, error, **kwargs):
        logging.error(f"Deepgram connection error: {error}")

    def on_utterance_end(self, end, **kwargs):
        logging.info(f"Utterance end detected: {end}")
        process_transcripts(sessionId)

    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
    dg_connection.on(LiveTranscriptionEvents.Warning, on_warning)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)
    dg_connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)

    options = LiveOptions(model="nova-2", language="en", endpointing=1500)

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
    logging.info(f"Received toggle_transcription event: {data}")
    action = data.get("action")
    sessionId = data.get("sessionId")
    if action == "start":
        logging.info("Starting Deepgram connection")
        initialize_deepgram_connection(sessionId)

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
    socketio.send(f'sessionId {room} has entered the room.', room=room)


# Handle room leave events
@socketio.on('leave')
def on_leave(data):
    room = data['sessionId']
    leave_room(room)
    logging.info(f"Client left room: {room}")

# Run the SocketIO server
if __name__ == '__main__':
    logging.info("Starting SocketIO server.")
    socketio.run(app_socketio, debug=True, allow_unsafe_werkzeug=True, port=5001)
