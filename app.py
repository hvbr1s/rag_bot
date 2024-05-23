import os
import re
import time
import cohere
import asyncio
from dotenv import main
from crewai import Crew, Process
from crew.agents import researcher
from crew.tasks import search_docs
from datetime import datetime
from openai import AsyncOpenAI
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from semantic_router.layer import RouteLayer
from semantic_router.encoders import OpenAIEncoder
from utilities.system_prompts import SYSTEM_PROMPT_eng, SYSTEM_PROMPT_fr, SYSTEM_PROMPT_ru, SYSTEM_PROMPT_es
from routes.semantic_routes import chitchat, human, niceties, languages, phone, ROUTER_DICTIONARY
from utilities.pii_filters import patterns
from utilities.tools import retrieve, rag
from utilities.rephraser import rephrase

# Initialize environment variables
main.load_dotenv()

# Initialize backend & API keys
server_api_key=os.environ['BACKEND_API_KEY'] 
API_KEY_NAME=os.environ['API_KEY_NAME'] 
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key_header: str = Depends(api_key_header)):
    if not api_key_header or api_key_header.split(' ')[1] != server_api_key:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return api_key_header

# Define query class
class Query(BaseModel):
    user_input: str
    user_id: str
    user_locale: str | None = None
    platform: str | None = None

# Define FastAPI app
app = FastAPI()

# Ready the crew
crew = Crew(
  agents=[researcher],
  tasks=[search_docs],
  process=Process.sequential,
  verbose= 1,
)

# Agent handling function
def agent(task):
    print(f"Processing task-> {task}")
    response = crew.kickoff(inputs={"topic": task})
    return response

# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']

# Initialize OpenAI client & Embedding model
openai_key = os.environ['OPENAI_API_KEY']
openai_client = AsyncOpenAI(api_key=openai_key)
embed_model = "text-embedding-3-large"

# Initialize Cohere
co = cohere.Client(os.environ["COHERE_API_KEY"])
cohere_key = os.environ["COHERE_API_KEY"]

#### DATA MANAGEMENT ####

# Initialize user state and periodic cleanup function
USER_STATES = {}
TIMEOUT_SECONDS = 1800  # 30 minutes

async def periodic_cleanup():
    while True:
        await cleanup_expired_states()
        await asyncio.sleep(TIMEOUT_SECONDS)

# Improved startup event to use asyncio.create_task for the continuous background task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(periodic_cleanup())

# Enhanced cleanup function with improved error logging
async def cleanup_expired_states():
    try:
        current_time = time.time()
        expired_users = [
            user_id for user_id, state in USER_STATES.items()
            if current_time - state['timestamp'] > TIMEOUT_SECONDS
        ]
        for user_id in expired_users:
            try:
                del USER_STATES[user_id]
                print("User state deleted!")
            except Exception as e:
                print(f"Error during cleanup for user {user_id}: {e}")
    except Exception as e:
        print(f"General error during cleanup: {e}")

######## LOCALIZATION ##########

# Define supported locales for data retrieval
SUPPORTED_LOCALES = {'eng', 'fr', 'ru', 'es'}
LOCALE_TO_PROMPT_MAP = {
    'eng': SYSTEM_PROMPT_eng,
    'fr': SYSTEM_PROMPT_fr,
    'ru': SYSTEM_PROMPT_ru,
    'es': SYSTEM_PROMPT_es
}

# Load localized prompt
def load_sysprompt(locale):
    try:
        return LOCALE_TO_PROMPT_MAP[locale]
    except KeyError:
        raise ValueError(f"System prompt for locale '{locale}' is not supported")

# Pre-load prompts
system_prompts = {locale: load_sysprompt(locale) for locale in SUPPORTED_LOCALES}

# Translations dictionary
translations = {
    'ru': '\n\nУзнайте больше на',
    'fr': '\n\nPour en savoir plus',
    'es': '\n\nPara aprender más'
}

########   SEMANTIC ROUTING  ##########

# Initialize routes and encoder
routes = [chitchat, human, niceties, languages, phone]
encoder = OpenAIEncoder(
    name='text-embedding-3-small',
    score_threshold=0.45,
)
rl = RouteLayer(
    encoder=encoder, 
    routes=routes,
)  

######## FUNCTIONS  ##########

