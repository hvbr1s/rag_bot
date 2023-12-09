from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import requests
import os
from dotenv import load_dotenv

# Initialize FastAPI app
app = FastAPI()

# Load environment variables
load_dotenv()

# Typesense API key and search endpoint
typesense_api_key = os.getenv("ADMIN_API_KEY")
#search_endpoint = "https://07guspnvcq5mlx1wp-1.a1.typesense.net/collections/help_center/documents/search"
search_endpoint = "https://07guspnvcq5mlx1wp-1.a1.typesense.net/collections/help_center_articles/documents/search"

# Request model
class SearchRequest(BaseModel):
    query: str

# Headers for Typesense request
headers = {
    'X-TYPESENSE-API-KEY': typesense_api_key
}

@app.post("/search")
def search(search_request: SearchRequest):
    search_params = {
        'q': search_request.query,
        'query_by': 'title,text',
        'query_by_weights': '2,1',
        'include_fields': 'title, last-updated, source',  
        'highlight_full_fields': 'text',  # Highlight matches in text
        'prefix': False,  # Disable prefix search for more precise matching
        'num_typos': 5, 
    }
    
    response = requests.get(search_endpoint, headers=headers, params=search_params)

    if response.status_code == 200:
        return response.json()
    else:
        raise HTTPException(status_code=response.status_code, detail=response.text)

@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("/home/danledger/knowledge_bot/typesense_pipeline/query/templates/index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# Local start command: uvicorn app:app --reload --port 8800
