import logging
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from config import Config
from models import db
from utils import log_event
from log_config import setup_logging
import os

load_dotenv()

app = Flask("app_http")
app.config.from_object(Config)
db.init_app(app)

def configure_app(use_cloudwatch):
    with app.app_context():
        db.create_all()
    
    # Set up logging
    logger = setup_logging(use_cloudwatch)
    
    # Configure Flask to use our logger
    app.logger.handlers = logger.handlers
    app.logger.setLevel(logger.level)

@app.route('/')
def index():
    app.logger.info('Index route accessed')
    log_event('page_view', {'page': 'index'})
    return render_template('index.html')

configure_app(use_cloudwatch=True)

if __name__ == '__main__':
    app.logger.info("Starting Flask server.")
    app.run()
