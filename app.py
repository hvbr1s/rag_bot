import os
import json
from dotenv import main
from datetime import datetime
from pinecone import Pinecone
from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException, status, Depends
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
    platform: str | None = None

# Define FastAPI app
app = FastAPI()

# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']
# index_name = 'serverless-test'
# pc_host ="https://serverless-test-e865e64.svc.apw5-4e34-81fa.pinecone.io"
# pc = Pinecone(api_key=pinecone_key)
# index = pc.Index(
#         index_name,
#         host=pc_host
#     )

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

# Set up tooling 
tools = [
{
    "type": "function",
    "function": {
    "name": "knowledge",
    "description": "Technical Question API, this API makes a POST request to an external Knowledge Base with a technical question.",
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
        "implementation": "async def knowledge(query):"
    }
    }
}
]

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

# Funtion to clean bolding from Bot's response
async def remove_double_asterisks(response):
    return response.replace("**", "")

# Function to investigate user issue
INVESTIGATOR_PROMPT = """

You are LedgerBot, an expert in cryptocurrency and helpful virtual assistant designed to support Ledger and technical queries through API integration. 
                    
When a user asks any question about Ledger products or anything related to Ledger's ecosystem, you will ALWAYS use your "Knowledge Base" tool to initiate an API call to an external service.

Before utilizing your API retrieval tool, it's essential to first understand the user's issue. This requires asking follow-up questions. 
    
Here are key points to remember:

1- Check the CHAT HISTORY to ensure the conversation doesn't exceed 4 exchanges between you and the user before calling your "Knowledge Base" API tool.
2- ALWAYS ask if the user is getting an error message.
3- NEVER request crypto addresses or transaction hashes/IDs.
4- NEVER ask the same question twice
5- If the user mention their Ledger device, always clarify whether they're talking about the Nano S, Nano X or Nano S Plus.
6- For issues related to a cryptocurrency, always inquire about the specific crypto coin or token involved and if the coin/token was transferred from an exchange. especially if the user hasn't mentioned it.
7- For issues related to withdrawing/sending crypto from an exchange (such as Binance, Coinbase, Kraken, etc) to a Ledger wallet, always inquire which coins or token was transferred and which network the user selected for the withdrawal (Ethereum, Polygon, Arbitrum, etc).
8- For connection issues, it's important to determine the type of connection the user is attempting. Please confirm whether they are using a USB or Bluetooth connection. Additionally, inquire if the connection attempt is with Ledger Live or another application. If they are using Ledger Live, ask whether it's on mobile or desktop and what operating system they are using (Windows, macOS, Linux, iPhone, Android).
9- For issues involving a swap, it's crucial to ask which swap service the user used (such as Changelly, Paraswap, 1inch, etc.). Also, inquire about the specific cryptocurrencies they were attempting to swap (BTC/ETH, ETH/SOL, etc)
10 For issues related to staking, always ask the user which staking service they're using.
    
After the user replies and even if you have incomplete information, you MUST summarize your interaction and call your 'Knowledge Base' API tool. This approach helps maintain a smooth and effective conversation flow.

ALWAYS summarize the issue as if you were the user, for example: "My issue is ..."

If a user needs to contact Ledger Support, they can do so at https://support.ledger.com/

NEVER use your API tool when a user simply thank you or greet you!

Take a deep breath, I'll tip you $200 dollars if you do a good job!

"""

