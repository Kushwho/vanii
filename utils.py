from models import db, Event
from functools import wraps
import logging

def log_event(event_type, event_data):
    try:
        new_event = Event(event_type=event_type, event_data=event_data)
        db.session.add(new_event)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Database error: {str(e)}")

def log_function_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        log_event('function_call', {
            'function_name': func.__name__,
            'module': func.__module__,
            'args': str(args),
            'kwargs': str(kwargs)
        })
        return func(*args, **kwargs)
    return wrapper

def store_audio_chunk(session_id, audio_data):
    try:
        with get_db() as db:
            new_chunk = AudioChunk(
                session_id=session_id,
                audio_data=audio_data,  # audio_data should already be in bytes
            )
            db.add(new_chunk)
            db.commit()
        
        log_event('audio_chunk_stored', {
            'session_id': session_id,
            'chunk_size': len(audio_data),
            'timestamp': datetime.utcnow().isoformat()
        })
        logging.info(f"Audio chunk stored for session {session_id}")
    except Exception as e:
        logging.error(f"Error storing audio chunk: {str(e)}")
        log_event('audio_chunk_error', {
            'session_id': session_id,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        })

def assign(sessionId) :
    pass