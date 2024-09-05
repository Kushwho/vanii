from deepgram import DeepgramClient, DeepgramClientOptions
from dotenv import load_dotenv
import logging
import os

class DeepgramService:
    def __init__(self):
        # Load environment variables from .env file
        load_dotenv()

        # Fetch the API key from environment variables
        self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")

        # Set up client configuration
        self.config = DeepgramClientOptions(
            verbose=logging.ERROR,
            options={"keepalive": "true"}
        )

        # Initialize the Deepgram client
        self.deepgram_client = DeepgramClient(self.deepgram_api_key, self.config)

    def get_client(self):
        # Returns the initialized Deepgram client instance
        return self.deepgram_client


