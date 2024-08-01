import logging
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from config import Config
from models import db
from utils import log_event
import os
from log_config import logger
load_dotenv()

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s [%(levelname)s] %(message)s',
#     handlers=[
#         logging.FileHandler("app.log"),
#         logging.StreamHandler()
#     ]
# )

app = Flask("app_http")
app.config.from_object(Config)
db.init_app(app)


with app.app_context():
    db.create_all()

logging.info("MongoDB URI: %s", os.getenv("DB_URI"))

@app.route('/')
def index():
    logger.info('Index route accessed')
    log_event('page_view', {'page': 'index'})
    return render_template('index.html')



if __name__ == '__main__':
    logging.info("Starting Flask server.")
   
    app.run(debug=True, port=8000)
