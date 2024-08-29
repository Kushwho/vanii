from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSON, BYTEA
import datetime

db = SQLAlchemy()

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(255), nullable=False)
    event_data = db.Column(db.JSON, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

class AudioChunk(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(255), nullable=False)
    audio_data = db.Column(BYTEA, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.UTC)

    def __repr__(self):
        return f'<AudioChunk {self.id} for session {self.session_id}>'