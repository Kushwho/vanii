# llm_groq.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os

load_dotenv()

async def get_groq_response_stream(prompt_text: str):
    chat = ChatGroq(temperature=0, model_name="llama3-70b-8192", groq_api_key=os.getenv("GROQ_API_KEY"))
    prompt = ChatPromptTemplate.from_messages([("human", prompt_text)])
    chain = prompt | chat
    response_buffer = []
    async for chunk in chain.astream({"text": prompt_text}):
        if chunk.content.strip():
            response_buffer.append(chunk.content)
            yield chunk.content
   
