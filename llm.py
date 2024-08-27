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

redis_client = redis.Redis(host="redis",port=6379,db=0)
mongo_client = MongoClient(host=os.getenv("DB_URI"))
db = mongo_client.get_database('VaniiHistory')
collection = db.get_collection('chatHistory')

redis_len = {}

def save_in_mongo_clear_redis(session_id: str):
    try:
        starttime = time.time()
        key = f"message_store:{session_id}"
        length = redis_client.llen(key)
        new_messages_count = length - redis_len.get(session_id, 0)
        print(f"New Messages count {new_messages_count}")
        if new_messages_count <= 0:
            logging.info(f"No new messages to save for session_id: {session_id}")
            return
        
        new_messages = redis_client.lrange(key, 0, new_messages_count - 1)
        new_messages.reverse()
        
        new_messages = [msg.decode('utf-8') for msg in new_messages]
        
        collection.update_one(
            {"session_id": session_id},
            {"$push": {"messages": {"$each": new_messages}}},
            upsert=True
        )
        
        # Update the redis_len dictionary with the new length
        redis_len[session_id] = length
        redis_client.delete(key)
        logging.info(f"Saved {new_messages_count} new messages for session_id: {session_id}")
        logging.info(f"It took {time.time() - starttime} seconds for save_in_mongo_clear_redis")
    except Exception as e:
        logging.error(f"Error during saving history in mongo: {e}")


def store_in_redis(session_id: str):
    try:
        key = f"message_store:{session_id}"
        length = redis_client.llen(key)
        print("redis_len from store in redis")
        print(redis_len)
        redis_len[session_id] = length
        if redis_client.exists(key):
            logging.info(f"Messages already exist for session_id: {session_id}")
            return
        
        starttime = time.time()
        document = collection.find_one(
            {"session_id": session_id},
            {"messages": {"$slice": -10}}
        )
        if not document or not document.get('messages'):
            logging.info(f"No messages found for session_id: {session_id}")
            return
        
        for message in document['messages']:
            redis_client.lpush(key, message.encode('utf-8'))
        
        
        logging.info(f"Latest 10 messages for session_id: {session_id} filled into Redis.")
        logging.info(f"It took {time.time() - starttime} seconds for store_in_redis")
    except Exception as e:
        logging.error(f"Error during saving history in redis: {e}")

    
load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")

CONNECTION_STRING = os.getenv("DB_URI")

model = ChatGroq(temperature=0.5, model_name="llama3-8b-8192", groq_api_key=groq_api_key,max_tokens=200)
system = '''You are Vaanii, act like  a Language Teacher with a vibrant personality, dedicated to making learning English fun and engaging and try to keep your reponses short.'''


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
        session_id, url="redis://redis:6379"
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


def streaming(session_id,transcript):
    try : 
        starttime = time.time()
        config = {"configurable": {"session_id": session_id}}
        for chunk in chain_with_history.stream({"question" : transcript},config=config) :
            yield(chunk)
        # print(f"It took {time.time()-starttime} seconds for llm response")
        logging.info(f"It took {time.time()-starttime} seconds for llm response")
    except Exception as e :
        logging.error(f"Error in generating response {e}")
        return "Sorry , there is some error"

# if __name__ == "__main__" :
#     print(batch("1","Tell me a poem on the moon"))
#     for chunk in streaming("1","Tell me a poem on the moon") :
#         print(chunk.content,end=" ")

    
    
