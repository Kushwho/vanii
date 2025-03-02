import asyncio
from typing import Annotated, AsyncIterable
from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import (
    ChatContext,
    ChatImage,
    ChatMessage,
    LLMStream
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero
from livekit.plugins.deepgram import STT as DeepgramSTT
from initializeClient import initializeMongoClient
from bson.objectid import ObjectId
from livekit.plugins.azure import TTS
from livekit.plugins.deepgram import tts
from livekit.agents import tokenize
import os
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
import json

load_dotenv()


embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
chroma_client = Chroma(
    persist_directory="./chroma_langchain_db",
    embedding_function=embeddings,
    collection_name="embeddings"
)

try:
    client = initializeMongoClient()
    prompt_collection = client["VaniiWeb"]["onboardings"]
    user_collection = client["VaniiWeb"]["users"]
except Exception as e:
    print(f"Error initializing MongoDB client: {e}")
    raise

class AssistantFunction(agents.llm.FunctionContext):
    """This class is used to define functions that will be called by the assistant."""

    def __init__(self,metadata) :
        super().__init__()
        self.metadata = metadata

    @agents.llm.ai_callable(
        description=(
            "Called when asked to evaluate something that would require vision capabilities,"
            "for example, an image, video, or the webcam feed."
        )
    )
    async def image(
        self,
        user_msg: Annotated[
            str,
            agents.llm.TypeInfo(
                description="The user message that triggered this function"
            ),
        ],
    ):
        print(f"Message triggering vision capabilities: {user_msg}")
        return None

    @agents.llm.ai_callable(
        description=(
            "Called when needing to retrieve relevant context for a user query. "
            "This function will search for relevant content in the knowledge base "
            "and return it to enhance your responses."
        )
    )
    async def retrieve_context(
        self,
        query: Annotated[
            str,
            agents.llm.TypeInfo(
                description="The user query to find relevant context for"
            ),
        ],
    ):
        # print(f"Retrieving context for: {query}")
        
        # Indicate thinking to the user
        result = "I'm thinking about that..."
        
        try:
            # Define your metadata filter
            metadata_filter = {
                "$and": [
                    {"category": {"$eq": f"{self.metadata.subject}"}},
                    {"chapter": {"$eq": f"{self.metadata.chapter}"}}
                ]
            }
            
            # Retrieve relevant documents
            relevant_docs = chroma_client.similarity_search(
                query=query,
                k=2,
                filter=metadata_filter
            )
            
            # Format the retrieved context
            if relevant_docs:
                context_content = "\n".join(
                    [f"Document excerpt: {doc.page_content}" 
                     for doc in relevant_docs]
                )
                result = f"Based on my knowledge: {context_content}"
            else:
                result = "I don't have specific information about that in my knowledge base, but I'll try to help based on my general knowledge."
                
        except Exception as e:
            print(f"Error retrieving context: {e}")
            result = "I'm not able to access my knowledge base right now, but I'll try to help with what I know."
            
        return result

async def get_video_track(room: rtc.Room):
    """Get the first video track from the room. We'll use this track to process images."""

    video_track = asyncio.Future[rtc.RemoteVideoTrack]()

    for _, participant in room.remote_participants.items():
        for _, track_publication in participant.track_publications.items():
            if track_publication.track is not None and isinstance(
                track_publication.track, rtc.RemoteVideoTrack
            ):
                video_track.set_result(track_publication.track)
                print(f"Using video track {track_publication.track.sid}")
                break

    return await video_track

def replace_words(assistant: VoicePipelineAgent, text: str | AsyncIterable[str]):
    return tokenize.utils.replace_words(
        text=text,
        replacements={r'[^a-zA-Z0-9\s]': ''}
    )

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    # print(f"Room name: {ctx.room.name}")
    prompt_data = {}
    user_data = {}
    try:
        metadata = json.load(ctx.room.metadata),
        mongo_id = ObjectId(metadata.userId)
        print(f"User Id: {ctx.room.name}")
        prompt_data = prompt_collection.find_one(filter={
            "user" : mongo_id
        })
        user_data = user_collection.find_one(filter={
            "_id" : mongo_id
        })
    except Exception as e:
        print(f"Error fetching prompt data from MongoDB: {e}")

    system_prompt = f'''You are Vaanii, an AI language tutor designed to help learners improve their language skills through personalized, conversational practice.

        When a student asks you a question that might need specific information from educational materials, use the retrieve_context function to find relevant information before responding. First tell the student you're thinking, then use the function, and finally answer with the retrieved context.

        - For questions about subject details: Always use retrieve_context
        - For general conversation: Just respond naturally without using the function
        - For unclear queries: Ask clarifying questions before using retrieve_context

        Always be supportive, encouraging, and adapt to the student's level.'''

    chat_context = ChatContext(
        messages=[
            ChatMessage(
                role="system",
                content=(system_prompt),
            )
        ]
    )

    try:
        stt = DeepgramSTT(
            language="en-IN",
            model="nova-2-general",
            interim_results=True,
            smart_format=True,
            punctuate=True,
            filler_words=True,
            profanity_filter=False,
        )
        deepgram_tts = tts.TTS(
            model="aura-asteria-en",
        )
    except ValueError as e:
        print(f"Error initializing Deepgram STT: {e}")
        raise
    
    groq = openai.LLM.with_groq(parallel_tool_calls=True)
    
    # Create the function context with our tools
    fnc_ctx = AssistantFunction(metadata)
    
    latest_image: rtc.VideoFrame | None = None
    assistant = VoicePipelineAgent(
        vad=silero.VAD.load(), 
        stt=stt,
        llm=groq,
        tts=deepgram_tts,
        chat_ctx=chat_context,
        fnc_ctx=fnc_ctx,
        before_tts_cb=replace_words,
    )

    chat = rtc.ChatManager(ctx.room)

    # Flag to track if the assistant is currently speaking
    is_speaking = False

    async def _answer(text: str, use_image: bool = False):
        """
        Answer the user's message with the given text and optionally the latest
        image captured from the video track.
        """
        nonlocal is_speaking
        
        content: list[str | ChatImage] = [text]
        if use_image and latest_image:
            content.append(ChatImage(image=latest_image))

        chat_context.messages.append(ChatMessage(role="user", content=content))
        
        # Now get the full response from the LLM (which might use the retrieve_context function)
        stream = groq.chat(chat_ctx=chat_context, fnc_ctx=fnc_ctx)
        await assistant.say(stream, allow_interruptions=True)

    @chat.on("message_received")
    def on_message_received(msg: rtc.ChatMessage):
        """This event triggers whenever we get a new message from the user."""
        if msg.message and not is_speaking:
            asyncio.create_task(_answer(msg.message, use_image=False))

    @assistant.on("function_calls_finished")
    def on_function_calls_finished(called_functions: list[agents.llm.CalledFunction]):
        """This event triggers when an assistant's function call completes."""
        if len(called_functions) == 0:
            return

        user_msg = called_functions[0].call_info.arguments.get("user_msg")
        if user_msg and not is_speaking:
            asyncio.create_task(_answer(user_msg, use_image=True))

    assistant.start(ctx.room)

    await asyncio.sleep(1)

    await assistant.say("Hi, I am Vaanii, your language tutor. Feel free to ask me questions about your lessons or practice conversation with me.", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))