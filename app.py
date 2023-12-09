import os
import json
from dotenv import main
from datetime import datetime
import pinecone
import openai
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, TypeAdapter
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import BackgroundTasks
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
from cohere.responses.classify import Example
from nostril import nonsense
import tiktoken
import re
import time
import cohere
import asyncio
from typing import NamedTuple


# Initialize environment variables
main.load_dotenv()

# Initialize backend
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

# Initialize Pinecone
openai.api_key=os.environ['OPENAI_API_KEY']
pinecone.init(api_key=os.environ['PINECONE_API_KEY'], environment=os.environ['PINECONE_ENVIRONMENT'])
pinecone.whoami()
index_name = 'database'
index = pinecone.Index(index_name)

# Initialize Cohere
os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY") 
co = cohere.Client(os.environ["COHERE_API_KEY"])

# Initialize and load Cohere classifier categories
Example = NamedTuple("Example", [("text", str), ("label", str)])
def load_examples(file_path):
    with open(file_path, 'r') as file:
        examples_list = json.load(file)
        return [Example(**ex) for ex in examples_list]

# Load the examples from the file
examples = load_examples('/home/dan/knowledge_bot/examples.json')

# examples=[
#   # Passphrase  
#   Example("There's no way to recover the accounts behind the passphrase if I don't remember it?", "Passphrase"),
#   Example("How can I verify my Passphrase? I want to make sure that it is correct.", "Passphrase"),
#   # Scam
#   Example("I have had messenger send me a form to fill in my 24 word phrase to update it, can I do it that way?", "Scam"),
#   Example("A ledger employee asked me for my 24-word recovery phrase on Twitter", "Scam"),
#   # Cardano staking
#   Example("how can I claim rewards for cardano?", "Staking Cardano"),\
#   Example("Does  ADA rewards compound?", "Staking Cardano"),
#   ## Cosmos
#   Example("does ATOM rewards compound?", "Cosmos Staking"),
#   Example("can't delegate my Cosmos", "Cosmos Staking"),
#   # Solana
#   Example("network error on SOl", "Solana"),
#   Example(" Does Solana have receiving address changing like Bitcoin?", "Solana"),
#   # Solana staking
#   Example("SOL commission 95%?", "Solana Staking"),
#   Example("can I stake SOL on solfalre?", "Solana Staking"),
#   Example("I cannot deactivate staking in Ledger with SOL", "Solana Staking"),
#   # Other
#   Example("can you please tell me if you have a physical store in Paris?", "Other"),
#   Example("does ledger hire?", "Other"),
#   # Swap Changelly
#   Example("Swapped 900 matic to solana account and swap is complete but no solana", "Swap Changelly"),
#   Example("I cannot swap swap BNB for XRP through Changelly", "Swap Changelly"),
# ]

# Email address detector
email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
def find_emails(text):  
    return re.findall(email_pattern, text)

# Set up address filters:
ETHEREUM_ADDRESS_PATTERN = r'\b0x[a-fA-F0-9]{40}\b'
BITCOIN_ADDRESS_PATTERN = r'\b(1|3)[1-9A-HJ-NP-Za-km-z]{25,34}\b|bc1[a-zA-Z0-9]{25,90}\b'
LITECOIN_ADDRESS_PATTERN = r'\b(L|M)[a-km-zA-HJ-NP-Z1-9]{26,34}\b'
DOGECOIN_ADDRESS_PATTERN = r'\bD{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}\b'
XRP_ADDRESS_PATTERN = r'\br[a-zA-Z0-9]{24,34}\b'
COSMOS_ADDRESS_PATTERN = r'\bcosmos[0-9a-z]{38,45}\b'
SOLANA_ADDRESS_PATTERN= r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'

# Initialize tokenizer and create length function
tokenizer = tiktoken.get_encoding('cl100k_base')
def tiktoken_len(text):
    tokens = tokenizer.encode(
        text,
        disallowed_special=()
    )
    return len(tokens)

