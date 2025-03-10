import asyncio
from typing import Annotated, AsyncIterable
from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import (
    ChatContext,
    ChatMessage,
)
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import  silero
from livekit.plugins.openai import llm
from livekit.plugins.deepgram import STT as DeepgramSTT
from initializeClient import initializeMongoClient,initializeChromaClient
from bson.objectid import ObjectId
from livekit.plugins.azure import TTS
from livekit.plugins.deepgram import tts
from livekit.agents import tokenize
from dotenv import load_dotenv
import json


load_dotenv()


db_client = None
chroma_client = None



def get_mongo_client():
    global db_client
    if db_client is None:
        print("✅ Initializing MongoDB Client...")
        db_client = initializeMongoClient()
    return db_client



def get_chroma_client():
    global chroma_client
    if chroma_client is None:
        print("✅ Initializing ChromaDB Client...")
        chroma_client = initializeChromaClient()
    return chroma_client

class AssistantFunction(agents.llm.FunctionContext):
    """This class is used to define functions that will be called by the assistant."""

    def __init__(self,metadata={"subject":"Geography", "chapter" : "Agriculture"},chroma_client=None) :
        super().__init__()
        self.metadata = metadata
        self.chroma_client = chroma_client


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
        print(f"Retrieving context for: {query}")
        print(self.metadata)
        # Indicate thinking to the user
        result = "Relevant context not found"
        
        try:
            # Define your metadata filter
            metadata_filter = {
                "$and": [
                    {"category": {"$eq": f"{self.metadata['subject']}"}},
                    {"chapter": {"$eq": f"{self.metadata['chapter']}"}}
                ]
            }
            
            # Retrieve relevant documents
            relevant_docs = self.chroma_client.similarity_search(
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
                result = f"Context: {context_content}"
                
        except Exception as e:
            print(f"Error retrieving context: {e}")
            
        return result


def replace_words(assistant: VoicePipelineAgent, text: str | AsyncIterable[str]):
    return tokenize.utils.replace_words(
        text=text,
        replacements={r'[^a-zA-Z0-9\s]': ''}
    )



async def entrypoint(ctx: JobContext):
    db_client = get_mongo_client()
    chroma_client = get_chroma_client()
    prompt_collection = db_client["VaniiWeb"]["onboardings"]
    user_collection = db_client["VaniiWeb"]["users"]
    await ctx.connect()
    print(f"Room name: {ctx.room.name}")
    prompt_data = {}
    user_data = {}
    try:
        metadata={"subject":"Geography", "chapter" : "Agriculture"}
        if ctx.room.metadata :
            print("Received metadata")
            print(ctx.room.metadata)
            metadata = json.loads(ctx.room.metadata)
            print("-------------------")
            print(metadata["userId"])
            print(metadata["subject"])
            print("-------------------")
        mongo_id = ObjectId(metadata["userId"])
        # print(f"User Id: {ctx.room.name}")
        prompt_data = prompt_collection.find_one(filter={
            "user" : mongo_id
        })
        user_data = user_collection.find_one(filter={
            "_id" : mongo_id
        })
    except Exception as e:
        print(f"Error fetching prompt data from MongoDB: {e}")

    system_prompt = f'''
        You are Vaanii, an AI language tutor specialized in {metadata.get("subject", "the subject")} with a focus on {metadata.get("chapter", "the chapter")}. Your role is to help learners improve their language skills through personalized, conversational practice. Adapt your teaching style, content, and interaction based on the learner’s profile:

        - User Name: {user_data.get('fullname', 'Unknown')}
        - Native Language: {prompt_data.get('nativeLanguage', 'English')}
        - Language Level: {prompt_data.get('languageLevel', 'Intermediate')}
        - Goal: {prompt_data.get('goal', 'Enhance fluency')}
        - Purpose: {prompt_data.get('purpose', 'Unknown')}
        - Time Dedication: {prompt_data.get('timeToBeDedicated', '5-15 minutes')}
        - Learning Pace: {prompt_data.get('learningPace', 'Moderate')}
        - Challenging Aspect: {prompt_data.get('challengingAspect', 'Fluency')}
        - Preferred Practice: {prompt_data.get('preferredPracticingWay', 'Unknown')}

        ## Retrieving Subject Knowledge
        When a student asks about specific educational material in {metadata.get("subject", "the subject")} ({metadata.get("chapter", "the chapter")}), retrieve the necessary context silently. Do not reveal technical details or any function IDs—instead, simply say “I am thinking” while processing the request and then say your answer.
        - For subject-specific details: Always retrieve the required context.
        - For general conversations: Respond naturally without retrieving additional context.
        - For unclear queries: Ask clarifying questions first, then retrieve context if needed.

        ## Interaction Guidelines
        1. Engage in natural, conversational exchanges that align with the learner's goals and interests.
        2. Adapt language complexity to match the learner's level and gradually increase difficulty.
        3. Provide clear explanations and gentle corrections to help learners internalize new concepts.
        4. Encourage active participation with questions, prompts, and constructive feedback.
        5. Incorporate cultural insights and idiomatic expressions for a more authentic learning experience.
        6. Maintain a friendly, patient, and supportive demeanor, adjusting your approach as needed.
        7. As a voice assistant, avoid using special characters.
        8. Keep responses short and concise while maintaining clarity and engagement.
        '''


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
            model="nova-2",
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
    
    groq = llm.LLM.with_groq(temperature=0.7,parallel_tool_calls=True)

    
    
    # Create the function context with our tools
    fnc_ctx = AssistantFunction(metadata,chroma_client)
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

    

    async def _answer(text: str,context=None):
        """
        Answer the user's message with the given text and optionally the context provided.
        """
        
        
        content: list[str] = [text]

        chat_context.messages.append(ChatMessage(role="user", content=content))
        if context:
            chat_context.messages.append(ChatMessage(role="tool", content=f"Context: {context}"))
        # Now get the full response from the LLM (which might use the retrieve_context function)
        stream = groq.chat(chat_ctx=chat_context,temperature=0.7)
        await assistant.say(stream, allow_interruptions=True)

    @chat.on("message_received")
    def on_message_received(msg: rtc.ChatMessage):
        """This event triggers whenever we get a new message from the user."""
        if msg.message :
            asyncio.create_task(_answer(msg.message))

    @assistant.on("function_calls_finished")
    def on_function_calls_finished(called_functions: list[agents.llm.CalledFunction]):
        """This event triggers when an assistant's function call completes."""
        print("I have been called")
        if len(called_functions) == 0:
            return

        user_msg = called_functions[0].call_info.arguments.get("user_msg")
        context = called_functions[0].result
        # print(context)
        if user_msg:
            asyncio.create_task(_answer(user_msg,context=context))

    assistant.start(ctx.room)
    await asyncio.sleep(1)
    await assistant.say(f"Hi, I am Vaanii, your tutor for your chapter {metadata["chapter"]}.", allow_interruptions=True)

if __name__ == "__main__":
    get_mongo_client()
    get_chroma_client()

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            load_threshold=0.99
        )
    )

