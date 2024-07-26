import os
from dotenv import load_dotenv
import requests
import logging
from deepgram import DeepgramClient, SpeakOptions
from cartesia import Cartesia
from llm import streaming

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


#supported `output_format`s at https://docs.cartesia.ai/api-reference/endpoints/stream-speech-server-sent-events




API_KEY = os.getenv("DEEPGRAM_API_KEY")


headers = {
    "Authorization": f"Token {API_KEY}",
    "Content-Type": "application/json"
}



deepgram = DeepgramClient(API_KEY)


client = Cartesia(api_key=os.environ.get("CARTESIA_API_KEY"))





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
        
    


def synthesize_audio(text, model="aura-asteria-en"):
    try:
        options = SpeakOptions(model=model)
        dg_stream = deepgram.speak.v("1").stream({"text":text}, options)        
        return dg_stream

    except Exception as e:
        raise ValueError(f"Speech synthesis failed: {str(e)}")


def text_to_speech(resp):
    payload = {
            "text": resp
            }
    response = requests.post(url, headers=headers, json=payload)
    return response