async def get_user_id(request: Request):
    try:
        body = TypeAdapter(Query).validate_python(await request.json())
        user_id = body.user_id
        return user_id
    except Exception as e:
        return get_remote_address(request)

# Define FastAPI app
app = FastAPI()

# Define rate-limiter
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

# Initialize user state and periodic cleanup function
user_states = {}
TIMEOUT_SECONDS = 1 * 25 * 60  # 25 minutes

async def periodic_cleanup():
    while True:
        await cleanup_expired_states()
        await asyncio.sleep(TIMEOUT_SECONDS)

# Invoke periodic cleanup
@app.on_event("startup")
async def startup_event():
    background_tasks = BackgroundTasks()
    background_tasks.add_task(periodic_cleanup)

# Handle cleanup crashes gracefully
async def cleanup_expired_states():
    try:
        current_time = time.time()
        expired_users = [
            user_id for user_id, state in user_states.items()
            if current_time - state['timestamp'] > TIMEOUT_SECONDS
        ]
        for user_id in expired_users:
            del user_states[user_id]
    except Exception as e:
        print(f"Error during cleanup: {e}")


# Define FastAPI endpoints
@app.get("/")
async def root():
    return {"welcome": "You've reached the home route!"}

# Define server health probe
@app.get("/_health")
async def health_check():
    return {"status": "OK"}

# Define exception handler function
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"message": "Snap! Something went wrong, please try again!"},
    )

# Define supported locales for data retrieval
SUPPORTED_LOCALES = {'eng', 'fr'}

