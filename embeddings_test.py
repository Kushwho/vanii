# Initialize ChromaDB and perform search
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceEmbeddings
import time

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vector_store = Chroma(
    persist_directory="./chroma_langchain_db",
    embedding_function=embeddings,
    collection_name="embeddings"
)

query = "What do you know about Rinjha from my chapter or the subject"
metadata_filter = {
    "$and": [
        {"category": {"$eq": "Geography"}},
        {"chapter": {"$eq": "Agriculture"}}
    ]
}

start = time.time()
results = vector_store.similarity_search(
    query=query,
    k=2,
    filter=metadata_filter
)

context_content = "\n".join(
            [f"Document excerpt: {doc.page_content}" 
             for doc in results]
        )
print(time.time()-start)
print(context_content)

