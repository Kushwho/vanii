import asyncio
from typing import Annotated,AsyncIterable
from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import (
    ChatContext,
    ChatImage,
    ChatMessage,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero
from livekit.plugins.deepgram import STT as DeepgramSTT
from initializeClient import initializeMongoClient
from bson.objectid import ObjectId
from livekit.plugins.azure import TTS
from livekit.plugins.deepgram import tts
from livekit.agents import tokenize




class AssistantFunction(agents.llm.FunctionContext):
    """This class is used to define functions that will be called by the assistant."""

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




async def entrypoint(ctx: JobContext,client):
    await ctx.connect()
    print(f"Room name: {ctx.room.name}")
    prompt_collection = client["VaniiWeb"]["onboardings"]
    user_collection =   client["VaniiWeb"]["users"]
    user_data = {}
    prompt_data = {}
    try:
        mongo_id = ObjectId(ctx.room.name)
        # print(f"User Id: {ctx.room.name}")
        prompt_data = prompt_collection.find_one(filter={
            "user" : mongo_id
        })
        user_data = user_collection.find_one(filter={
            "_id" : mongo_id
        })
    except Exception as e:
        print(f"Error fetching prompt data from MongoDB: {e}")
    system_prompt = f'''You are Vaanii, an AI language tutor designed to help learners improve their language skills through personalized, conversational practice. Adapt your teaching style, content, and interaction based on the learner's profile:
        * User Name: {user_data.get('fullname',"")}
        * Native Language: {prompt_data.get('nativeLanguage', 'English')}
        * Language Level: {prompt_data.get('languageLevel', 'Intermediate')}
        * Goal: {prompt_data.get('goal', 'Enhance fluency')}
        * Purpose: {prompt_data.get('purpose', 'Unknown')}
        * Time Dedication: {prompt_data.get('timeToBeDedicated', '5-15 minutes')}
        * Learning Pace: {prompt_data.get('learningPace', 'Moderate')}
        * Challenging Aspect: {prompt_data.get('challengingAspect', 'Fluency')}
        * Preferred Practice: {prompt_data.get('preferredPracticingWay', 'Unknown')}

        ## Interaction Guidelines
        1. Try to keep your response very short and concise.
        2. Engage in natural, conversational exchanges relevant to the learner's goals and interests.
        3. Adapt language complexity to match the learner's level. Gradually increase difficulty as they progress.
        4. Provide explanations and gentle corrections to help learners internalize new concepts.
        5. Encourage active participation through questions and prompts, and offer constructive feedback.
        6. Incorporate cultural insights and idiomatic expressions for a more authentic language understanding.
        7. Maintain a friendly, patient, and supportive demeanor, and adjust your approach as needed.
        8. Since you are a voice assistant, do not use special characters.

        Vaanii, please start the conversation by greeting the learner by there name and asking about their goals and interests. Make sure to adapt your interaction according to the provided profile.'''
    chat_context = ChatContext(
        messages=[
            ChatMessage(
                role="system",
                content=(system_prompt),
            )
        ]
    )


    azure_tts = TTS(
            voice='en-IN-AashiNeural',  
            language='en-IN',
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
    groq = openai.LLM.with_groq()
    latest_image: rtc.VideoFrame | None = None
    assistant = VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=stt,
        llm=groq,
        tts=deepgram_tts,
        chat_ctx=chat_context,
        before_tts_cb=replace_words,
    )

    chat = rtc.ChatManager(ctx.room)

    async def _answer(text: str, use_image: bool = False):
        """
        Answer the user's message with the given text and optionally the latest
        image captured from the video track.
        """
        content: list[str | ChatImage] = [text]
        if use_image and latest_image:
            content.append(ChatImage(image=latest_image))

        chat_context.messages.append(ChatMessage(role="user", content=content))
        stream = groq.chat(chat_ctx=chat_context)
        await assistant.say(stream, allow_interruptions=True)

    @chat.on("message_received")
    def on_message_received(msg: rtc.ChatMessage):
        """This event triggers whenever we get a new message from the user."""
        if msg.message:
            asyncio.create_task(_answer(msg.message, use_image=False))

    @assistant.on("function_calls_finished")
    def on_function_calls_finished(called_functions: list[agents.llm.CalledFunction]):
        """This event triggers when an assistant's function call completes."""

        if len(called_functions) == 0:
            return

        user_msg = called_functions[0].call_info.arguments.get("user_msg")
        if user_msg:
            asyncio.create_task(_answer(user_msg, use_image=True))

    assistant.start(ctx.room)

    await asyncio.sleep(1)

    await assistant.say("Hi, I am Vaanii", allow_interruptions=True)

    # async def on_user_speech_committed(transcript: str):
    #     print(f"User speech committed: {transcript}")
    # await assistant.on("user_speech_committed",on_user_speech_committed)
    

    # while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
    #     video_track = await get_video_track(ctx.room)
    #     async for event in rtc.VideoStream(video_track):
    #         latest_image = event.frame


def run_entrypoint(ctx):
        return entrypoint(ctx=ctx, client=client)

if __name__ == "__main__":
    client = initializeMongoClient()
    cli.run_app(WorkerOptions(entrypoint_fnc=run_entrypoint,load_threshold=0.98))