# Define RAG route
@app.post('/gpt')
@limiter.limit("100/minute")
async def react_description(query: Query, request: Request, api_key: str = Depends(get_api_key)):
    user_id = query.user_id
    user_input = query.user_input.strip()
    locale = query.user_locale if query.user_locale in SUPPORTED_LOCALES else "eng"

    def load_sysprompt(locale):
        filename = f'system_prompt_{locale}.txt'
        try:
            with open(filename, 'r') as sys_file:
                return sys_file.read()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"System primer file for {locale} not found")

    primer = load_sysprompt(locale)

    if user_id not in user_states:
        user_states[user_id] = {
            'previous_queries': [],
            'timestamp': time.time()
        }

    if not user_input or nonsense(user_input):
        print('Nonsense detected!')
        if locale == "fr":
            return {'output': "Je suis désolé, je n'ai pas compris votre question et je ne peux pas aider avec des questions qui incluent des adresses de cryptomonnaie. Pourriez-vous s'il vous plaît fournir plus de détails ou reformuler sans l'adresse ? N'oubliez pas, je suis ici pour aider avec toute demande liée à Ledger."}
        else: 
            return {'output': "I'm sorry, I cannot understand your question, and I can't assist with questions that include cryptocurrency addresses. Could you please provide more details or rephrase it without the address? Remember, I'm here to help with any Ledger-related inquiries."}
  

    if re.search(ETHEREUM_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(BITCOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(LITECOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(DOGECOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(COSMOS_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(SOLANA_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(XRP_ADDRESS_PATTERN, user_input, re.IGNORECASE):
        if locale == 'fr':
            return {'output': "Je suis désolé, mais je ne peux pas aider avec des questions qui incluent des adresses de cryptomonnaie. Veuillez retirer l'adresse et poser la question à nouveau."}
        else:
            return {'output':"I'm sorry, but I can't assist with questions that include cryptocurrency addresses. Please remove the address and ask again"}
    
    if re.search(email_pattern, user_input):
        if locale == 'fr':
            return {
            'output': "Je suis désolé, mais je ne peux pas aider avec des questions qui incluent des adresses e-mail. Veuillez retirer l'adresse et poser la question à nouveau."
                }
        else:
            return{
                'output': "I'm sorry, but I can't assist with questions that include email addresses. Please remove the address and ask again."
            }
    
    else:
        
        try:

            # Set clock
            todays_date = datetime.now().strftime("%B %d, %Y")

            # Classify the query with Cohere
            try:
                # Classify the query with Cohere
                res = co.classify(
                    inputs=[user_input],
                    examples=examples,
                )
                prediction = res.classifications
                category = prediction[0].predictions[0]
            except Exception as e:
                print(f"Classification failed: {e}")
                category = 'Could not categorize'
            print(category)
  
            #############
                       
            async def retrieve(query, contexts=None):
                # Define context box
                contexts = []
                
                # Prepare embeddings
                response = co.embed(
                    texts=[user_input],
                    model='embed-english-v3.0',
                    input_type='search_document'
                )
                xq = response.embeddings

                try:
                    # Pulls 7 chunks from Pinecone
                    res_query = index.query(xq, top_k=7, namespace=locale, include_metadata=True)

                    # Rerank chunks using Cohere
                    docs = {x["metadata"]['text'] + "\nLearn more at: " + x["metadata"].get('source', 'N/A'): i for i, x in enumerate(res_query["matches"])}
                    rerank_docs = co.rerank(
                        query=query, 
                        documents=docs.keys(), 
                        top_n=2, 
                        model="rerank-english-v2.0"
                    )
                    reranked = rerank_docs[0].document["text"]

                    # Construct the contexts
                    contexts.append(reranked)

                except Exception as e:
                    print(f"Reranking failed: {e}")

                    # Fallback to simpler retrieval without Cohere if reranking fails
                    res_query = index.query(xq, top_k=2, namespace=locale, include_metadata=True)
                    sorted_items = sorted([item for item in res_query['matches'] if item['score'] > 0.77], key=lambda x: x['score'], reverse=True)

                    for idx, item in enumerate(sorted_items):
                        context = item['metadata']['text']
                        context += "\nLearn more: " + item['metadata'].get('source', 'N/A')
                        contexts.append(context)

            ##########################  
                
                # Retrieve and format previous conversation history for a specific user_id        
                previous_conversations = user_states[user_id].get('previous_queries', [])[-2:]  # Get the last -N conversations

                # Format previous conversations
                previous_conversation = ""
                for conv in previous_conversations:
                    previous_conversation += f"User: {conv[0]}\nAssistant: {conv[1]}\n\n"
                
                # Construct the augmented query string with locale, contexts, chat history, and user input
                if locale == 'fr':
                    augmented_query = "CONTEXTE: " + "\n\n" + "La date d'aujourdh'hui est: " + todays_date + "\n\n" + "\n\n".join(contexts) + "\n\n-----\n\n" + "HISTORIQUE DU CHAT: \n" +  previous_conversation.strip() + "\n\n-----\n\n" + "User: " + user_input + "\n" + "Assistant: " + "\n"
                else:
                    augmented_query = "CONTEXT: " + "\n\n" + "Today is: " + todays_date + "\n\n" + "\n\n".join(contexts) + "\n\n-----\n\n" + "CHAT HISTORY: \n" +  previous_conversation.strip() + "\n\n-----\n\n" + "User: " + user_input + "\n" + "Assistant's short answer: " + "\n"

                return augmented_query

            # Start Retrieval        
            augmented_query = await retrieve(user_input)
            print(augmented_query)

            # Request and return OpenAI RAG
            async def rag(query, contexts=None):
                res = openai.ChatCompletion.create(
                    temperature=0.0,
                    model='gpt-4',
                    #model='gpt-4-1106-preview',
                    messages=[
                        {"role": "system", "content": primer},
                        {"role": "user", "content": augmented_query}
                    ]
                )             
                reply = res['choices'][0]['message']['content']
                return reply
            
            # Start RAG
            response = await rag(augmented_query)
                                   
            # Save the response to a thread
            user_states[user_id] = {
                'previous_queries': user_states[user_id].get('previous_queries', []) + [(user_input, response)],
                'timestamp': time.time()
            }

            print("\n\n" + response + "\n\n")
            return {'output': response, 'category': category}
    
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