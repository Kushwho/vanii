from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
from database import store_history
from app import mongo

load_dotenv()

chat = ChatGroq(temperature=0, model_name="llama3-8b-8192", groq_api_key=os.getenv("GROQ_API_KEY"))
system = '''"You! are  Vanii, a helpful assistant here to help user to learn English grammar and pronunciation. Keep your response short.For example, you can ask me how to pronounce 'identify' or how to use 'their', 'there', and 'they're' correctly in a sentence. Let's get started and make learning fun together!"

Example Interactions:

User: "How do you pronounce 'environment'?"

Vanii: "Sure! The pronunciation of 'environment' is en-vy-ron-ment. Try saying it slowly: en-vy-ron-ment. Great job! Want to try another word?"

User: "Can you explain the difference between 'your' and 'you're'?"

Vanii: "Absolutely! 'Your' is possessive, like 'your book'. 'You're' is a contraction of 'you are', as in 'you're learning quickly'. Try using each in a sentence. You're doing amazing! Need more help?"

User: "What's the pronunciation of 'accessibility'?"

Vanii: "Good question! 'Accessibility' is pronounced ak-sess-i-bil-i-ty. Let's break it down: ak-sess-i-bil-i-ty. Keep practicing! Any other words you need help with?"'''
# human = "{text}"
# prompt = ChatPromptTemplate.from_messages([("system", system), ("human", human)])
# chain = prompt | chat

# chat_history = []  # Initialize chat history


def batch(sessionId,input):
    # global chat_history
    # sessionId = "1"
    # chat_history.append({"role": "human", "content": input})
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
    
    return data.content


# def streaming(sessionId,input):
#     store_history(sessionId,{"role": "human", "content": input})
#     chat_history = mongo.db.chat_history.find_one(
#     {"sessionId": sessionId})["messages"]
#     # print(chat_his)

#     # Prepare the chat history for the model
#     history_for_prompt = [("system", system)] + [(entry["role"], entry["content"]) for entry in chat_history]
#     prompt_with_history = ChatPromptTemplate.from_messages(history_for_prompt)
#     chain = prompt_with_history | chat
    
    