from langchain_core.prompts import ChatPromptTemplate,MessagesPlaceholder
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
import time
import logging
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_core.messages import trim_messages
import redis
from pymongo import MongoClient
import os


load_dotenv()



redis_client = redis.Redis(host="localhost",port=6379,db=0)
mongo_client = MongoClient(host=os.getenv("DB_URI"))
db = mongo_client.get_database('VaniiHistory')
collection = db.get_collection('chatHistory')



def save_in_mongo_clear_redis(session_id : str) :
    try :
        starttime = time.time()
        key = f"message_store:{session_id}"
        messages = redis_client.lrange(key,0,-1)
        if not messages : 
            logging.info(f"No messages found for session_id: {session_id}")
            return
        messages = [msg.decode('utf-8') for msg in messages]
        messages.reverse()
        document = {
            "session_id" : session_id,
            "messages" : messages
        }
        collection.insert_one(document)
        redis_client.delete(key)
        logging.info(f"It took {time.time()-starttime} seconds for save_in_mongo_clear_redis")
    except Exception as e:
        logging.error(f"Error during saving history in mongo and clearing redis {e}")
     

def store_in_redis(session_id: str):
    try:
        key = f"message_store:{session_id}"
        if redis_client.exists(key) : 
            logging.info(f"Messages already exist for session_id: {session_id}")
            return
        starttime = time.time()
        # Retrieve all documents with the given session_id
        documents = collection.find({"session_id": session_id})
        
        # Combine all messages from the documents
        all_messages = []
        for document in documents:
            messages = document.get("messages", [])
            all_messages.extend(messages)

        if not all_messages:
            logging.info(f"No messages found for session_id: {session_id}")
            return

        # Fill Redis with messages
        
        for message in all_messages:
            redis_client.rpush(key, message)
        
        logging.info(f"Messages for session_id: {session_id} filled into Redis.")
        logging.info(f"It took {time.time()-starttime} seconds for store_in_redis")
    except Exception as e:
        logging.error(f"Error during saving history in redis: {e}")

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")

CONNECTION_STRING = os.getenv("DB_URI")

model = ChatGroq(temperature=0.5, model_name="llama3-8b-8192", groq_api_key=groq_api_key,max_tokens=300)
system = '''You are Vanii, act like  a Language Teacher with a vibrant personality, dedicated to making learning English fun and engaging and try to keep your reponses short.'''


trimmer=trim_messages(
    max_tokens=500,
    strategy="last",
    token_counter=model,
    include_system=True,
    allow_partial=False,
    start_on="human"
)

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        MessagesPlaceholder(variable_name="messages"),
        ("human", "{question}"),
    ]
)

chain = prompt | trimmer | model


chain_with_history = RunnableWithMessageHistory(
    chain,
    lambda session_id: RedisChatMessageHistory(
        session_id, url="redis://localhost:6379"
    ),
    input_messages_key="question",
    history_messages_key="messages",
)

def batch(session_id,input):
    try : 
        starttime = time.time()
        config = {"configurable": {"session_id": session_id}}
        response = chain_with_history.invoke({"question" : input},config=config)
        logging.info(f"It took {time.time()-starttime} seconds for llm response")
        return response.content
    except Exception as e :
        logging.error(f"Error in generating response {e}")
        return "Sorry , there is some error"


def streaming(session_id,input):
    try : 
        starttime = time.time()
        config = {"configurable": {"session_id": session_id}}
        for chunk in chain_with_history.stream({"question" : input},config=config) :
            yield(chunk)
            i+=1
        logging.info(f"It took {time.time()-starttime} seconds for llm response")
    except Exception as e :
        logging.error(f"Error in generating response {e}")
        return "Sorry , there is some error"

# if __name__ == "__main__" :
#     # print(batch("1","Hello , How are you?"))
#     for chunk in streaming("1","Hello, How are you?") :
#         print(chunk.content,end=" ")

    
    