async def chat(chat):
    # Define the initial messages with the system's instructions
    messages = [
        {"role": "system", "content":INVESTIGATOR_PROMPT},
        {"role": "user", "content": chat}
    ]
    try:
        # Call the API to get a response
        res = await openai_client.chat.completions.create(
            temperature=0.0,
            model='gpt-4-1106-preview',
            #model='gpt-3.5-turbo-1106',
            messages=messages,
            tools=tools,
            tool_choice="auto",
            timeout= 30.0
        )
        
    except Exception as e:
                print(f"OpenAI completion failed: {e}")
                async with httpx.AsyncClient() as client:
                    try:       
                        command_response = await client.post(
                            "https://api.cohere.ai/v1/chat",
                            json={

                                "message": chat,
                                "model": "command",
                                "preamble_override": INVESTIGATOR_PROMPT,
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
                        res = rep['text']
                        
                    except Exception as e:
                        print(f"Snap! Something went wrong, please try again!")
                        return("Snap! Something went wrong, please try again!")
    return res

# Function to expand the user's question:
EXPANDER_PROMPT = """

You are a helpful expert crypto research assistant working for Ledger, the crypto hardware wallet company,

Your role is to provide technical answers to queries from Ledger customers seeking assistance.

Customers might reach out about a technical issue with the Ledger Live app on mobile or desktop, or an issue with their Ledger device (Nano S, Nano X or Nano S Plus) or an issue with an order from the Ledger store.

For each query, give one SHORT answer based on your knowledge of cryptocurrency, blockchain, Ledger devices and the Ledger Live app.

Take a deep breath, begin!

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
async def retrieve(user_input, locale, joint_query):
    # Define context box
    contexts = []

    if joint_query == '':
        joint_query = user_input

    # Define a dictionary to map locales to URL segments
    locale_url_map = {
        "fr": "/fr-fr/",
        "ru": "/ru/",
        # add other locales as needed
    }

    # Check if the locale is in the map, otherwise default to "/en-us/"
    url_segment = locale_url_map.get(locale, "/en-us/")

    try:            
            # Call the OpenAI embedding function
            res = await openai_client.embeddings.create(
                input=joint_query, 
                model='text-embedding-3-large',
                dimensions=3072
            )
            xq = res.data[0].embedding
        
    except Exception as e:
            print(f"Embedding failed: {e}")
            return(e)

 # Query Pinecone
    async with httpx.AsyncClient() as client:
        try:
            try:
                # Pull chunks from the serverless Pinecone instance
                pinecone_response = await client.post(
                    "https://serverless-test-e865e64.svc.apw5-4e34-81fa.pinecone.io/query",
                    json={

                        "vector": xq, 
                        "topK": 5,
                        "namespace": "eng", 
                        "includeValues": True, 
                        "includeMetadata": True

                    },
                    headers={

                        "Api-Key": pinecone_key,
                        "Accept": "application/json",
                        "Content-Type": "application/json" 

                    },
                    timeout=8,
                )
                pinecone_response.raise_for_status()
                res_query = pinecone_response.json()

            except Exception as e:
                print(e)
                # Pull chunks from the legacy Pinecone fallback
                print('Serverless response failed, falling back to legacy Pinecone')
                try:
                    pinecone_response = await client.post(
                        "https://prod-e865e64.svc.northamerica-northeast1-gcp.pinecone.io/query",
                        json={

                            "vector": xq, 
                            "topK": 5,
                            "namespace": "eng", 
                            "includeValues": True, 
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
                    print(pinecone_response)
                    res_query = pinecone_response.json()
                except Exception as e:
                    print(f"Fallback Pinecone query failed: {e}")
                    return
  
            # Format docs from Pinecone response
            learn_more_text = ('\n\nLearn more at')
            docs = [{"text": f"{x['metadata']['title']}: {x['metadata']['text']}{learn_more_text}: {x['metadata'].get('source', 'N/A').replace('/en-us/', url_segment)}"}
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
                    "query": user_input, 
                    "documents": docs, 
                    "top_n": 2,
                    "return_documents": True,

                },
                headers={

                    "Authorization": f"Bearer {cohere_key}",

                },
                timeout=30,
            )
            rerank_response.raise_for_status()
            rerank_docs = rerank_response.json()

            # Fetch all re-ranked documents
            for result in rerank_docs['results']:
                reranked = result['document']['text']
                contexts.append(reranked)

        except Exception as e:
            print(f"Reranking failed: {e}")
            # Fallback to simpler retrieval without Cohere if reranking fails

            sorted_items = sorted([item for item in res_query['matches'] if item['score'] > 0.70], key=lambda x: x['score'], reverse=True)

            for idx, item in enumerate(sorted_items):
                context = item['metadata']['text']
                context_url = "\nLearn more: " + item['metadata'].get('source', 'N/A')
                context += context_url
                contexts.append(context)

    return contexts


# Legacy RAG function
async def rag(primer, timestamp, contexts, user_id, locale, user_input, platform, joint_query):

    # Choose OpenAI model depending on where the query is coming from
    llm = 'gpt-4-1106-preview' if platform in ["slack", "discord", "other"] else 'gpt-4-1106-preview'

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
        augmented_query = "КОНТЕКСТ: " + "\n\n" + "Сегодня: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "ИСТОРИЯ ПЕРЕПИСКИ: \n" +  previous_conversation.strip() + "\n\n" + "Пользователь: \"" + user_input + "\"\n" + "Ассистента: " + "\n"
    else:
        augmented_query = "CONTEXT: " + "\n\n" + "Today is: " + timestamp + "\n\n" + "\n\n".join(contexts) + "\n\n######\n\n" + "CHAT HISTORY: \n" +  previous_conversation.strip() + "\n\n" + "User: \"" + user_input + "\"\n" + "Assistant: " + "\n"

    try:
        
        res = await openai_client.chat.completions.create(
            temperature=0.0,
            model=llm,
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
                model='gpt-4',
                messages=[

                    {"role": "system", "content": primer},
                    {"role": "user", "content": augmented_query}

                ],
                timeout= 45.0
            )             
            reply = res.choices[0].message.content

        except Exception as e:
            print(f"GPT4 completion failed: {e}")

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
                    reply= rep['text']
                

                except Exception as e:
                    print(f"Snap! Something went wrong, please try again!")
                    return("Snap! Something went wrong, please try again!")

    print(
                joint_query + "\n",
                augmented_query + "\n",
                reply + "\n\n"
                  
    )
    return reply

# RAG Chat Function
async def ragchat(primer, timestamp, user_id, chat_history, locale):

    res = await chat(chat_history)

    # Check for tool_calls in the response
    if res.choices[0].message.tool_calls is not None:
        print("Calling API!")
        tool_call_arguments = json.loads(res.choices[0].message.tool_calls[0].function.arguments)

        # Extract query
        function_call_query = tool_call_arguments["query"]

        # Use this extracted query to call the retrieve function
        retrieved_context = await retrieve(function_call_query, locale, joint_query='')
        #retrieved_context_string = retrieved_context[0]  # This will get the first item
        retrieved_context_string = "\n".join(retrieved_context)  # This will get all the items separated with a line break
        if retrieved_context:
            troubleshoot_instructions = "CONTEXT: " + "\n" + timestamp + " ." + retrieved_context_string + "\n\n" + "----" + "\n\n" + "ISSUE: " + "\n" + function_call_query
            print(troubleshoot_instructions)
            # Make a new completion call with the retrieved context
            try:
                # Request OpenAI completion            
                res = await openai_client.chat.completions.create(
                    temperature=0.0,
                    #model='gpt-4',
                    model='gpt-4-1106-preview',
                    messages=[

                        {"role": "system", "content": primer},
                        {"role": "user", "content": troubleshoot_instructions}

                    ],
                    timeout= 45.0
                )             
                new_reply = res.choices[0].message.content
        
            except Exception as e:
                print(f"OpenAI completion failed: {e}")
                async with httpx.AsyncClient() as client:
                    try:       
                        command_response = await client.post(
                            "https://api.cohere.ai/v1/chat",
                            json={

                                "message": troubleshoot_instructions,
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
                        new_reply = rep['text']
                        
                    except Exception as e:
                        print(f"Snap! Something went wrong, please try again!")
                        return("Snap! Something went wrong, please try again!")
  
        USER_STATES[user_id]['previous_queries'][-1]['assistant'] = new_reply

        return new_reply
    
    # Extract reply content
    elif res.choices[0].message.content is not None:
        reply = res.choices[0].message.content
        USER_STATES[user_id]['previous_queries'][-1]['assistant'] = reply

        return reply



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
    platform = query.platform

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

            # Start date retrieval and reranking
            contexts = await retrieve(user_input, locale, joint_query)

            # Start RAG
            response = await rag(primer, timestamp, contexts, user_id, locale, user_input, platform, joint_query)

            #Clean response
            cleaned_response = await remove_double_asterisks(response)            

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
        
# RAGChat route
@app.post('/chat') 
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

    USER_STATES[user_id]['previous_queries'].append({'user': user_input})
    previous_conversations = USER_STATES[user_id]['previous_queries'][-4:]

    # Format previous conversations for RAG
    formatted_history = ""
    for conv in previous_conversations:
        formatted_history += f"User: {conv.get('user', '')}\nAssistant: {conv.get('assistant', '')}\n"

    # Construct the query string with complete chat history
    chat_history = f"CHAT HISTORY: \n\n{formatted_history.strip()}"

    # Apply nonsense filter
    if not user_input or nonsense(user_input):
        return handle_nonsense(locale)

    else:
        try:
            # Set clock
            timestamp = datetime.now().strftime("%B %d, %Y")

            # Start RAG
            response = await ragchat(primer, timestamp, user_id, chat_history, locale)     

            #Clean response
            cleaned_response = await remove_double_asterisks(response)

            # Print for debugging
            print(
                
                chat_history + "\n",
                response + "\n\n"
                  
            )          
                            
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