# Function to replace crypto addresses
def replace_crypto_address(match):
    full_address = match.group(0)
    if match.lastindex is not None and match.lastindex >= 1:
        prefix = match.group(1)  # Capture the prefix
    else:
        # Infer prefix based on the address pattern
        if full_address.startswith("0x"):
            prefix = "0x"
        elif any(full_address.startswith(p) for p in ["L", "M", "D", "r", "cosmos", "addr1"]):
            prefix = full_address.split('1', 1)[0] 
        else:
            prefix = ''
    return prefix + 'xxxx'

# Function to apply email & crypto addresses filter and replace addresses
def filter_and_replace_crypto(user_input):
    for ctxt, pattern_list in patterns.items():
        for pattern in pattern_list:
            user_input = re.sub(pattern, replace_crypto_address, user_input, flags=re.IGNORECASE)
    return user_input

# Concise input function:
def extract_concise_input(user_input):
    # Find the index of the first occurrence of ":"
    end_index = user_input.find(":")
    
    if end_index != -1:
        # Extract the substring after the first ":"
        concise_input = user_input[end_index + 1:].strip()
        return concise_input
    else:
        return user_input


######## API Routes ##########

# Health probe
@app.get("/_health")
async def health_check():
    return {"status": "OK"}

# RAG route
@app.post('/gpt') 
async def react_description(query: Query, api_key: str = Depends(get_api_key)): 

    # Deconstruct incoming query
    user_id = query.user_id
    user_input = filter_and_replace_crypto(query.user_input.strip())
    concise_query = extract_concise_input(user_input)
    locale = query.user_locale if query.user_locale in SUPPORTED_LOCALES else "eng" # if locale is not supported or not provided, default to 'eng'

    # Loading locale-appropriate system prompt
    primer = system_prompts.get(locale, system_prompts["eng"])

    # Create a conversation history for new users
    convo_start = time.time()
    USER_STATES.setdefault(user_id, {
        'previous_queries': [],
        'timestamp': convo_start
    })

    try:
        # Set clock
        timestamp = datetime.now().strftime("%B %d, %Y")

        # Prepare enriched user query
        rephrased_query = await rephrase(user_input, locale)

        # Filter non-queries
        route_path = rl(concise_query).name
        if route_path in ["chitchat", "human", "niceties", "languages", "phone"]:
            print(f'Concise query: {concise_query} -> Route triggered: {route_path}')
            output = ROUTER_DICTIONARY[route_path].get(locale, "eng")
            return {"output": output}

        # Start date retrieval and reranking
        try:
            # Retrieve contexts asynchronously in a separate thread
            contexts = await asyncio.to_thread(agent, rephrased_query)
        except Exception as e:
            # Handle exceptions from the agent function
            print(f"Agentic retrieval failed: {e}")
            contexts = await retrieve(user_input, locale, rephrased_query)


        # Retrieve and format previous conversation history for a specific user_id
        previous_conversations = USER_STATES[user_id].get('previous_queries', [])[-1:]  # Get the last -N conversations

        # Start RAG
        response = await rag(primer, timestamp, contexts, locale, concise_query, previous_conversations)
        rep =  response[0]
        bot = response[1]

        #Clean response
        cleaned_response = rep.replace("**", "").replace("Manager", "Manager (now called 'My Ledger')")           
        
        log_entry = f"""
----------------{f"User ID: {user_id}"}----------------
Full query: {query}
Locale: {locale}
Llm: {bot}
Route: {route_path}
Concise query: {concise_query}
Rephrased query: {rephrased_query}
Docs: {contexts}
Chat history: {previous_conversations}
Final Output: {cleaned_response}
---------------------------------------
"""
        print(log_entry)
        # Save the response to a thread
        try:
            USER_STATES[user_id] = {
                'previous_queries': USER_STATES[user_id].get('previous_queries', []) + [(user_input, cleaned_response)],
                'timestamp': convo_start
            }

        except Exception as e:
            print("Saving thread failed!")
                                        
        # Return response to user
        return {'output': cleaned_response}
    
    except ValueError as e:
        print(e)
        raise HTTPException(status_code=400, detail="Snap! Something went wrong, please try again!")
    
    except HTTPException as e:
        print(e)
        # Handle known HTTP exceptions
        return JSONResponse(
            status_code=e.status_code,
            content={"message": e.detail},
        )
    except Exception as e:
        print(e)
        # Handle other unexpected exceptions
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"message": "Snap! Something went wrong, please try again!"},
        )
        
# Local start command: uvicorn app:app --reload --port 8800
