from langchain_core.prompts import ChatPromptTemplate,MessagesPlaceholder
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
import time
import logging
from langchain_community.chat_message_histories import RedisChatMessageHistory
from langchain_mongodb import MongoDBChatMessageHistory
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_core.messages import trim_messages


load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")

CONNECTION_STRING = os.getenv("DB_URI")

model = ChatGroq(temperature=0.5, model_name="llama3-8b-8192", groq_api_key=groq_api_key,max_tokens=500)
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
    lambda session_id : MongoDBChatMessageHistory(
        session_id=session_id,
        connection_string=CONNECTION_STRING,
        database_name="chat_histories",
        collection_name="messages",
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

    
    