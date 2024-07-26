import logging
from app import db
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.messages import HumanMessage,AIMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

store = {}


def validate_session_id(sessionId):
    if not isinstance(sessionId, str) or not sessionId:
        raise ValueError("Invalid sessionId")

def validate_obj(obj):
    if not isinstance(obj, dict) or not obj:
        raise ValueError("Invalid message object")

def store_history(sessionId, obj):
    try:
        
        validate_session_id(sessionId)
        validate_obj(obj)

        doc = db.chat_history.find_one({"sessionId": sessionId})

        if doc:
            db.chat_history.update_one(
                {"sessionId": sessionId},
                {"$push": {"messages": obj}}
            )
            logger.info(f"Updated chat history for sessionId: {sessionId}")
        else:
            db.chat_history.insert_one({
                "sessionId": sessionId,
                "messages": [obj]
            })
            logger.info(f"Inserted new chat history for sessionId: {sessionId}")
    except ValueError as ve:
        logger.error(f"Validation error: {ve}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")

def get_session_history(session_id:str)->BaseChatMessageHistory:
    if session_id not in store:
        store[session_id]=ChatMessageHistory()
    return store[session_id]

def save_history_and_clear_store(sessionId):
    pass