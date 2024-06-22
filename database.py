import logging
from app import db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)




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



