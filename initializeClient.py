from pymongo import MongoClient
from dotenv import load_dotenv
import os
import sys

load_dotenv()


DB_URI = os.getenv("DB_URI")

def initializeMongoClient():
    """
    Initializes a MongoDB client.
    Exits the application if the connection fails.
    """
    try:
        # Attempt to connect to MongoDB
        client = MongoClient(DB_URI)
        # Verify the connection
        client.admin.command('ping')
        print("✅ Successfully connected to MongoDB")
        return client
    except Exception as e:
        # Print the error and exit the app
        print(f"❌ Error connecting to MongoDB: {e}")
        sys.exit(1)  # Exit the application with status code 1