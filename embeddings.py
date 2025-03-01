import os
from langchain_voyageai import VoyageAIEmbeddings
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from pinecone import Pinecone, ServerlessSpec





def process_pdf_to_faiss(pdf_path: str, model: str = "voyage-3-lite", chunk_size: int = 1000, chunk_overlap: int = 200):
    """
    Processes a PDF file, splits it into chunks, and stores embeddings in FAISS.

    Args:
        pdf_path (str): Path to the PDF file to process.
        model (str): The VoyageAI model to use for embeddings. Default is "voyage-3-lite".
        chunk_size (int): Size of text chunks for splitting. Default is 1000 characters.
        chunk_overlap (int): Overlap between text chunks. Default is 200 characters.

    Returns:
        FAISS: The FAISS vector store with the processed embeddings.
    """
    # Load environment variables
    load_dotenv()
    VOYAGEAI_API_KEY = os.getenv("VOYAGEAI_API_KEY")

    if not VOYAGEAI_API_KEY:
        raise ValueError("VoyageAI API key not found in environment variables.")
    embeddings = VoyageAIEmbeddings(model=model, api_key=VOYAGEAI_API_KEY) 
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    all_splits = text_splitter.split_documents(docs)
    vector_store = FAISS.from_documents(all_splits,embeddings)
    return vector_store






# Example usage
if __name__ == "__main__":
    pdf_file = "CCclass10.pdf"  
    faiss_store = process_pdf_to_faiss(pdf_file)

    # Save the FAISS index to a file for future use
    faiss_store.save_local("faiss_index")
    print("FAISS index created and saved.")