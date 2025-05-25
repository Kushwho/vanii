import asyncio
import json
import re
from typing import Annotated, AsyncIterable, Optional
from bson.objectid import ObjectId
from dotenv import load_dotenv

from livekit import  rtc
from livekit.agents import (
    Agent, AgentSession, ChatContext, 
    JobContext, WorkerOptions, cli, function_tool, RunContext,
    BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip, tokenize, 
    ModelSettings
)
from livekit.plugins import silero
from livekit.plugins import  openai
from livekit.plugins.deepgram import STT as DeepgramSTT
from livekit.plugins.deepgram import tts
from initializeClient import initializeMongoClient, initializeChromaClient
from livekit.plugins import groq

load_dotenv()

# Global clients for connection pooling
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

def replace_special_chars(text: str | AsyncIterable[str]):
    """Replace special characters that might cause issues in speech."""
    return tokenize.utils.replace_words(
        text=text,
        replacements={r'[^a-zA-Z0-9\s]': ''}
    )

class VaaniiTutor(Agent):
    """Vaanii Tutor Agent with RAG capabilities for educational content."""
    
    def __init__(self, metadata=None, chroma_client=None, chat_ctx=None):
        self.metadata = metadata or {"subject": "Geography", "chapter": "Agriculture"}
        self.chroma_client = chroma_client
        super().__init__(
            chat_ctx=chat_ctx,
            instructions=f"You are Vaanii, an AI language tutor specialized in {self.metadata.get('subject')} with a focus on {self.metadata.get('chapter')}."
        )

    @function_tool()
    async def retrieve_context(
        self,
        context: RunContext,
        query: Annotated[
            str,
            "The user query to find relevant context for"
        ],
    ) -> str:
        """
        Called when needing to retrieve relevant context for a user query.
        This function will search for relevant content in the knowledge base
        and return it to enhance your responses.
        """
        # Send a verbal status update to the user after a short delay
        async def _speak_status_update(delay: float = 0.5):
            await asyncio.sleep(delay)
            await context.session.generate_reply(instructions="""
                You are retrieving information about this topic. 
                Tell the user "I am thinking" very briefly while you process this request.
            """)
        
        # Start the status update task
        status_update_task = asyncio.create_task(_speak_status_update(0.5))
        
        result = "Relevant context not found"
        
        try:
            # Define your metadata filter
            metadata_filter = {
                "$and": [
                    {"category": {"$eq": f"{self.metadata['subject']}"}},
                    {"chapter": {"$eq": f"{self.metadata['chapter']}"}},
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
        
        # Cancel the status update task if search completed before timeout
        status_update_task.cancel()
            
        return result
    
    # Override the tts_node to apply the replace_special_chars function
    async def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        """Process text through TTS with special character replacement."""
        
        # Apply special character replacement to the text
        async def process_text():
            async for chunk in text:
                # Apply the replacement function to each text chunk
                processed_chunk = re.sub(r'[^a-zA-Z0-9\s]', '', chunk)
                yield processed_chunk
        
        # Pass the processed text to the default TTS node
        async for frame in Agent.default.tts_node(self, process_text(), model_settings):
            yield frame

async def entrypoint(ctx: JobContext):
    # Initialize database connections
    db_client = get_mongo_client()
    chroma_client = get_chroma_client()
    prompt_collection = db_client["VaniiWeb"]["onboardings"]
    user_collection = db_client["VaniiWeb"]["users"]
    
    # Connect to the room before doing any operations
    await ctx.connect()
    print(f"Room name: {ctx.room.name}")
    print(ctx.room)
    # Load user data and metadata
    prompt_data = {}
    user_data = {}
    try:
        metadata = {"subject": "Geography", "chapter": "Agriculture"}
        if ctx.room.metadata:
            # print("Received metadata")
            metadata = json.loads(ctx.room.metadata)
            # print("-------------------")
            # print(metadata["userId"])
            # print(metadata["subject"])
            # print("-------------------")
            
            mongo_id = ObjectId(metadata["userId"])
            prompt_data = prompt_collection.find_one(filter={"user": mongo_id})
            user_data = user_collection.find_one(filter={"_id": mongo_id})
            if user_data :
                name = user_data.get('fullname', 'Unknown')
            else :
                name = "Unknown"
            if prompt_data :
                native_language = prompt_data.get('nativeLanguage', 'English')
                language_level = prompt_data.get('languageLevel', 'Intermediate')
                goal = prompt_data.get('goal', 'Enhance fluency')
                purpose = prompt_data.get('purpose', 'Unknown')
                time_dedication = prompt_data.get('timeToBeDedicated', '5-15 minutes')
                learning_pace = prompt_data.get('learningPace', 'Moderate')
                challenging_aspect = prompt_data.get('challengingAspect', 'Fluency')
                preferred_practicing_way = prompt_data.get('preferredPracticingWay', 'Unknown')
            else :
                native_language = "English"
                language_level = "Intermediate"
                goal = "Enhance fluency"
                purpose = "Unknown"
                time_dedication = "5-15 minutes"
                learning_pace = "Moderate"
                challenging_aspect = "Fluency"
                preferred_practicing_way = "Unknown"

                pass
    except Exception as e:
        print(f"Error fetching data from MongoDB: {e}")

    # Create the system prompt with user information
    system_prompt = f'''
    You are Vaanii, an AI language tutor specialized in {metadata.get("subject", "the subject")} with a focus on {metadata.get("chapter", "the chapter")}. Your role is to help learners improve their language skills through personalized, conversational practice. Adapt your teaching style, content, and interaction based on the learner's profile:

    - User Name: {name}
    - Native Language: {native_language}
    - Language Level: {language_level}
    - Goal: {goal}
    - Purpose: {purpose}
    - Time Dedication: {time_dedication}
    - Learning Pace: {learning_pace}
    - Challenging Aspect: {challenging_aspect}
    - Preferred Practice: {preferred_practicing_way}

    ## Retrieving Subject Knowledge
    When a student asks about specific educational material in {metadata.get("subject", "the subject")} ({metadata.get("chapter", "the chapter")}), retrieve the necessary context silently. Do not reveal technical details or any function IDs—instead, simply say "I am thinking" while processing the request and then say your answer.
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
    8. **Most Important: Keep responses very short and concise while maintaining clarity and engagement. Prioritize brevity at all times.**
    '''



    # Initialize chat context with system prompt
    chat_context = ChatContext()
    chat_context.add_message(role="system", content=[system_prompt])
    # Initialize speech recognition, text-to-speech, and LLM
    try:
        stt = DeepgramSTT(
            language="multi",
            model="nova-3",
            interim_results=True,
            smart_format=True,
            punctuate=True,
            filler_words=True,
            profanity_filter=False,
            energy_filter=True
        )
        tts_engine = tts.TTS(
            model="aura-asteria-en",
        )
        llm_engine = groq.LLM(model="llama3-8b-8192",temperature=0.7, parallel_tool_calls=True)
    except ValueError as e:
        print(f"Error initializing models: {e}")
        raise
    
    # Create the agent session
    session = AgentSession(
        stt=stt,
        llm=llm_engine,
        tts=tts_engine,
        vad=silero.VAD.load(),
    )
    
    # Create the tutor agent with RAG capabilities
    tutor = VaaniiTutor(
        metadata=metadata,
        chroma_client=chroma_client,
        chat_ctx=chat_context
    )
    
    # Start the agent session
    await session.start(
        room=ctx.room,
        agent=tutor,
    )
    
    # Set up background "thinking" sound to play during tool calls
    background_audio = BackgroundAudioPlayer(
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
        ],
    )
    await background_audio.start(room=ctx.room, agent_session=session)
    
    # Setup chat manager for text messages
    # chat = rtc.ChatManager(ctx.room)
    
    # @chat.on("message_received")
    # def on_message_received(msg: rtc.ChatMessage):
    #     """Handle incoming text messages."""
    #     if msg.message:
    #         # Process the incoming message
    #         asyncio.create_task(process_message(msg.message))
    
    async def process_message(message: str):
        """Process an incoming message from the user."""
        # Generate a reply using the LLM
        await session.generate_reply(
            user_input=message,
            allow_interruptions=True,
        )

    
    @session.on("function_calls_finished")
    def on_function_calls_finished(called_functions: list):
        """This event triggers when function calls complete."""

        print("Hello function cal finished")
        if len(called_functions) == 0:
            return
            
        for function_call in called_functions:
            if function_call.name == "retrieve_context":
                # Get the context from the function result
                context = function_call.result
                # Get query from the function arguments
                query = function_call.call_info.arguments.get("query")
                
                if context and query:
                    # Add the context to the chat context
                    chat_context.add_message(
                        role="assistant", 
                        content=[f"Additional information relevant to the query: {context}"]
                    )
                    # Generate a reply using the updated context
                    asyncio.create_task(session.generate_reply(
                        user_input=query,
                        allow_interruptions=True,
                    ))
    
    # Greet the user to start the conversation
    await asyncio.sleep(1)  # Small delay to ensure everything is ready
    await session.say(
        f"Hi, I am Vaanii, your tutor for your chapter {metadata['chapter']}.",
        allow_interruptions=True
    )

if __name__ == "__main__":
    # Initialize resources
    get_mongo_client()
    get_chroma_client()
    
    # Run the app
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            load_threshold=0.99,
        )
    )