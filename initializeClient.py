from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()


URL = os.getenv("DB_URI")

def initializeMongoClient() :
    client = MongoClient(URL)
    return client