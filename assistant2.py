import asyncio
import json
import re
import logging
import sys
from typing import Annotated, AsyncIterable, Optional
from bson.objectid import ObjectId
from dotenv import load_dotenv
from datetime import datetime

from livekit import rtc
from livekit.agents import (
    Agent, AgentSession, ChatContext, 
    JobContext, WorkerOptions, cli, function_tool, RunContext,
    BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip, tokenize, 
    ModelSettings
)
from livekit.plugins import silero
from livekit.plugins import openai
from livekit.plugins.deepgram import STT as DeepgramSTT
from livekit.plugins.deepgram import tts
from initializeClient import initializeMongoClient, initializeChromaClient
from livekit.plugins import groq
from livekit import api


load_dotenv()

# Configure logging
def setup_logging():
    """Configure logging with proper formatting and levels."""
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Optional: File handler for persistent logging
    try:
        file_handler = logging.FileHandler('vaanii_tutor.log')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create file handler: {e}")
    
    # Set specific logger levels
    logging.getLogger('pymongo').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('livekit').setLevel(logging.INFO)
    
    return logging.getLogger(__name__)

# Initialize logging
logger = setup_logging()

# Global clients for connection pooling
db_client = None
chroma_client = None

def get_mongo_client():
    global db_client
    if db_client is None:
        logger.info("Initializing MongoDB Client...")
        try:
            db_client = initializeMongoClient()
            logger.info("MongoDB Client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MongoDB Client: {e}")
            raise
    return db_client

def get_chroma_client():
    global chroma_client
    if chroma_client is None:
        logger.info("Initializing ChromaDB Client...")
        try:
            chroma_client = initializeChromaClient()
            logger.info("ChromaDB Client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB Client: {e}")
            raise
    return chroma_client

def replace_special_chars(text: str | AsyncIterable[str]):
    """Replace special characters that might cause issues in speech."""
    return tokenize.utils.replace_words(
        text=text,
        replacements={r'[^a-zA-Z0-9\s]': ''}
    )

class ChatHistoryManager:
    """Manages chat history loading with configurable message limits."""
    
    def __init__(self, session_collection, max_messages: int = 50):
        self.session_collection = session_collection
        self.max_messages = max_messages
        self.logger = logging.getLogger(f"{__name__}.ChatHistoryManager")
    
    async def load_latest_history(self, session_id: str, chat_context) -> bool:
        """
        Load latest chat history with comprehensive error handling.
        
        Args:
            session_id: MongoDB ObjectId as string
            chat_context: Chat context object to populate
            
        Returns:
            bool: True if history was loaded successfully, False otherwise
        """
        if not self._validate_session_id(session_id):
            return False
        
        try:
            self.logger.info(f"Loading latest {self.max_messages} messages for session {session_id}")
            
            # Database-level optimization using aggregation
            pipeline = [
                {"$match": {"_id": ObjectId(session_id)}},
                {"$project": {
                    "chatHistory": {"$slice": ["$chatHistory", -self.max_messages]},
                    "totalMessages": {"$size": {"$ifNull": ["$chatHistory", []]}},
                    "_id": 0
                }}
            ]
            
            result = list(self.session_collection.aggregate(pipeline))
            
            if not result:
                self.logger.warning(f"Session {session_id} not found in database")
                return False
            
            session_data = result[0]
            chat_history = session_data.get("chatHistory", [])
            total_messages = session_data.get("totalMessages", 0)
            
            if not chat_history:
                self.logger.info(f"No chat history found for session {session_id}")
                return True
            
            if total_messages > self.max_messages:
                self.logger.info(f"Loading latest {len(chat_history)} of {total_messages} total messages")
            else:
                self.logger.info(f"Loading all {len(chat_history)} messages")
            
            return self._load_messages_to_context(chat_history, chat_context)
            
        except Exception as e:
            self.logger.error(f"Error loading chat history for session {session_id}: {e}", exc_info=True)
            return False
    
    def _validate_session_id(self, session_id: str) -> bool:
        """Validate session ID format and presence."""
        if not session_id:
            self.logger.warning("No session ID provided")
            return False
        
        if not ObjectId.is_valid(session_id):
            self.logger.error(f"Invalid session ID format: {session_id}")
            return False
        
        return True
    
    def _load_messages_to_context(self, messages: list, chat_context) -> bool:
        """Load messages into chat context with validation."""
        success_count = 0
        
        for i, msg_data in enumerate(messages):
            try:
                if self._load_single_message(msg_data, chat_context):
                    success_count += 1
                else:
                    self.logger.warning(f"Failed to load message {i}: {msg_data}")
            except Exception as e:
                self.logger.error(f"Error processing message {i}: {e}", exc_info=True)
                continue
        
        self.logger.info(f"Successfully loaded {success_count}/{len(messages)} messages into chat context")
        return success_count > 0
    
    def _load_single_message(self, msg_data: dict, chat_context) -> bool:
        """Load a single message with validation."""
        role = msg_data.get("sender")
        content = msg_data.get("message")
        
        if not role:
            self.logger.debug("Skipping message: missing sender role")
            return False
        
        if content is None:
            self.logger.debug("Skipping message: missing content")
            return False
        
        # Validate role
        if role not in ["user", "assistant", "system"]:
            self.logger.warning(f"Unexpected role '{role}' in message")
            return False
        
        try:
            if isinstance(content, dict):
                chat_context.add_message(role=role, content=[content])
            elif isinstance(content, str):
                chat_context.add_message(role=role, content=content)
            elif isinstance(content, list):
                chat_context.add_message(role=role, content=content)
            else:
                self.logger.warning(f"Unexpected content format: {type(content)}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error adding message to context: {e}")
            return False

