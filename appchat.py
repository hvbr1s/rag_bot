import os
import json
from dotenv import main
from datetime import datetime
import pinecone
from openai import OpenAI
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
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
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
pinecone.init(api_key=os.environ['PINECONE_API_KEY'], environment=os.environ['PINECONE_ENVIRONMENT'])
pinecone.whoami()
index_name = 'prod'
index = pinecone.Index(index_name)

# Initialize Cohere
os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY") 
co = cohere.Client(os.environ["COHERE_API_KEY"])

# Initialize and load Cohere classifier categories
Example = NamedTuple("Example", [("text", str), ("label", str)])

def load_examples():
    filecat = f'examples.json'
    try:
        with open(filecat, 'r') as file:
            examples_list = json.load(file)
            return [Example(**ex) for ex in examples_list]
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Examples file not found!")

examples = load_examples()

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
SUPPORTED_LOCALES = {'eng', 'fr', 'ru'}

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
            timestamp = datetime.now().strftime("%B %d, %Y %H:%M:%S")

            # Prepare tooling for the bot
            tools = [
            {
                "type": "function",
                "function": {
                "name": "retrieve",
                "description": "Technical Question API, this API makes a POST request to an external service with a technical question and user identifier.",
                "parameters": {
                    "type": "object",
                    "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's technical question."
                    }
                    },
                    "required": ["query"],
                    "async": True,
                    "implementation": "async def retrieve(query, contexts=None):"
                }
                }
            }
            ]

            # Categorize the query with Cohere
            try:
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
  
            ##################################
                       
            async def retrieve(query, contexts=None):
                # Prepare context box
                contexts = []

                # Prepare Cohere embeddings 
                try:
                    # Choose the model based on the locale
                    model = 'embed-multilingual-v3.0' if locale in ['fr', 'ru'] else 'embed-english-v3.0'

                    # Call the embedding function
                    res_embed = co.embed(
                        texts=[query],
                        model=model,
                        input_type='search_query'
                    )

                # Grab the embeddings from the response object
                except Exception as e:
                    print(f"Embedding failed: {e}")
                xq = res_embed.embeddings

                try:
                    # Translation dictionary
                    translations = {
                        'ru': '\n\nУзнайте больше на',
                        'fr': '\n\nPour en savoir plus'
                    }

                    # Default to English if locale not in dictionary
                    learn_more_text = translations.get(locale, '\n\nLearn more at')

                    # Pulls 7 chunks from Pinecone
                    res_query = index.query(xq, top_k=7, namespace=locale, include_metadata=True)

                    # Rerank chunks using Cohere
                    docs = {x["metadata"]['text'] + learn_more_text + ": " + x["metadata"].get('source', 'N/A'): i for i, x in enumerate(res_query["matches"])}
                    rerank_docs = co.rerank(
                        query=query, 
                        documents=docs.keys(), 
                        top_n=2, 
                        model="rerank-english-v2.0"
                    )
                    reranked = rerank_docs[0].document["text"]

                    # Construct the contexts
                    contexts.append(reranked)
                    return contexts

                except Exception as e:
                    return(f"Reranking failed: {e}")


            ########################################################### 
                
            # Retrieve and format the entire conversation history for a specific user_id
            user_states.setdefault(user_id, {'previous_queries': [], 'timestamp': time.time()})
            user_states[user_id]['previous_queries'].append({'user': user_input})
            previous_conversations = user_states[user_id]['previous_queries'][-4:]

            # Format previous conversations for RAG
            formatted_history = ""
            for conv in previous_conversations:
                formatted_history += f"User: {conv.get('user', '')}\nAssistant: {conv.get('assistant', '')}\n"

            # Construct the query string with complete chat history
            augmented_query = f"CHAT HISTORY: \n\n{formatted_history.strip()}"
            print(augmented_query)

            
            # Start RAG with full history
            async def rag(query, contexts=None):
                messages =  [
                    {"role": "system", "content": """
                    
                    You are SamanthaBot, an expert in cryptocurrency and helpful virtual assistant designed to support Ledger and technical queries through API integration. 
                    
                    When a user asks any question about Ledger products or anything related to Ledger's ecosystem, you will ALWAYS use the "retrieve" tool initiate an API call to an external service.

                    Before utilizing your API retrieval tool, it's essential to first understand the user's issue. This requires asking follow-up questions. Here are key points to remember:

                    1- Limit yourself to a maximum of 2 follow-up questions.
                    2- Ensure the conversation doesn't exceed 3 exchanges between you and the user.
                    3- Never request crypto addresses or transaction hashes/IDs.

                   After the user replies and even if you have incomplete information, you MUST summarize your interaction and call your API tool. This approach helps maintain a smooth and effective conversation flow.

                    ALWAYS summarize the issue as if you were the user, for example: "My issue is ..."

                    If a user needs to contact Ledger Support, they can do so at https://support.ledger.com/

                    Never use your API tool when a user simply thank you or greet you!

                    Take a deep breath, and begin!
                    
                    """},
                    {"role": "user", "content": augmented_query}
                ]
                res = client.chat.completions.create(
                    temperature=0.0,
                    #model='gpt-4',
                    model='gpt-4-1106-preview',
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
                print(res)
                # Extract reply content
                if res.choices[0].message.content is not None:
                    reply = res.choices[0].message.content
                else:
                    print("Calling API!")

                # Check for tool_calls in the response
                if res.choices[0].message.tool_calls is not None:
                    tool_call_arguments = json.loads(res.choices[0].message.tool_calls[0].function.arguments)

                    # Extract query
                    function_call_query = tool_call_arguments["query"]

                    # Use this extracted query to call the retrieve function
                    retrieved_context = await retrieve(function_call_query)
                    retrieved_context_string = retrieved_context[0]
                    if retrieved_context:
                        troubleshoot_instructions = "CONTEXT: " + "\n" + todays_date + " ." + retrieved_context_string + "\n\n" + "----" + "\n\n" + "ISSUE: " + "\n" + function_call_query
                        print(troubleshoot_instructions)
                        # Make a new completion call with the retrieved context
                        res = client.chat.completions.create(
                            temperature=0.0,
                            #model='gpt-4-1106-preview',
                            model='gpt-4',
                            messages=[
                                {"role": "system", "content": primer},
                                {"role": "user", "content": troubleshoot_instructions}
                            ]
                        )
                        new_reply = res.choices[0].message.content
                    user_states[user_id]['previous_queries'][-1]['assistant'] = new_reply
                    return new_reply

                else:
                    user_states[user_id]['previous_queries'][-1]['assistant'] = reply
                    return reply
            
            # Start RAG
            response = await rag(augmented_query)             
            print("\n\n" + response + "\n\n")
            return {'output': response}
    
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
# Local start command: uvicorn appchat:app --reload --port 8800