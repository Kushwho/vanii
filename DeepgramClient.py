from deepgram import DeepgramClient, DeepgramClientOptions
from dotenv import load_dotenv
import logging
import os

class DeepgramService:
    def __init__(self):
        load_dotenv()

        self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")

        self.config = DeepgramClientOptions(
            verbose=logging.ERROR,
            options={"keepalive": "true"}
        )

        self.deepgram_client = DeepgramClient(self.deepgram_api_key, self.config)

    def get_client(self):
        
        return self.deepgram_client