class VaaniiTutor(Agent):
    """Vaanii Tutor Agent with RAG capabilities for educational content."""
    
    def __init__(self, metadata=None, chroma_client=None, chat_ctx=None):
        self.metadata = metadata or {"subject": "Geography", "chapter": "Agriculture"}
        self.chroma_client = chroma_client
        self.logger = logging.getLogger(f"{__name__}.VaaniiTutor")
        
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
        self.logger.info(f"Retrieving context for query: {query}")
        
        # Send a verbal status update to the user after a short delay
        async def _speak_status_update(delay: float = 0.5):
            await asyncio.sleep(delay)
            await context.session.generate_reply(instructions="""
                You are retrieving information about this topic. 
                Tell the user "I am thinking" very briefly while you process this request.
            """)
        
        # Start the status update task
        status_update_task = asyncio.create_task(_speak_status_update(0.3))
        
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
                k=4,
                filter=metadata_filter
            )
            
            # Format the retrieved context
            if relevant_docs:
                context_content = "\n".join(
                    [f"Document excerpt: {doc.page_content}" 
                     for doc in relevant_docs]
                )
                result = f"Context: {context_content}"
                self.logger.info(f"Retrieved {len(relevant_docs)} relevant documents")
            else:
                self.logger.warning("No relevant documents found for query")
                
        except Exception as e:
            self.logger.error(f"Error retrieving context: {e}", exc_info=True)
        
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
    """Main entrypoint for the Vaanii Tutor agent."""
    logger.info("Starting Vaanii Tutor agent entrypoint")
    
    # Initialize database connections
    try:
        db_client = get_mongo_client()
        chroma_client = get_chroma_client()
        prompt_collection = db_client["VaniiWeb"]["onboardings"]
        user_collection = db_client["VaniiWeb"]["users"]
        session_collection = db_client["VaniiWeb"]["sessions"]
        logger.info("Database connections established successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database connections: {e}")
        raise
    
    # Configuration
    MAX_MESSAGES_TO_LOAD = 50  # Adjust as needed
    
    async def save_chat_history():
        """Save chat history to database on session end."""
        try:
            session_id = metadata.get("sessionId")
            
            if not session_id:
                logger.warning("No session ID found in metadata for saving chat history")
                return
            
            logger.info(f"Saving chat history for session {session_id}")
            
            # Get chat history from session
            chat_history_items = session.history.to_dict().get("items", [])
            
            chat_history = []
            for msg in chat_history_items:
                content = msg.get("content")
                role = msg.get("role", "")
                
                # Handle different content formats safely
                if content is None:
                    message = ""
                elif isinstance(content, list) and len(content) > 0:
                    message = content[0] if content[0] is not None else ""
                elif isinstance(content, str):
                    message = content
                else:
                    message = ""
                
                chat_history.append({
                    "message": message,
                    "sender": role,
                })
            
            # Update session status and endTime, and append new chat history
            update_data = {
                "status": "completed",
                "endTime": datetime.now()
            }

            # Use $push with $each to append new messages to existing chatHistory
            result = session_collection.update_one(
                {"_id": ObjectId(session_id)},
                {
                    "$set": update_data,
                    "$push": {
                        "chatHistory": {
                            "$each": chat_history
                        }
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Session {session_id} updated successfully with {len(chat_history)} messages")
            else:
                logger.warning(f"No changes made to session {session_id}")
                
        except Exception as e:
            logger.error(f"Error saving session data: {e}", exc_info=True)
    async def save_and_delete():
        await save_chat_history()
        api_client = api.LiveKitAPI()
        try:
            await api_client.room.delete_room(
            api.DeleteRoomRequest(room=ctx.room.name))
            logger.info(f"Room '{ctx.room.name}' deleted successfully")
        except Exception as e:
            logger.error(f"Failed to delete room '{ctx.room.name}': {e}")

    ctx.add_shutdown_callback(save_and_delete)
    
    # Connect to the room before doing any operations
    try:
        await ctx.connect()
        logger.info(f"Connected to room: {ctx.room.name}")
    except Exception as e:
        logger.error(f"Failed to connect to room: {e}")
        raise
    
    # Load user data and metadata
    prompt_data = {}
    user_data = {}
    session_data = {}
    metadata = {"subject": "Geography", "chapter": "Agriculture"}  # Default values
    
    try:
        if ctx.room.metadata:
            metadata = json.loads(ctx.room.metadata)
            logger.info(f"Loaded metadata: {metadata}")
        
        user_id = metadata.get("userId")
        if user_id:
            mongo_id = ObjectId(user_id)
            prompt_data = prompt_collection.find_one(filter={"user": mongo_id})
            user_data = user_collection.find_one(filter={"_id": mongo_id})
            
            if user_data:
                name = user_data.get('fullname', 'Unknown')
                logger.info(f"Loaded user data for: {name}")
            else:
                name = "Unknown"
                logger.warning(f"User data not found for user ID: {user_id}")
                
            if prompt_data:
                native_language = prompt_data.get('nativeLanguage', 'English')
                language_level = prompt_data.get('languageLevel', 'Intermediate')
                goal = prompt_data.get('goal', 'Enhance fluency')
                purpose = prompt_data.get('purpose', 'Unknown')
                time_dedication = prompt_data.get('timeToBeDedicated', '5-15 minutes')
                learning_pace = prompt_data.get('learningPace', 'Moderate')
                challenging_aspect = prompt_data.get('challengingAspect', 'Fluency')
                preferred_practicing_way = prompt_data.get('preferredPracticingWay', 'Unknown')
                logger.info("Loaded user prompt data successfully")
            else:
                # Default values
                native_language = "English"
                language_level = "Intermediate"
                goal = "Enhance fluency"
                purpose = "Unknown"
                time_dedication = "5-15 minutes"
                learning_pace = "Moderate"
                challenging_aspect = "Fluency"
                preferred_practicing_way = "Unknown"
                logger.warning(f"Prompt data not found for user ID: {user_id}, using defaults")
        else:
            # Default values when no user ID
            name = "Unknown"
            native_language = "English"
            language_level = "Intermediate"
            goal = "Enhance fluency"
            purpose = "Unknown"
            time_dedication = "5-15 minutes"
            learning_pace = "Moderate"
            challenging_aspect = "Fluency"
            preferred_practicing_way = "Unknown"
            logger.warning("No user ID found in metadata, using default values")
            
    except Exception as e:
        logger.error(f"Error fetching data from MongoDB: {e}", exc_info=True)
        # Use default values
        name = "Unknown"
        native_language = "English"
        language_level = "Intermediate"
        goal = "Enhance fluency"
        purpose = "Unknown"
        time_dedication = "5-15 minutes"
        learning_pace = "Moderate"
        challenging_aspect = "Fluency"
        preferred_practicing_way = "Unknown"

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

    logger.info("System prompt created successfully")

    # Initialize chat context with system prompt
    chat_context = ChatContext()
    chat_context.add_message(role="system", content=[system_prompt])
    
    # ---- LOAD CHAT HISTORY ----
    session_id = metadata.get("sessionId")
    if session_id:
        chat_manager = ChatHistoryManager(session_collection, max_messages=MAX_MESSAGES_TO_LOAD)
        history_loaded = await chat_manager.load_latest_history(session_id, chat_context)
        
        if history_loaded:
            logger.info("Chat history loaded successfully")
        else:
            logger.warning("Failed to load chat history or no history available")
    else:
        logger.warning("No session ID found in metadata, cannot load chat history")
    # ---- END LOAD CHAT HISTORY ----
    
    # Initialize speech recognition, text-to-speech, and LLM
    try:
        logger.info("Initializing AI models...")
        
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
        
        llm_engine = groq.LLM(
            model="llama3-8b-8192",
            temperature=0.7,
            parallel_tool_calls=True
        )
        
        logger.info("AI models initialized successfully")
        
    except ValueError as e:
        logger.error(f"Error initializing models: {e}")
        raise
    
    # Create the agent session
    try:
        session = AgentSession(
            stt=stt,
            llm=llm_engine,
            tts=tts_engine,
            vad=silero.VAD.load(),
        )
        logger.info("Agent session created successfully")
    except Exception as e:
        logger.error(f"Error creating agent session: {e}")
        raise
    
    # Create the tutor agent with RAG capabilities
    try:
        tutor = VaaniiTutor(
            metadata=metadata,
            chroma_client=chroma_client,
            chat_ctx=chat_context
        )
        logger.info("Vaanii Tutor agent created successfully")
    except Exception as e:
        logger.error(f"Error creating tutor agent: {e}")
        raise
    
    # Start the agent session
    try:
        await session.start(
            room=ctx.room,
            agent=tutor,
        )
        logger.info("Agent session started successfully")
    except Exception as e:
        logger.error(f"Error starting agent session: {e}")
        raise
    
    # Set up background "thinking" sound to play during tool calls
    try:
        background_audio = BackgroundAudioPlayer(
            thinking_sound=[
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.8),
                AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
            ],
        )
        await background_audio.start(room=ctx.room, agent_session=session)
        logger.info("Background audio player started successfully")
    except Exception as e:
        logger.error(f"Error starting background audio: {e}")
        # Non-critical error, continue without background audio

    async def process_message(message: str):
        """Process an incoming message from the user."""
        logger.info(f"Processing message: {message[:100]}...")  # Log first 100 chars
        try:
            await session.generate_reply(
                user_input=message,
                allow_interruptions=True,
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        """Handle participant disconnection and shutdown if room is empty."""
        logger.info(f"Participant {participant.identity} disconnected")
        
        # Check if there are any remaining participants (excluding the agent)
        remaining_participants = [p for p in ctx.room.remote_participants.values()]
        
        if len(remaining_participants) == 0:
            logger.info("No participants remaining, scheduling session shutdown...")
            # Schedule shutdown in the next event loop iteration
            asyncio.create_task(shutdown_session())

    async def shutdown_session():
        logger.info("Shutting down session due to no remaining participants")
        await asyncio.sleep(0.1)  # Small delay to ensure cleanup
        ctx.shutdown(reason="Session ended - no participants remaining")

    @session.on("function_calls_finished")
    def on_function_calls_finished(called_functions: list):
        """This event triggers when function calls complete."""
        logger.debug(f"Function calls finished: {len(called_functions)} functions called")
        
        if len(called_functions) == 0:
            return
            
        for function_call in called_functions:
            if function_call.name == "retrieve_context":
                # Get the context from the function result
                context = function_call.result
                # Get query from the function arguments
                query = function_call.call_info.arguments.get("query")
                
                logger.info(f"Context retrieved for query: {query}")
                
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
    try:
        await asyncio.sleep(1)  # Small delay to ensure everything is ready
        greeting_message = f"Hi, I am Vaanii, your tutor for your chapter {metadata['chapter']}."
        logger.info(f"Sending greeting: {greeting_message}")
        
        await session.say(
            greeting_message,
            allow_interruptions=True
        )
        
        logger.info("Agent initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Error sending greeting message: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info("Starting Vaanii Tutor application")
    
    # Initialize resources
    try:
        get_mongo_client()
        get_chroma_client()
        logger.info("Resources initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize resources: {e}")
        sys.exit(1)
    
    # Run the app
    try:
        cli.run_app(
            WorkerOptions(
                entrypoint_fnc=entrypoint,
                load_threshold=0.99,
            )
        )
    except Exception as e:
        logger.error(f"Application failed to start: {e}", exc_info=True)
        sys.exit(1)