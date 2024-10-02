from langchain_core.prompts import ChatPromptTemplate,MessagesPlaceholder
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
import time
import logging
# from langchain_redis import RedisChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.messages import trim_messages
import redis
from pymongo import MongoClient
import os
from langchain_community.chat_message_histories.redis import RedisChatMessageHistory


load_dotenv()

CONNECTION_STRING = os.getenv("DB_URI")

redis_client = redis.Redis(host="redis",port=6379,db=0)
mongo_client = MongoClient(host=CONNECTION_STRING)
db = mongo_client.get_database('VaniiHistory')
collection = db.get_collection('chatHistory')
db2 = mongo_client.get_database('VaniiWeb')
collection2 = db2.get_collection('onboardings')

groq_api_key = os.getenv("GROQ_API_KEY")


chains = {}


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
        # print("redis_len from store in redis")
        # print(redis_len)
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


def extract_prompt_and_create_chain(session_id: str):
    try:
        # Extraction of prompt from MongoDB
        prompt_data = collection2.find_one({"user": session_id})

        # Default system prompt
        default_system_prompt = '''You are Vaani - a Voice-Based Conversational AI. Act like an Expert Language Teacher with a vibrant personality, 
        dedicated to making learning English fun and engaging. Keep your responses short, sweet, and specific.
        -> Be chatty enough to keep the conversation flowing, as the user is trying to improve.
        -> Be empathetic towards the user. Handle any incompleteness or confusion with care.
        *Do not use special characters or capital words, and maintain appropriate punctuation.*'''

        # Form the prompt based on user data if available
        if prompt_data:
            system_prompt = f'''You are an AI language tutor designed to help learners improve their language skills through      personalized, conversational practice. Adapt your teaching style, content, and interaction based on the learner's profile :
            *Native Language*: {prompt_data.get('nativeLanguage', 'English')}
            *Language Level*: {prompt_data.get('languageLevel', 'Intermediate')}
            *Goal*: {prompt_data.get('goal', 'Enhance fluency')}
            *Purpose*: {prompt_data.get('purpose', 'Unknown')}
            *Time Dedication*: {prompt_data.get('timeToBeDedicated', '5-15 minutes')}
            *Learning Pace*: {prompt_data.get('learningPace', 'Moderate')}
            *Challenging Aspect*: {prompt_data.get('challengingAspect', 'Fluency')}
            *Preferred Practice*: {prompt_data.get('preferredPracticingWay', 'Unknown')}

            ## Interaction Guidelines
            1. Engage in natural, conversational exchanges relevant to the learner's goals and interests.
            2. Adapt language complexity to match the learner's level. Gradually increase difficulty as they progress.
            3. Provide explanations and gentle corrections to help learners internalize new concepts.
            4. Encourage active participation through questions and prompts, and offer constructive feedback.
            5. Incorporate cultural insights and idiomatic expressions for a more authentic language understanding.
            6. Maintain a friendly, patient, and supportive demeanor, and adjust your approach as needed.
            '''
        else:
            system_prompt = default_system_prompt

        # Create model and chain components
        model = ChatGroq(temperature=0.5, model_name="llama3-8b-8192", groq_api_key=groq_api_key, max_tokens=200)
        trimmer = trim_messages(
            max_tokens=1200,
            strategy="last",
            token_counter=model,
            include_system=True,
            allow_partial=False,
            start_on="human"
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
                ("human", "{question}")
            ]
        )

        # Combine the components into a chain
        chain = prompt | trimmer | model
        chain_with_history = RunnableWithMessageHistory(
            chain,
            lambda session_id: RedisChatMessageHistory(
                session_id, url="redis://redis:6379"
            ),
            input_messages_key="question",
            history_messages_key="messages",
        )

        # Store the chain in the global chains dictionary
        chains[session_id] = chain_with_history

    except Exception as e:
        # Handle errors by assigning default chain
        logging.error(f"Error in extracting prompt and chain creation: {e}")
        # Fallback to default chain creation
        fallback_chain_creation(session_id, default_system_prompt)


def fallback_chain_creation(session_id: str, system_prompt: str):
    """Helper function to create a default chain when an error occurs."""
    try:
        model = ChatGroq(temperature=0.5, model_name="llama3-8b-8192", groq_api_key=groq_api_key, max_tokens=200)
        trimmer = trim_messages(
            max_tokens=1200,
            strategy="last",
            token_counter=model,
            include_system=True,
            allow_partial=False,
            start_on="human"
        )
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="messages"),
                ("human", "{question}")
            ]
        )

        # Create fallback chain
        chain = prompt | trimmer | model
        chain_with_history = RunnableWithMessageHistory(
            chain,
            lambda session_id: RedisChatMessageHistory(
                session_id, url="redis://redis:6379"
            ),
            input_messages_key="question",
            history_messages_key="messages",
        )

        # Store the fallback chain
        chains[session_id] = chain_with_history

    except Exception as e:
        logging.error(f"Error in creating fallback chain: {e}")


def delete_chain(session_id: str):
    """Safely delete a session's chain."""
    try:
        if session_id in chains:
            del chains[session_id]
    except Exception as e:
        logging.error(f"Error in deleting chain for session {session_id}: {e}")


    
def streaming(session_id,transcript):
    try : 
        starttime = time.time()
        config = {"configurable": {"session_id": session_id}}
        chain_with_history = chains[session_id]
        for chunk in chain_with_history.stream({"question" : transcript},config=config) :
            yield(chunk)
        # print(f"It took {time.time()-starttime} seconds for llm response")
        logging.info(f"It took {time.time()-starttime} seconds for llm response")
    except Exception as e :
        logging.error(f"Error in generating response {e}")
        return "Sorry , there is some error"
    
def streaming2(session_id,transcript):
    try :
        starttime = time.time()
        config = {"configurable": {"session_id": session_id}}
        response = ""
        chain_with_history = chains[session_id]
        for chunk in chain_with_history.stream({"question" : transcript},config=config) :
            response += chunk.content
            yield(chunk)
        # print(f"It took {time.time()-starttime} seconds for llm response")
        logging.info(f"It took {time.time()-starttime} seconds for llm response")
        return response
    except Exception as e :
        logging.error(f"Error in generating response {e}")
        return "Sorry , there is some error"
    

def batch(session_id,input):
    try : 
        starttime = time.time()
        config = {"configurable": {"session_id": session_id}}
        chain_with_history = chains[session_id]
        response = chain_with_history.invoke({"question" : input},config=config)
    
        logging.info(f"It took {time.time()-starttime} seconds for llm response")
        return response.content
    except Exception as e :
        logging.error(f"Error in generating response {e}")
        return "Sorry , there is some error"

# if __name__ == "__main__" :
#     print(batch("1","Tell me a poem on the moon"))
#     for chunk in streaming("1","Tell me a poem on the moon") :
#         print(chunk.content,end=" ")

    
    
