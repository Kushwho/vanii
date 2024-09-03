import os
from dotenv import load_dotenv
import requests
import logging
from cartesia import Cartesia
import time
from DeepgramClient import deepgram
from deepgram import SpeakOptions
load_dotenv()

url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=mp3"




#supported `output_format`s at https://docs.cartesia.ai/api-reference/endpoints/stream-speech-server-sent-events
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

options = SpeakOptions(model="aura-hera-en")


session = requests.Session()
session.headers.update(headers)





def text_to_speech_cartesia(response ,voice_id = "ff1bb1a9-c582-4570-9670-5f46169d0fc8") : 
    try :
        start_time = time.time()
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
        logging.info(f"It took {time.time()-start_time} for cartesia text to speech")
        return audio_data
    except Exception as e :
        logging.error(f"Error in cartesia text to speech {e}")

def text_to_speech_cartesia_batch(response ,voice_id = "ff1bb1a9-c582-4570-9670-5f46169d0fc8") : 
    try :
        start_time = time.time()
        voice = cartesia_client.voices.get(id=voice_id)
        audio_data = cartesia_client.tts.sse(
            model_id=model_id,
            transcript=response,
            voice_embedding=voice["embedding"],
            stream=False,
            output_format=output_format,
        )["audio"]
        logging.info(f"It took {time.time()-start_time} for cartesia text to speech batch")
        return audio_data
    except Exception as e :
        logging.error(f"Error in cartesia text to speech {e}")




def text_to_speech_stream(resp):
    audio_content = b''
    dg_stream = deepgram.speak.v("1").stream({"text" : resp})
    for chunk in dg_stream.stream.read(1024) :
        if chunk:
            audio_content += chunk  
    
    return audio_content  

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



