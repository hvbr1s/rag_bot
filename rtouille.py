"""

An implementation of the RAGatouille search framework

"""

import json
from fastapi import FastAPI
from pydantic import BaseModel
from ragatouille import RAGPretrainedModel

app = FastAPI()

# Define query class
class Query(BaseModel):
    user_input: str
    user_id: str | None = None
    user_locale: str | None = None


# Initialize the RAG model globally
RAG = RAGPretrainedModel.from_pretrained("colbert-ir/colbertv2.0")

# Load and index documents outside the route
file_path = "/home/dan/rag_bot/pinecone_pipeline/ragatouille/output_ragatouille.json"
with open(file_path, 'r', encoding='utf-8') as file:
    my_documents = json.load(file)

index = "ledger"
RAG.index(
    collection=my_documents,
    index_name=index,
    max_document_length=512,
    split_documents=True,
)

@app.get("/ragatouille_retrieval")
async def retrieve(query: Query):
    user_query = query.user_input
    print(user_query)
    
    # Run query using the RAG model
    results = RAG.search(query=user_query, k=4)
    
    # Assign the content of the first ranked item to the variable 'reply'
    reply = results[0]['content'] if results else "No results found"
    
    return {"output": reply}

# Run using: uvicorn rtouille:app --reload --port 8800
