# import logging

# from dotenv import load_dotenv
# from flask import Flask, render_template

# load_dotenv()

# app = Flask("app_http")


# @app.route('/')
# def index():
#     return render_template('index.html')

import logging
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
import os

load_dotenv()

from flask import Flask
from flask_pymongo import PyMongo

app = Flask("app_http")
app.config["MONGO_URI"] = os.getenv("DB_URI")
mongo = PyMongo(app)

print(mongo)

@app.route('/')
def index():
    return render_template('index.html')

def save_to_database():
    pass

if __name__ == '__main__':
    logging.info("Starting Flask server.")
    # Run flask app
    app.run(debug=True, port=8000)
