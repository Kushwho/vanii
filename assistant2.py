import asyncio
import json
import re
import logging
import sys
from typing import AsyncIterable
from bson.objectid import ObjectId
from dotenv import load_dotenv
from datetime import datetime

from livekit import rtc
from livekit.agents import (
    Agent, AgentSession, ChatContext,
    JobContext, WorkerOptions, cli,
    BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip, tokenize,
    ModelSettings
)
from livekit.plugins import silero

from livekit.plugins.deepgram import STT as DeepgramSTT
from livekit.plugins.deepgram import tts as deepgram_tts
from initializeClient import initializeMongoClient
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
    """Vaanii Tutor Agent for English language learning conversations."""

    def __init__(self, metadata=None, chat_ctx=None):
        self.metadata = metadata or {}
        self.logger = logging.getLogger(f"{__name__}.VaaniiTutor")

        super().__init__(
            chat_ctx=chat_ctx,
            instructions="You are Vaanii, an AI language tutor designed to help learners improve their English language skills through personalized, conversational practice."
        )


    
    # Override the tts_node to apply the replace_special_chars function
    # async def tts_node(
    #     self, text: AsyncIterable[str], model_settings: ModelSettings
    # ) -> AsyncIterable[rtc.AudioFrame]:
    #     """Process text through TTS with special character replacement."""
        
    #     # Apply special character replacement to the text
    #     async def process_text():
    #         async for chunk in text:
    #             # Apply the replacement function to each text chunk
    #             processed_chunk = re.sub(r'[^a-zA-Z0-9\s]', '', chunk)
    #             yield processed_chunk
        
    #     # Pass the processed text to the default TTS node
    #     async for frame in Agent.default.tts_node(self, process_text(), model_settings):
    #         yield frame

async def entrypoint(ctx: JobContext):
    """Main entrypoint for the Vaanii Tutor agent."""
    logger.info("Starting Vaanii Tutor agent entrypoint")
    
    # Initialize database connections
    try:
        db_client = get_mongo_client()
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
            session_id = ctx.room.name
            
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

                # Only add messages that are not empty and have a valid role
                if message and message.strip() and role:
                    chat_history.append({
                        "message": message.strip(),
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
    metadata = {}  # Default values
    
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
    system_prompt = f'''You are Vaanii, an AI language tutor designed to help learners improve their language skills through personalized, conversational practice. Adapt your teaching style, content, and interaction based on the learner's profile:
        * User Name: {name}
        * Native Language: {native_language}
        * Language Level: {language_level}
        * Goal: {goal}
        * Purpose: {purpose}
        * Time Dedication: {time_dedication}
        * Learning Pace: {learning_pace}
        * Challenging Aspect: {challenging_aspect}
        * Preferred Practice: {preferred_practicing_way}

        ## Interaction Guidelines
        1. Try to keep your response very short and concise.
        2. Engage in natural, conversational exchanges relevant to the learner's goals and interests.
        3. Adapt language complexity to match the learner's level. Gradually increase difficulty as they progress.
        4. Provide explanations and gentle corrections to help learners internalize new concepts.
        5. Encourage active participation through questions and prompts, and offer constructive feedback.
        6. Incorporate cultural insights and idiomatic expressions for a more authentic language understanding.
        7. Maintain a friendly, patient, and supportive demeanor, and adjust your approach as needed.
        8. Since you are a voice assistant, do not use special characters.

        Vaanii, please start the conversation by greeting the learner by their name and asking about their goals and interests. Make sure to adapt your interaction according to the provided profile.'''

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
        
        # TTS Configuration with Google TTS and Deepgram TTS fallback
        tts_engine = None

        # Try Google TTS first
        try:
            from livekit.plugins import google
            logger.info("Attempting to initialize Google TTS...")
            tts_engine = google.TTS(
                voice_name="en-IN-Chirp3-HD-Achernar",  # Use voice_name instead of voice
                language="en-IN",
                gender="female"
            )
            logger.info("✅ Google TTS initialized successfully")
        except Exception as e:
            logger.warning(f"❌ Google TTS initialization failed: {e}")
            logger.info("🔄 Falling back to Deepgram TTS...")

            # Fallback to Deepgram TTS
            try:
                tts_engine = deepgram_tts.TTS(
                    model="aura-asteria-en",
                )
                logger.info("✅ Deepgram TTS initialized successfully as fallback")
            except Exception as deepgram_error:
                logger.error(f"❌ Both Google TTS and Deepgram TTS failed to initialize!")
                logger.error(f"Google TTS error: {e}")
                logger.error(f"Deepgram TTS error: {deepgram_error}")
                raise Exception("No TTS engine could be initialized")

        # Log which TTS engine is being used
        if hasattr(tts_engine, '__class__'):
            tts_class_name = tts_engine.__class__.__name__
            if 'google' in tts_class_name.lower():
                logger.info("🎤 Using Google TTS for speech synthesis")
            elif 'deepgram' in tts_class_name.lower():
                logger.info("🎤 Using Deepgram TTS for speech synthesis")
            else:
                logger.info(f"🎤 Using {tts_class_name} for speech synthesis")
       
        
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
            tts=tts_engine,  # Use the initialized TTS engine (Google with Deepgram fallback)
            vad=silero.VAD.load(),
        )
        logger.info("Agent session created successfully")
    except Exception as e:
        logger.error(f"Error creating agent session: {e}")
        raise
    
    # Create the tutor agent
    try:
        tutor = VaaniiTutor(
            metadata=metadata,
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



    # Greet the user to start the conversation
    try:
        await asyncio.sleep(1)  # Small delay to ensure everything is ready
        greeting_message = f"Hi, I am Vaanii, your English language tutor."
        logger.info(f"Sending greeting: {greeting_message}")

        await session.say(
            greeting_message,
            allow_interruptions=True
        )

        logger.info("Agent initialization completed successfully")

    except Exception as e:
        logger.error(f"Error sending greeting message: {e}", exc_info=True)


def get_port():
    """Get port from environment variable or default to 8080."""
    import os
    return int(os.environ.get('PORT', 8080))


if __name__ == "__main__":
    logger.info("Starting Vaanii Tutor application")
    # Initialize resources

    port = get_port()
    logger.info(f"Using port: {port}")
    try:
        get_mongo_client()
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
                port=port
            )
        )
    except Exception as e:
        logger.error(f"Application failed to start: {e}", exc_info=True)
        sys.exit(1)