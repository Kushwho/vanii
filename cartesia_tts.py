# cartesia_tts.py
import asyncio
import os
import json
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from cartesia.tts import AsyncCartesiaTTS

load_dotenv()

client = AsyncCartesiaTTS(api_key=os.getenv("CARTESIA_API_KEY"))

# Load voice parameters from JSON file
def load_voice_parameters(voice_name):
    with open('C:/Users/kusha/OneDrive/Desktop/Groq+Cartesia/Barbershop Man.json') as f:
        voices = json.load(f)
    return voices[voice_name]

voice_parameters = load_voice_parameters("Barbershop Man")

gen_cfg = dict(model_id="upbeat-moon", chunk_time=0.1, data_rtype='array', output_format='fp32')
play_cfg = dict(channels=1)

async def generate_audio_async(voice_name: str, transcript: str, q_audio, done_gen, **kwargs):
    voice = voice_parameters["embedding"]
    async with client:
        try:
            chunk_generator = await client.generate(transcript=transcript, voice=voice, stream=True, **kwargs)
            i = 0
            async for chunk in chunk_generator:
                if i == 0:
                    await q_audio.put(chunk)
                q_audio.put_nowait(chunk)
                i += 1
        except Exception as e:
            print(f"Error during audio generation: {e}")
        finally:
            done_gen.set()

async def play_audio_async(channels: int, q_audio, done_gen, done_play, **kwargs):
    def callback(outdata, frames, time, status):
        if q_audio.empty():
            outdata.fill(0)
            if done_gen.is_set():
                done_play.set()
                return sd.CallbackStop
            return
        chunk = q_audio.get_nowait()
        data = chunk['audio'].astype(dtype).reshape(-1, channels)
        outdata[:len(data)] = data

    init_chunk = await q_audio.get()
    block_size = len(init_chunk['audio'])
    dtype = init_chunk['audio'].dtype
    sampling_rate = init_chunk['sampling_rate']
    stream = sd.OutputStream(blocksize=block_size, samplerate=sampling_rate, callback=callback, channels=channels, dtype=dtype, **kwargs)

    with stream:
        await done_play.wait()

async def tts(voice_name: str, text: str):
    q_audio = asyncio.Queue()
    done_gen = asyncio.Event()
    done_play = asyncio.Event()
    try:
        async with client:
            await asyncio.gather(
                generate_audio_async(voice_name, text, q_audio, done_gen, **gen_cfg),
                play_audio_async(**play_cfg, q_audio=q_audio, done_gen=done_gen, done_play=done_play)
            )
    except Exception as e:
        print(f"Error during TTS process: {e}")
    finally:
        done_gen.set()
        done_play.set()
