import logging
import os
from flask import Flask
from flask_socketio import SocketIO
from dotenv import load_dotenv
from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
    DeepgramClientOptions
)
from llm import batch 
from text_to_speech import text_to_speech2 , text_to_speech
import time

load_dotenv()

API_KEY = os.getenv("DEEPGRAM_API_KEY")

app_socketio = Flask("app_socketio")
socketio = SocketIO(app_socketio, cors_allowed_origins='*')

config = DeepgramClientOptions(
    verbose=logging.WARN,  
    options={"keepalive": "true"}
)

deepgram = DeepgramClient(API_KEY, config)

dg_connection = None

sessionId = None

headers = {
    "Authorization": f"Token {API_KEY}",
    "Content-Type": "application/json"
}

def initialize_deepgram_connection():
    global dg_connection
    # Initialize Deepgram client and connection
    logging.info("Initializing Deepgram connection")
    dg_connection = deepgram.listen.live.v("1")

    def on_open(self, open, **kwargs):
        logging.info(f"Deepgram connection opened: {open}")
        print(f"\n\n{open}\n\n")

    def on_message(self, result, **kwargs):
        transcript = result.channel.alternatives[0].transcript
        if len(transcript) > 0:
            logging.info(f"Received transcript: {transcript}")
            resp = batch(sessionId, transcript)
            logging.info(f"Batch response: {resp}")
            
            starttime = time.time()
            
            # Stream the response to the client
            # audio_chunks = text_to_speech2(resp)
            # for chunk in audio_chunks:
            #     socketio.emit('transcription_update', {'audioBinary': chunk, 'transcription': resp})

            response = text_to_speech(resp)

            if response.status_code==200 :
                socketio.emit('transcription_update', {'audioBinary': response.content, 'transcription': resp})

            else :
                socketio.emit('transcription_update', {'transcription': resp})
            
            endtime = time.time() - starttime
            logging.info(f"It took {endtime} seconds for text to speech")

    def on_close(self, close, **kwargs):
        logging.info(f"Deepgram connection closed: {close}")

    def on_error(self, error, **kwargs):
        logging.error(f"Deepgram connection error: {error}")

    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

    options = LiveOptions(model="nova-2", language="en", endpointing=400)

    if dg_connection.start(options) is False:
        logging.error("Failed to start Deepgram connection")
        exit()

@socketio.on('audio_stream')
def handle_audio_stream(data):
    global sessionId
    logging.info(f"Received audio stream for session ID: {sessionId}")
    if dg_connection:
        dg_connection.send(data)
        logging.info(f"Audio sent for session ID: {sessionId}")

@socketio.on('toggle_transcription')
def handle_toggle_transcription(data):
    logging.info(f"Received toggle_transcription event: {data}")
    action = data.get("action")
    if action == "start":
        logging.info("Starting Deepgram connection")
        initialize_deepgram_connection()

@socketio.on('connect')
def server_connect():
    logging.info('Client connected')

@socketio.on('restart_deepgram')
def restart_deepgram():
    logging.info('Restarting Deepgram connection')
    initialize_deepgram_connection()

@socketio.on('session_start')
def handle_session_start(data):
    global sessionId
    sessionId = data
    logging.info(f"Session started with session ID: {sessionId}")

if __name__ == '__main__':
    logging.info("Starting SocketIO server.")
    socketio.run(app_socketio, debug=True, allow_unsafe_werkzeug=True, port=5001)
