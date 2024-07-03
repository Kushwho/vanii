import os
from dotenv import load_dotenv
import requests
import logging

load_dotenv()

url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=mp3"




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