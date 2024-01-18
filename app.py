import os
from dotenv import main
from datetime import datetime
import pinecone
from openai import AsyncOpenAI
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.security import APIKeyHeader
from nostril import nonsense
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

# Define FastAPI app
app = FastAPI()

# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']
pinecone.init(api_key=pinecone_key, environment=os.environ['PINECONE_ENVIRONMENT'])
pinecone.whoami()
index_name = 'prod'
index = pinecone.Index(index_name)

# Initialize OpenAI client & Embedding model
openai_key = os.environ['OPENAI_API_KEY']
openai_client = AsyncOpenAI(api_key=openai_key)
embed_model = "text-embedding-ada-002"

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

# Define supported locales for data retrieval
SUPPORTED_LOCALES = {'eng', 'fr', 'ru'}

# Load localized system prompt
def load_sysprompt(locale):
    filename = f'system_prompt_{locale}.txt'
    try:
        with open(filename, 'r') as sys_file:
            return sys_file.read()
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"System primer file for {locale} not found")

# Pre-load prompts
system_prompts = {locale: load_sysprompt(locale) for locale in SUPPORTED_LOCALES}

# Define helpers functions & dictionaries
def handle_nonsense(locale):
    messages = {
        'fr': "Je suis désolé, je n'ai pas compris votre question et je ne peux pas aider avec des questions qui incluent des adresses de cryptomonnaie. Pourriez-vous s'il vous plaît fournir plus de détails ou reformuler sans l'adresse ? N'oubliez pas, je suis ici pour aider avec toute demande liée à Ledger.",
        'ru': "Извините, я не могу понять ваш вопрос, и я не могу помочь с вопросами, содержащими адреса криптовалют. Не могли бы вы предоставить более подробную информацию или перефразировать вопрос без упоминания адреса? Помните, что я готов помочь с любыми вопросами, связанными с Ledger.",
        'default': "I'm sorry, I didn't quite get your question, and I can't assist with questions that include cryptocurrency addresses or transaction hashes. Could you please provide more details or rephrase it without the address? Remember, I'm here to help with any Ledger-related inquiries."
    }
    print('Nonsense detected!')
    return {'output': messages.get(locale, messages['default'])}

# Translations dictionary
translations = {
    'ru': '\n\nУзнайте больше на',
    'fr': '\n\nPour en savoir plus'
}

# Initialize email address detector
email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
def find_emails(text):  
    return re.findall(email_pattern, text)

# Set up address patterns:
EVM_ADDRESS_PATTERN = r'\b0x[a-fA-F0-9]{40}\b|\b0x[a-fA-F0-9]{64}\b'
BITCOIN_ADDRESS_PATTERN = r'\b(1|3)[1-9A-HJ-NP-Za-km-z]{25,34}\b|bc1[a-zA-Z0-9]{25,90}\b'
LITECOIN_ADDRESS_PATTERN = r'\b(L|M)[a-km-zA-HJ-NP-Z1-9]{26,34}\b'
DOGECOIN_ADDRESS_PATTERN = r'\bD{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}\b'
XRP_ADDRESS_PATTERN = r'\br[a-zA-Z0-9]{24,34}\b'
COSMOS_ADDRESS_PATTERN = r'\bcosmos[0-9a-z]{38,45}\b'
SOLANA_ADDRESS_PATTERN= r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
CARDANO_ADDRESS_PATTERN = r'\baddr1[0-9a-z]{58}\b'

patterns = {
    'crypto': [EVM_ADDRESS_PATTERN, BITCOIN_ADDRESS_PATTERN, LITECOIN_ADDRESS_PATTERN, 
            DOGECOIN_ADDRESS_PATTERN, COSMOS_ADDRESS_PATTERN, CARDANO_ADDRESS_PATTERN, 
            SOLANA_ADDRESS_PATTERN, XRP_ADDRESS_PATTERN],
    'email': [email_pattern]
}


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

