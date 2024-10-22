import asyncio
from typing import Annotated
from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import (
    ChatContext,
    ChatImage,
    ChatMessage,
)
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import deepgram, openai, silero,cartesia
from initializeClient import initializeMongoClient
from bson.objectid import ObjectId

try:
    client = initializeMongoClient()
    prompt_collection = client["VaniiWeb"]["onboardings"]
except Exception as e:
    print(f"Error initializing MongoDB client: {e}")
    raise

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




async def entrypoint(ctx: JobContext):
    await ctx.connect()
    print(f"Room name: {ctx.room.name}")
    prompt_data = {}
    try:
        mongo_id = ObjectId(ctx.room.name)
        print(f"User Id: {ctx.room.name}")
        prompt_data = prompt_collection.find_one(filter={
            "user" : mongo_id
        })
    except Exception as e:
        print(f"Error fetching prompt data from MongoDB: {e}")

    system_prompt = f'''You are Vanii, an AI language tutor designed to help learners improve their language skills through      personalized, conversational practice. Adapt your teaching style, content, and interaction based on the learner's profile :
            *Native Language*: {prompt_data.get('nativeLanguage', 'English')}
            *Language Level*: {prompt_data.get('languageLevel', 'Intermediate')}
            *Goal*: {prompt_data.get('goal', 'Enhance fluency')}
            *Purpose*: {prompt_data.get('purpose', 'Unknown')}
            *Time Dedication*: {prompt_data.get('timeToBeDedicated', '5-15 minutes')}
            *Learning Pace*: {prompt_data.get('learningPace', 'Moderate')}
            *Challenging Aspect*: {prompt_data.get('challengingAspect', 'Fluency')}
            *Preferred Practice*: {prompt_data.get('preferredPracticingWay', 'Unknown')}

            ## Interaction Guidelines
            1. Engage in natural, conversational exchanges relevant to the learner's goals and interests.
            2. Adapt language complexity to match the learner's level. Gradually increase difficulty as they progress.
            3. Provide explanations and gentle corrections to help learners internalize new concepts.
            4. Encourage active participation through questions and prompts, and offer constructive feedback.
            5. Incorporate cultural insights and idiomatic expressions for a more authentic language understanding.
            6. Maintain a friendly, patient, and supportive demeanor, and adjust your approach as needed.
            '''
    chat_context = ChatContext(
        messages=[
            ChatMessage(
                role="system",
                content=(system_prompt),
            )
        ]
    )

    groq = openai.LLM.with_groq()
    cartesia_tts = cartesia.TTS()
    latest_image: rtc.VideoFrame | None = None
    assistant = VoiceAssistant(
        vad=silero.VAD.load(), 
        stt=deepgram.STT(),  
        llm=groq,
        tts=cartesia_tts,  
        # fnc_ctx=AssistantFunction(),
        chat_ctx=chat_context,
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
        # print("Below is the text")
        # print(text)
        stream = groq.chat(chat_ctx=chat_context)
        # print("Below is the text")
        # print(stream)
        await assistant.say(stream, allow_interruptions=True)

    @chat.on("message_received")
    def on_message_received(msg: rtc.ChatMessage):
        """This event triggers whenever we get a new message from the user."""
        # print("Hello")
        # print(msg)
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
    await assistant.say("Hi..", allow_interruptions=True)
    # async def on_user_speech_committed(transcript: str):
    #     print(f"User speech committed: {transcript}")
    # await assistant.on("user_speech_committed",on_user_speech_committed)
    

    # while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
    #     video_track = await get_video_track(ctx.room)
    #     async for event in rtc.VideoStream(video_track):
    #         latest_image = event.frame


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
