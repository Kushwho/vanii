from cartesia import Cartesia
import pyaudio
import os
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
import time

load_dotenv()

client = Cartesia(api_key=os.environ.get("CARTESIA_API_KEY"))

transcripts = [
    "The crew engaged in a range of activities designed to mirror those "
    "they might perform on a real Mars mission. ",
    "Aside from growing vegetables and maintaining their habitat, they faced "
    "additional stressors like communication delays with Earth, ",
    "up to twenty-two minutes each way, to simulate the distance from Mars to our planet. ",
    "These exercises were critical for understanding how astronauts can "
    "maintain not just physical health but also mental well-being under such challenging conditions. ",
]

chat = ChatGroq(temperature=0, model_name="llama3-8b-8192", groq_api_key=os.getenv("GROQ_API_KEY"))
system = '''You are Vanii, act like  a Language Teacher with a vibrant personality, dedicated to making learning English fun and engaging and keep your reponses short.

Example Interactions:

User: "How do you pronounce 'environment'?"

Vanii: "Absolutely! The pronunciation of 'environment' is en-vy-ron-ment. Let's break it down together: en-vy-ron-ment. Fantastic job! Ready to tackle another word?"

User: "Can you explain the difference between 'your' and 'you're'?"

Vanii: "Of course! 'Your' is possessive, like in 'your book'. 'You're' is a contraction of 'you are', as in 'you're doing awesome'. Try using each one in a sentence. You're doing brilliantly! Need more clarification?"

User: "What's the pronunciation of 'accessibility'?"

Vanii: "Great choice! 'Accessibility' is pronounced ak-sess-i-bil-i-ty. Let's break it down step by step: ak-sess-i-bil-i-ty. Keep practicing, you're doing wonderfully! Any other words you're curious about?"'''

# Ending each transcript with a space makes the audio smoother
def chunk_generator(transcripts):
    for transcript in transcripts:
        if transcript.endswith(" "):
            yield transcript
        else:
            yield transcript + " "



def streaming(input):
    prompt = ChatPromptTemplate.from_messages([
        ('system',system),
        ('user','{input}')
    ])

    chain = prompt | chat
    
    for chunk in chain.stream({"input" : input}) :
        if(chunk.content==''):
            yield(' ')
            continue
        # print(chunk.content)
        yield(chunk.content)


# You can check out voice IDs by calling `client.voices.list()` or on https://play.cartesia.ai/
voice_id = "ff1bb1a9-c582-4570-9670-5f46169d0fc8"

# You can check out our models at https://docs.cartesia.ai/getting-started/available-models
model_id = "sonic-english"

# You can find the supported `output_format`s at https://docs.cartesia.ai/api-reference/endpoints/stream-speech-server-sent-events
output_format = {
    "container": "raw",
    "encoding": "pcm_f32le",
    "sample_rate": 44100,
}

# p = pyaudio.PyAudio()
# rate = 44100

# stream = None

# # Set up the websocket connection
# ws = client.tts.websocket()

# # Create a context to send and receive audio
# ctx = ws.context()  # Generates a random context ID if not provided

# # Pass in a text generator to generate & stream the audio
# output_stream = ctx.send(
#     model_id=model_id,
#     transcript=streaming("What is your name."),
#     voice_id=voice_id,
#     output_format=output_format,
# )

# print(output_stream)
# for output in output_stream:
#     buffer = output["audio"]
#     # print(buffer)
#     if not stream:
#         stream = p.open(format=pyaudio.paFloat32, channels=1, rate=rate, output=True)
#         print(stream)

#     # Write the audio data to the stream
#     # print(type(stream))
#     # print(stream)
#     stream.write(buffer)

# stream.stop_stream()
# stream.close()
# p.terminate()

# ws.close()  # Close the websocket connection



# st = time.time()
# streaming("Write a poem on The sun.")
# print(time.time() - st)

if __name__ == "__main__" :
    
    voices = client.voices.list()
    for voice in voices :
        # print(voice.id,end=" ")
        # print(voice.name)
        print(voice['id'],end=" ")
        print(voice['name'])
        # break

    