# main.py
import asyncio
from llm import get_groq_response_stream
from cartesia_tts import tts, client

async def main():
    while True:
        prompt_text = input("You: ")
        response_buffer = []
        async for response_chunk in get_groq_response_stream(prompt_text):
            if response_chunk.strip():  # Ensure the response_chunk is not empty
                response_buffer.append(response_chunk)
            else:
                print("Received an empty response chunk.")
        full_response = "".join(response_buffer)
        print(f"Complete Response: {full_response}")  # Debugging: Check the complete response
        if full_response.strip():  # Ensure the full response is not empty
            await tts("Barbershop Man", full_response)


if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        loop.run_until_complete(client.close())
        loop.close()
