from deepgram import DeepgramClient,DeepgramClientOptions
from dotenv import load_dotenv
import logging
import os
load_dotenv()





DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
config = DeepgramClientOptions(
    verbose=logging.ERROR,
    options={"keepalive": "true"}
)
deepgram = DeepgramClient(DEEPGRAM_API_KEY, config)