# Function to generate one expanded query
EXPANDER_PROMPT = """

You are a helpful expert crypto research assistant working for Ledger, the crypto wallet company,

Your role is to provide technical answers to queries from Ledger customers seeking assistance.

For each query, give ONE brief answer based on your knowledge of cryptocurrency, Ledger devices and the Ledger Live app.

VERY IMPORTANT:

- Solana tokens (USDC, UDTC, etc) are not supported in Ledger Live.
- When users mention issues swapping, they often refer to issues swapping coins (BTC to ETH, ETH to SOL, etc) via the Changelly app within Ledger Live. It's best to refer them to the article titled 'I Didn’t Receive My Crypto After Swap.'
- Ledger Live doesn't need an email and password, if you're asked for one, you're in the wrong part of the app that's only for Ledger Recover subscribers.
- If you see the exact error "Something went wrong" when sending or receiving coins or tokens from an account, tell the user: "you have the wrong private keys in your Ledger device".

Begin!

"""

# Augment query function
async def augment_query_generated(user_input):
    try:
        messages = [
            {
                "role": "system",
                "content": EXPANDER_PROMPT
            },
            {
                "role": "user", 
                "content": user_input
            }
        ] 

        res = await openai_client.chat.completions.create(
            model="gpt-3.5-turbo-1106",
            #model='gpt-4-1106-preview',
            temperature= 0.0,
            messages=messages,
            timeout=8.0,
        )
        reply = res.choices[0].message.content
        return reply
    except Exception as e:
        print(f"OpenAI couldn't generate an augmented query: {e}")
        no_output = ""
        return no_output

    
# Retrieve and re-rank function
async def retrieve(query, joint_query, locale, user_id, timestamp, user_input):
    # Define context box
    contexts = []

    async with httpx.AsyncClient() as client:
        # Prepare Cohere embeddings
        try:
            # Choose Cohere embeddings model based on locale
            embedding_model = 'embed-multilingual-v3.0' if locale in ['fr', 'ru'] else 'embed-english-v3.0'
            
            # Call the embedding function
            embed_response = await client.post(
                "https://api.cohere.ai/v1/embed",
                json={

                    "texts": [joint_query], 
                    "model": embedding_model, 
                    "input_type": "search_query",

                },
                headers={

                    "Authorization": f"Bearer {cohere_key}"
                },
                timeout=20,
            )

            embed_response.raise_for_status()
            res_embed = embed_response.json()
            xq = res_embed['embeddings']
        
        except Exception as e:
            print(f"Embedding failed: {e}")
            return(e)

        # Example Pinecone query replacement
        try:
            # Pull data chunks from Pinecone
            pinecone_response = await client.post(
                "https://prod-e865e64.svc.northamerica-northeast1-gcp.pinecone.io/query",
                json={

                    "vector": xq, 
                    "topK": 8, 
                    "namespace": locale,
                    "includeValues": False, 
                    "includeMetadata": True

                },
                headers={

                    "Api-Key": pinecone_key,
                    "Accept": "application/json",
                    "Content-Type": "application/json" 

                },
                timeout=25,
            )
            pinecone_response.raise_for_status()
            res_query = pinecone_response.json()

            # Format docs from Pinecone response
            learn_more_text = translations.get(locale, '\n\nLearn more at')
            docs = [{"text": f"{x['metadata']['text']}{learn_more_text}: {x['metadata'].get('source', 'N/A')}"} 
                for x in res_query["matches"]]


        
        except Exception as e:
            print(f"Pinecone query failed: {e}")
            return

        # Try re-ranking with Cohere
        try:
            # Dynamically choose reranker model based on locale
            reranker_model = 'rerank-multilingual-v2.0' if locale in ['fr', 'ru'] else 'rerank-english-v2.0'

            # Rerank docs with Cohere
            rerank_response = await client.post(
                "https://api.cohere.ai/v1/rerank",
                json={

                    "model": reranker_model,
                    "query": query, 
                    "documents": docs, 
                    "top_n": 3,
                    "return_documents": True,

                },
                headers={

                    "Authorization": f"Bearer {cohere_key}",

                },
                timeout=30,
            )
            rerank_response.raise_for_status()
            rerank_docs = rerank_response.json()

            # Process reranked documents
            reranked = rerank_docs['results'][0]['document']['text']
            contexts.append(reranked)

        except Exception as e:
            print(f"Reranking failed: {e}")
            # Fallback to simpler retrieval without Cohere if reranking fails
            res_query = index.query(xq, top_k=2, namespace=locale, include_metadata=True)
            sorted_items = sorted([item for item in res_query['matches'] if item['score'] > 0.50], key=lambda x: x['score'], reverse=True)

            for idx, item in enumerate(sorted_items):
                context = item['metadata']['text']
                context_url = "\nLearn more: " + item['metadata'].get('source', 'N/A')
                context += context_url
                contexts.append(context)

    # Retrieve and format previous conversation history for a specific user_id
    previous_conversations = USER_STATES[user_id].get('previous_queries', [])[-1:]  # Get the last -N conversations

    # Format previous conversations
    previous_conversation = ""
    for conv in previous_conversations:
        previous_conversation += f"User: {conv[0]}\nAssistant: {conv[1]}\n\n"
    
    # Construct the augmented query string with locale, contexts, chat history, and user input
    if locale == 'fr':
        augmented_query = "CONTEXTE: " + "\n\n" + "La date d'aujourdh'hui est: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "HISTORIQUE DU CHAT: \n" +  previous_conversation.strip() + "\n\n" + "Utilisateur: \"" + user_input + "\"\n" + "Assistant: " + "\n"
    elif locale == 'ru':
        augmented_query = "КОНТЕКСТ: " + "\n\n" + "Сегодня: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "ИСТОРИЯ ПЕРЕПИСКИ: \n" +  previous_conversation.strip() + "\n\n" + "Пользователь: \"" + user_input + "\"\n" + "Краткий ответ ассистента: " + "\n"
    else:
        augmented_query = "CONTEXT: " + "\n\n" + "Today is: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "CHAT HISTORY: \n" +  previous_conversation.strip() + "\n\n" + "User: \"" + user_input + "\"\n" + "Assistant's short answer: " + "\n"

    return augmented_query

