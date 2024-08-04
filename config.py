import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_POOL_PRE_PING = True  # Enable pre-ping on connections
    SQLALCHEMY_POOL_RECYCLE = 600    # Recycle connections after 300 seconds

    @staticmethod
    def init_app(app):
        # Create the SQLAlchemy engine with pre-ping and recycle settings
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 600
        }
