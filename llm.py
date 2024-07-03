from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
from database import store_history
from app import mongo
import time
import logging

load_dotenv()

chat = ChatGroq(temperature=0, model_name="llama3-8b-8192", groq_api_key=os.getenv("GROQ_API_KEY"))
system = '''You are Vanii, a "World Class Language Teacher" with a vibrant personality, dedicated to making learning English fun and engaging and keep your responses short.

Example Interactions:

User: "How do you pronounce 'environment'?"

Vanii: "Absolutely! The pronunciation of 'environment' is en-vy-ron-ment. Let's break it down together: en-vy-ron-ment. Fantastic job! Ready to tackle another word?"

User: "Can you explain the difference between 'your' and 'you're'?"

Vanii: "Of course! 'Your' is possessive, like in 'your book'. 'You're' is a contraction of 'you are', as in 'you're doing awesome'. Try using each one in a sentence. You're doing brilliantly! Need more clarification?"

User: "What's the pronunciation of 'accessibility'?"

Vanii: "Great choice! 'Accessibility' is pronounced ak-sess-i-bil-i-ty. Let's break it down step by step: ak-sess-i-bil-i-ty. Keep practicing, you're doing wonderfully! Any other words you're curious about?"'''
# human = "{text}"
# prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
# chain = prompt | chat

# chat_history = []  # Initialize chat history
# system = "You! are  Vanii, a helpful assistant. Give reply in hinglish language"


def batch(sessionId,input):
    # global chat_history
    # sessionId = "1"
    # chat_history.append({"role": "human", "content": input})
    try : 
        starttime = time.time()
        store_history(sessionId,{"role": "human", "content": input})
        chat_history = mongo.db.chat_history.find_one(
        {"sessionId": sessionId})["messages"]
        # print(chat_his)

        # Prepare the chat history for the model
        history_for_prompt = [("system", system)] + [(entry["role"], entry["content"]) for entry in chat_history]
        prompt_with_history = ChatPromptTemplate.from_messages(history_for_prompt)

        # Generate response
        data = (prompt_with_history | chat).invoke({"text": input})
        
        # Append assistant response to chat history
        # chat_history.append({"role": "assistant", "content": data.content})
        store_history("1",{"role": "assistant", "content": data.content})
        endtime = time.time() - starttime
        logging.info(f"It took {endtime} seconds for generating responses.")
        return data.content
    except Exception as e :
        logging.error(f"Error in generating response {e}")
        return "Sorry , there is some error"


# def streaming(sessionId,input):
#     store_history(sessionId,{"role": "human", "content": input})
#     chat_history = mongo.db.chat_history.find_one(
#     {"sessionId": sessionId})["messages"]
#     # print(chat_his)

#     # Prepare the chat history for the model
#     history_for_prompt = [("system", system)] + [(entry["role"], entry["content"]) for entry in chat_history]
#     prompt_with_history = ChatPromptTemplate.from_messages(history_for_prompt)
#     chain = prompt_with_history | chat
    
    