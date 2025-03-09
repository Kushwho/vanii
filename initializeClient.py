from pymongo import MongoClient
from dotenv import load_dotenv
import os
import sys
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# Load environment variables from .env file
load_dotenv()

# Fetch the MongoDB URI from environment variable
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


def initializeChromaClient():
    """
    Initializes a Chroma DB client.
    Exits the application if the connection fails.
    """
    try:
        # Initialize embeddings for Chroma
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

        # Initialize Chroma client
        chroma_client = Chroma(
            persist_directory="./chroma_langchain_db",
            embedding_function=embeddings,
            collection_name="embeddings"
        )

        # Verify Chroma connection (optional)
        print("✅ Successfully connected to Chroma DB")
        return chroma_client

    except Exception as e:
        # Print the error and exit the app
        print(f"❌ Error connecting to Chroma DB: {e}")
        sys.exit(1)  # Exit the application with status code 1



