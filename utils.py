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


def assign(sessionId) :
    pass