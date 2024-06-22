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
import os
from llm import batch 
from text_to_speech import text_to_speech
from database import store_history



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
            # print(transcript)
            resp = batch(sessionId,transcript)
            logging.info(f"Batch response: {resp}")
            # with requests.post("https://api.deepgram.com/v1/speak", stream=True, headers=headers, json={"text": resp}) as r:  
            #     i = 0
            #     for chunk in r.iter_content(chunk_size=1024):
            #         i+=1
            #         if chunk:
            #             # print(chunk)
            #             socketio.emit('transcription_update', {'audioBinary': chunk,'transcription': resp})
            #             # time.sleep(1)
            #             # print("chunk emmited")
            #     print(i)
            response = text_to_speech(resp)
            if response.status_code == 200:
                logging.info("Successfully converted text to speech")
                socketio.emit('transcription_update', {'audioBinary': response.content,'transcription': resp})
            else:
                # print(f"Error: {response.status_code} - {response.text}")
                logging.error(f"Text-to-speech conversion failed: {response.status_code} - {response.text}")
                socketio.emit('transcription_update', {'transcription': resp})
            # print(type(response.content))
            logging.info("Emitted transcription update")

    def on_close(self, close, **kwargs):
        logging.info(f"Deepgram connection closed: {close}")
        # print(f"\n\n{close}\n\n")

    def on_error(self, error, **kwargs):
        # print(f"\n\n{error}\n\n")
        logging.error(f"Deepgram connection error: {error}")

    dg_connection.on(LiveTranscriptionEvents.Open, on_open)
    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

   
    options = LiveOptions(model="nova-2", language="en-IN",endpointing=200)

    if dg_connection.start(options) is False: 
        logging.error("Failed to start Deepgram connection")
        exit()
        # print("Failed to start connection")

@socketio.on('audio_stream')
def handle_audio_stream(data):
    global sessionId
    logging.info(f"Received audio stream for session ID: {sessionId}")
    if dg_connection:
        dg_connection.send(data)

@socketio.on('toggle_transcription')
def handle_toggle_transcription(data):
    # print("toggle_transcription", data)
    logging.info(f"Received toggle_transcription event: {data}")
    action = data.get("action")
    if action == "start":
        print("Starting Deepgram connection")
        initialize_deepgram_connection()

@socketio.on('connect')
def server_connect():
    logging.info('Client connected')
    # print('Client connected')

@socketio.on('restart_deepgram')
def restart_deepgram():
    # print('Restarting Deepgram connection')
    logging.info('Restarting Deepgram connection')
    initialize_deepgram_connection()


@socketio.on('session_start')
def handle_session_start(data):
    global sessionId
    sessionId = data
    logging.info(f"Session started with session ID: {sessionId}")
    # print(f"Session started with session ID: {sessionId}")


if __name__ == '__main__':
    logging.info("Starting SocketIO server.")
    socketio.run(app_socketio, debug=True, allow_unsafe_werkzeug=True, port=5001)