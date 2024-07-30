import os
from dotenv import load_dotenv
import requests
import logging
from cartesia import Cartesia

load_dotenv()

url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=mp3"


CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
# Initialize Cartesia client
cartesia_client = Cartesia(api_key=CARTESIA_API_KEY)

# Voice ID and model for Cartesia TTS

model_id = "sonic-english"
output_format = {
    "container": "raw",
    "encoding": "pcm_f32le",
    "sample_rate": 44100,
}


API_KEY = os.getenv("DEEPGRAM_API_KEY")


headers = {
    "Authorization": f"Token {API_KEY}",
    "Content-Type": "application/json"
}

session = requests.Session()
session.headers.update(headers)


def text_to_speech(resp):
    payload = {
            "text": resp
            }
    response = requests.post(url, headers=headers, json=payload)
    return response


def text_to_speech2(resp):
    payload = {
        "text": resp
    }
    
    # Stream the response for faster processing
    with session.post(url, json=payload, stream=True) as response:
        if response.status_code == 200:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    yield chunk
        else:
            logging.error(f"Text-to-speech conversion failed: {response.status_code} - {response.text}")
            yield b''


def text_to_speech_cartesia(response ,voice_id = "ff1bb1a9-c582-4570-9670-5f46169d0fc8") : 
    try :
        voice = cartesia_client.voices.get(id=voice_id)
        audio_data = b""
        for output in cartesia_client.tts.sse(
            model_id=model_id,
            transcript=response,
            voice_embedding=voice["embedding"],
            stream=True,
            output_format=output_format,
        ):
            audio_data += output["audio"]
        return audio_data
    except Exception as e :
        logging.error(f"Error in cartesia text to speech {e}")