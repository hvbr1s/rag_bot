import os
from dotenv import main
from datetime import datetime
from openai import AsyncOpenAI
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from semantic_router.layer import RouteLayer
from semantic_router.encoders import OpenAIEncoder
from utilities.system_prompts import SYSTEM_PROMPT_eng, SYSTEM_PROMPT_fr, SYSTEM_PROMPT_ru
from utilities.semantic_routes import chitchat, agent, niceties, languages, phone, ROUTER_DICTIONARY
from utilities.pii_filters import patterns
from utilities.tools import retrieve
import re
import time
import cohere
import asyncio
import httpx

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

# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']

# Initialize OpenAI client & Embedding model
openai_key = os.environ['OPENAI_API_KEY']
openai_client = AsyncOpenAI(api_key=openai_key)
embed_model = "text-embedding-3-large"

# Initialize Cohere
co = cohere.Client(os.environ["COHERE_API_KEY"])
cohere_key = os.environ["COHERE_API_KEY"]

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
SUPPORTED_LOCALES = {'eng', 'fr', 'ru'}
LOCALE_TO_PROMPT_MAP = {
    'eng': SYSTEM_PROMPT_eng,
    'fr': SYSTEM_PROMPT_fr,
    'ru': SYSTEM_PROMPT_ru
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
    'fr': '\n\nPour en savoir plus'
}

########   SEMANTIC ROUTING  ##########

# Initialize routes and encoder
routes = [chitchat, agent, niceties, languages, phone]
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

        
# RAG function
async def rag(primer, timestamp, contexts, user_id, locale, concise_query, docs):

    # Prepare LLMs
    main_llm = 'gpt-4-turbo'
    first_backup_llm = 'gpt-4'
    second_backup_llm = 'command-r'

    # Retrieve and format previous conversation history for a specific user_id
    previous_conversations = USER_STATES[user_id].get('previous_queries', [])[-1:]  # Get the last -N conversations

    # Format previous conversations
    previous_conversation = ""
    for conv in previous_conversations:
        previous_conversation += f"User: {conv[0]}\nAssistant: {conv[1]}\n\n"
    
    # Construct the augmented query string with locale, contexts, chat history, and user input
    if locale == 'fr':
        augmented_query = "CONTEXTE: " + "\n\n" + "La date d'aujourdh'hui est: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "HISTORIQUE DU CHAT: \n" +  previous_conversation.strip() + "\n\n" + "Utilisateur: \"" + concise_query + "\"\n" + "Assistant: " + "\n"
    elif locale == 'ru':
        augmented_query = "КОНТЕКСТ: " + "\n\n" + "Сегодня: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "ИСТОРИЯ ПЕРЕПИСКИ: \n" +  previous_conversation.strip() + "\n\n" + "Пользователь: \"" + concise_query + "\"\n" + "Ассистента: " + "\n"
    else:
        augmented_query = "CONTEXT: " + "\n\n" + "Today is: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "CHAT HISTORY: \n" +  previous_conversation.strip() + "\n\n" + "User: \"" + concise_query + "\"\n" + "Assistant: " + "\n"

    try:
        
        res = await openai_client.chat.completions.create(
            temperature=0.0,
            model=main_llm,
            messages=[

                {"role": "system", "content": primer},
                {"role": "user", "content": augmented_query}

            ],
            timeout= 45.0
        )             
        reply = res.choices[0].message.content
   
    except Exception as e:
        print(f"GPT4-turbo completion failed: {e}")
        try:

            res = await openai_client.chat.completions.create(
                    temperature=0.0,
                    model=first_backup_llm,
                    messages=[

                        {"role": "system", "content": primer},
                        {"role": "user", "content": augmented_query}

                    ],
                    timeout= 45.0
                )             
            reply = res.choices[0].message.content

        except Exception as e:
            print(f"GPT4-legacy completion failed: {e}")
            try:   

                docs = docs
                documents = []
                for doc in docs:
                    if "\nLearn more at: " in doc['text']:
                        # Splitting the document into parts before and after "Learn more at: "
                        pre_learn_more, post_learn_more = doc['text'].split("\nLearn more at: ", 1)
                        url = post_learn_more.split()[0]
                        documents.append({
                            "title": url,
                            "snippet": pre_learn_more.strip()
                        })
                    else:
                        # If no "Learn more at: " is found, we'll leave the title empty and take the entire text as snippet.
                        documents.append({
                            "title": "",
                            "snippet": doc['text'].strip()
                        })
                async with httpx.AsyncClient() as client: 

                    command_response = await client.post(

                        "https://api.cohere.ai/v1/chat",
                        json={

                            "message": augmented_query,
                            "model": second_backup_llm,
                            "preamble_override": primer,
                            "temperature": 0.0,
                            "documents": documents,

                        },
                        headers={

                            "Authorization": f"Bearer {cohere_key}"

                        },
                        timeout=35.0,

                    )
                command_response.raise_for_status()
                rep = command_response.json()
                
                # Extract URLs from respnse object and construct the reply
                doc_id_to_url = {doc["id"]: doc["title"] for doc in rep["documents"]}
                unique_doc_ids = {doc_id for citation in rep["citations"] for doc_id in citation["document_ids"]}
                limited_citation_urls = [doc_id_to_url[doc_id] for doc_id in list(unique_doc_ids)[:2]] # only grab 2 urls
                reply = rep["text"] + '\nYou can learn more at: ' + '\n' + '\n'.join(url for url in limited_citation_urls)
                 
            except Exception as e:
                print(f"Cohere command-r completion failed: {e}")
                return("Snap! Something went wrong, please ask your question again!")

    return reply

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
    locale = query.user_locale if query.user_locale in SUPPORTED_LOCALES else "eng"

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

        # Filter non-queries
        route_path = rl(concise_query).name
        if route_path in ["chitchat", "agent", "niceties", "languages", "phone"]:
            print(f'Concise query: {concise_query} -> Route triggered: {route_path}')
            output = ROUTER_DICTIONARY[route_path].get(locale, "eng")
            return {"output": output}

        # Start date retrieval and reranking
        retriever = await retrieve(user_input, locale)
        contexts, docs = retriever

        # Start RAG
        response = await rag(primer, timestamp, contexts, user_id, locale, concise_query, docs)

        #Clean response
        cleaned_response = response.replace("**", "").replace("Manager", "Manager (now called 'My Ledger')")           
     
        #Verbose logging
        titles = []
        for doc in docs[:2]: 
                title = doc["text"].split(":")[0]
                titles.append(title)
        
        log_entry = f"""
----------------{f"User ID: {user_id}"}----------------
Full Query: {query}
Route: {route_path}
Concise query: {user_input}
Docs: {titles}
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
