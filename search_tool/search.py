import os
import json
from dotenv import main
import pinecone
from openai import OpenAI
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, parse_obj_as
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import BackgroundTasks
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from nostril import nonsense
import tiktoken
from langsmith.run_helpers import traceable
import re
import time


main.load_dotenv()

#########Initialize backend API keys ######
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
server_api_key=os.environ['BACKEND_API_KEY'] 
API_KEY_NAME=os.environ['API_KEY_NAME'] 
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Depends(api_key_header)):
    if not api_key_header or api_key_header.split(' ')[1] != server_api_key:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return api_key_header

class Query(BaseModel):
    user_input: str
    user_id: str

# Initialize Pinecone

pinecone.init(api_key=os.environ['PINECONE_API_KEY'], enviroment=os.environ['PINECONE_ENVIRONMENT'])
pinecone.whoami()
index_name = 'prod'
index = pinecone.Index(index_name)

embed_model = "text-embedding-ada-002"

# ###################################################


# Email address  detector
email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
def find_emails(text):  
    return re.findall(email_pattern, text)

# Address filter:
ETHEREUM_ADDRESS_PATTERN = r'\b0x[a-fA-F0-9]{40}\b'
BITCOIN_ADDRESS_PATTERN = r'\b(1|3)[1-9A-HJ-NP-Za-km-z]{25,34}\b|bc1[a-zA-Z0-9]{25,90}\b'
LITECOIN_ADDRESS_PATTERN = r'\b(L|M)[a-km-zA-HJ-NP-Z1-9]{26,34}\b'
DOGECOIN_ADDRESS_PATTERN = r'\bD{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}\b'
XRP_ADDRESS_PATTERN = r'\br[a-zA-Z0-9]{24,34}\b'
COSMOS_ADDRESS_PATTERN = r'\bcosmos[0-9a-z]{38,45}\b'


tokenizer = tiktoken.get_encoding('cl100k_base')

# create the length function
def tiktoken_len(text):
    tokens = tokenizer.encode(
        text,
        disallowed_special=()
    )
    return len(tokens)

def get_user_id(request: Request):
    try:
        body = parse_obj_as(Query, request.json())
        user_id = body.user_id
        return user_id
    except Exception as e:
        return get_remote_address(request)

def find_longest_common_substring(s1, s2):
    # Create a table to store the length of common substrings
    common_substring_lengths = [[0] * (len(s2) + 1) for _ in range(len(s1) + 1)]
    max_length = 0
    end_index_s1 = 0

    for i in range(1, len(s1) + 1):
        for j in range(1, len(s2) + 1):
            if s1[i - 1] == s2[j - 1]:
                common_substring_lengths[i][j] = common_substring_lengths[i - 1][j - 1] + 1
                if common_substring_lengths[i][j] > max_length:
                    max_length = common_substring_lengths[i][j]
                    end_index_s1 = i

    return s1[end_index_s1 - max_length:end_index_s1]


def combine_sentences(sentences):
    if len(sentences) == 0:
        return ""

    combined_sentence = sentences[0]
    for i in range(1, len(sentences)):
        overlap = find_longest_common_substring(combined_sentence, sentences[i])
        combined_sentence += sentences[i].replace(overlap, "", 1)

    return combined_sentence

# Define FastAPI app
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="./static/BBALP00A.TTF")


# Define limiter
limiter = Limiter(key_func=get_user_id)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Too many requests, please try again in a minute."},
    )

# Define FastAPI endpoints
@app.get("/")
async def root():
    return {"welcome": "You've reached the home route!"}

@app.get("/search", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/_health")
async def health_check():
    return {"status": "OK"}

@app.get("/_index")
async def pinecone_index():
    return {"index": index_name}

@app.post('/search_go')
@limiter.limit("500/minute")
async def react_description(query: Query, request: Request): 
    
    user_input = query.user_input.strip()
    
    # if not nonsense(user_input):
    #     print('Nonsense detected!')
    #     return {'output': "I'm sorry, I cannot understand your question, and I can't assist with questions that include cryptocurrency addresses. Could you please provide more details or rephrase it without the address? Remember, I'm here to help with any Ledger-related inquiries."}
    
    if re.search(ETHEREUM_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(BITCOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(LITECOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(DOGECOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(COSMOS_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(XRP_ADDRESS_PATTERN, user_input, re.IGNORECASE):
        return {'output': "I'm sorry, but I can't assist with questions that include cryptocurrency addresses. Please remove the address and ask again."}
    
    if re.search(email_pattern, user_input):
        return {
            'output': "I'm sorry, but I can't assist with questions that include email addresses. Please remove the address and ask again."
        }
    
    else:
        try:
            # Define Retrieval
            async def retrieve(query, contexts=None):
                res_embed = client.embeddings.create(input=[user_input],
                engine=embed_model)
                xq = res_embed['data'][0]['embedding']
                res_query = index.query(xq, top_k=5, namespace="en-us", include_metadata=True)
                
                # Filter items with score > 0.77 and sort them in descending order by score
                sorted_items = sorted([item for item in res_query['matches'] if item['score'] > 0.77], 
                                    key=lambda x: x['score'], reverse=True)

                # Construct the search results
                results = []
                seen_titles = set()  # Set to keep track of titles already added
                for item in sorted_items:
                    title = item['metadata'].get('title', 'N/A').title()  # Capitalize each word in title
                    if title in seen_titles:  # If this title has already been added, skip
                        continue
                    seen_titles.add(title)
                    source = item['metadata'].get('source', 'N/A')
                    context = item['metadata']['text'][:100]  # Limit the context to 100 characters
                    results.append(f"**{title.strip()}**\nSource: {source}\n\n{context}\n\n****\n")  # Title is bolded and Source is added before the URL
                    
                return "\n".join(results)

            # Start Retrieval        
            response = await retrieve(user_input)
            print(response)
            return {'output': response}

        except ValueError as e:
            print(e)
            raise HTTPException(status_code=400, detail="Invalid input")


        
# Local start command: uvicorn search:app --reload --port 8800