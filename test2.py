import httpx
import threading
import time
import json

from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
)

# Your Deepgram API key
DEEPGRAM_API_KEY = '🔑🔑🔑 Your API Key here! 🔑🔑🔑'

# URL for the realtime streaming audio you would like to transcribe
URL = 'http://stream.live.vc.bbcmedia.co.uk/bbc_world_service'

# Duration for transcription in seconds
TRANSCRIPTION_DURATION = 30

# Set this variable to `True` if you wish only to 
# see the transcribed words, like closed captions. 
# Set it to `False` if you wish to see the raw JSON responses.
TRANSCRIPT_ONLY = False

def main():
    try:
        # Initialize Deepgram client
        deepgram = DeepgramClient(DEEPGRAM_API_KEY)

        # Create a websocket connection to Deepgram
        dg_connection = deepgram.listen.live.v("1")

        # Define event handlers
        def on_message(self, result, **kwargs):
            if TRANSCRIPT_ONLY:
                sentence = result.channel.alternatives[0].transcript
                if len(sentence) > 0:
                    print(f"Speaker: {sentence}")
            else:
                # Extract relevant information from the LiveResultResponse object
                response_dict = {
                    "type": result.type,
                    "channel": {
                        "alternatives": [
                            {
                                "transcript": alt.transcript
                            } for alt in result.channel.alternatives
                        ]
                    }
                }
                print(json.dumps(response_dict, indent=4))


        def on_metadata(self, metadata, **kwargs):
            print(f"\n\n{metadata}\n\n")

        def on_error(self, error, **kwargs):
            print(f"\n\n{error}\n\n")

        # Register event handlers
        dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
        dg_connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
        dg_connection.on(LiveTranscriptionEvents.Error, on_error)

        # Configure Deepgram options for live transcription
        options = LiveOptions(
            model="nova-2", 
            language="en-US", 
            smart_format=True,
        )

        # Start the connection
        dg_connection.start(options)

        # Create a lock and a flag for thread synchronization
        lock_exit = threading.Lock()
        exit = False

        # Define a thread that streams the audio and sends it to Deepgram
        def myThread():
            start_time = time.time()
            with httpx.stream("GET", URL) as r:
                for data in r.iter_bytes():
                    if time.time() - start_time >= TRANSCRIPTION_DURATION:
                        break
                    dg_connection.send(data)

        # Start the thread
        myHttp = threading.Thread(target=myThread)
        myHttp.start()

        # Wait for the specified duration
        myHttp.join(TRANSCRIPTION_DURATION)

        # Set the exit flag to True to stop the thread
        lock_exit.acquire()
        exit = True
        lock_exit.release()

        # Close the connection to Deepgram
        dg_connection.finish()

        print("Finished")

    except Exception as e:
        print(f"Could not open socket: {e}")
        return


if __name__ == "__main__":
    main()
