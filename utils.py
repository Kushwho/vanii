from models import db, Event
from functools import wraps

def log_event(event_type, event_data):
    new_event = Event(event_type=event_type, event_data=event_data)
    db.session.add(new_event)
    db.session.commit()

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