# RAG function
async def rag(primer, augmented_query):
    async with httpx.AsyncClient() as client:
        try:
            # Request OpenAI completion
            res = await openai_client.chat.completions.create(
                temperature=0.0,
                model='gpt-4',
                #model='gpt-4-1106-preview',
                messages=[

                    {"role": "system", "content": primer},
                    {"role": "user", "content": augmented_query}

                ],
                timeout= 45.0
            )             
            reply = res.choices[0].message.content
            return reply

        except Exception as e:
            print(f"OpenAI completion failed: {e}")
            async with httpx.AsyncClient() as client:
                try:       
                    command_response = await client.post(
                        "https://api.cohere.ai/v1/chat",
                        json={

                            "message": augmented_query,
                            "model": "command",
                            "preamble_override": primer,
                            "temperature": 0.0,

                        },
                        headers={

                            "Authorization": f"Bearer {cohere_key}"

                        },
                        timeout=30.0,

                    )
                    command_response.raise_for_status()
                    rep = command_response.json()

                    # Extract and return chat response
                    cohere_chat = rep['text']
                    return cohere_chat


                except Exception as e:
                    print(f"Snap! Something went wrong, please try again!")
                    return("Snap! Something went wrong, please try again!")
        


######## ROUTES ##########


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
    locale = query.user_locale if query.user_locale in SUPPORTED_LOCALES else "eng"

    # Loading locale-appropriate system prompt
    primer = system_prompts.get(locale, system_prompts["eng"])

    # Create a conversation history for new users
    convo_start = time.time()
    USER_STATES.setdefault(user_id, {
        'previous_queries': [],
        'timestamp': convo_start
    })

    # Apply nonsense filter
    if not user_input or nonsense(user_input):
        return handle_nonsense(locale)
    else:
        try:
            # Set clock
            timestamp = datetime.now().strftime("%B %d, %Y")
 
            # Prepare enriched user query
            hypothetical_answer = await augment_query_generated(user_input)
            joint_query = f"{user_input} {hypothetical_answer}"
            print(joint_query)

            # Start date retrieval and reranking
            augmented_query = await retrieve(user_input, joint_query, locale, user_id, timestamp, user_input)

            # Start RAG
            response = await rag(primer, augmented_query)            

            # Save the response to a thread
            try:
                USER_STATES[user_id] = {
                    'previous_queries': USER_STATES[user_id].get('previous_queries', []) + [(user_input, response)],
                    'timestamp': convo_start
                }

            except Exception as e:
                print("Saving thread failed!")
             
            # Print values for debugging
            print(
                
                "\n\n" + "Query: " + joint_query + "\n\n",
                augmented_query + "\n",
                response + "\n\n"
                  
            )

                                
            # Return response to user
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
