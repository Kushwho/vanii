import os
from dotenv import load_dotenv
import requests

load_dotenv()

url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=mp3"


API_KEY = os.getenv("DEEPGRAM_API_KEY")


headers = {
    "Authorization": f"Token {API_KEY}",
    "Content-Type": "application/json"
}


def text_to_speech(resp):
    payload = {
            "text": resp
            }
    response = requests.post(url, headers=headers, json=payload)
    return response