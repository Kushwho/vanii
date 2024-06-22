import logging
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
from flask_pymongo import PyMongo
import os


load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)


app = Flask("app_http")
app.config["MONGO_URI"] = os.getenv("DB_URI")
mongo = PyMongo(app)
db = mongo.db


logging.info("MongoDB URI: %s", os.getenv("DB_URI"))

@app.route('/')
def index():
    logging.info("Rendering index page.")
    return render_template('index.html')



if __name__ == '__main__':
    logging.info("Starting Flask server.")
   
    app.run(debug=True, port=8000)
