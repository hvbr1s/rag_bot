import os
import json
from dotenv import main
from datetime import datetime
import pinecone
from openai import OpenAI
from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.security import APIKeyHeader
from nostril import nonsense
import tiktoken
import re
import time
import cohere
from typing import NamedTuple
import asyncio


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

# Initialize Pinecone
pinecone.init(api_key=os.environ['PINECONE_API_KEY'], environment=os.environ['PINECONE_ENVIRONMENT'])
pinecone.whoami()
index_name = 'prod'
index = pinecone.Index(index_name)

# Initialize OpenAI client & Embedding model
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
embed_model = "text-embedding-ada-002"

# Initialize Cohere
os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY") 
co = cohere.Client(os.environ["COHERE_API_KEY"])

# Initialize email address detector
email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
def find_emails(text):  
    return re.findall(email_pattern, text)

# Set up address filters:
EVM_ADDRESS_PATTERN = r'\b0x[a-fA-F0-9]{40}\b'
BITCOIN_ADDRESS_PATTERN = r'\b(1|3)[1-9A-HJ-NP-Za-km-z]{25,34}\b|bc1[a-zA-Z0-9]{25,90}\b'
LITECOIN_ADDRESS_PATTERN = r'\b(L|M)[a-km-zA-HJ-NP-Z1-9]{26,34}\b'
DOGECOIN_ADDRESS_PATTERN = r'\bD{1}[5-9A-HJ-NP-U]{1}[1-9A-HJ-NP-Za-km-z]{32}\b'
XRP_ADDRESS_PATTERN = r'\br[a-zA-Z0-9]{24,34}\b'
COSMOS_ADDRESS_PATTERN = r'\bcosmos[0-9a-z]{38,45}\b'
SOLANA_ADDRESS_PATTERN= r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
CARDANO_ADDRESS_PATTERN = r'\baddr1[0-9a-z]{58}\b'


# Initialize tokenizer and create length function
tokenizer = tiktoken.get_encoding('cl100k_base')
def tiktoken_len(text):
    tokens = tokenizer.encode(
        text,
        disallowed_special=()
    )
    return len(tokens)

# Define FastAPI app
app = FastAPI()

# Initialize user state and periodic cleanup function
user_states = {}
TIMEOUT_SECONDS = 600  # 10 minutes

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
            user_id for user_id, state in user_states.items()
            if current_time - state['timestamp'] > TIMEOUT_SECONDS
        ]
        for user_id in expired_users:
            try:
                del user_states[user_id]
                print("User state deleted!")
            except Exception as e:
                print(f"Error during cleanup for user {user_id}: {e}")
    except Exception as e:
        print(f"General error during cleanup: {e}")


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
async def react_description(query: Query, request: Request, api_key: str = Depends(get_api_key)):
    user_id = query.user_id
    user_input = query.user_input.strip()
    locale = query.user_locale if query.user_locale in SUPPORTED_LOCALES else "eng"

    # Load localized system prompt
    def load_sysprompt(locale):
        filename = f'system_prompt_{locale}.txt'
        try:
            with open(filename, 'r') as sys_file:
                return sys_file.read()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"System primer file for {locale} not found")
    primer = load_sysprompt(locale)

    # load classifier system prompt
    def load_categories():
        filecat = f'classifier_prompt.txt'
        try:
            with open(filecat, 'r') as categories:
                return categories.read()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"Categories not found!")
        
    classifier_prompt = load_categories()

    # Create a conversation history for new users
    if user_id not in user_states:
        user_states[user_id] = {
            'previous_queries': [],
            'timestamp': time.time()
        }

    # Filter out nonsense queries
    if not user_input or nonsense(user_input):
        print('Nonsense detected!')
        if locale == 'fr':
            return {'output': "Je suis désolé, je n'ai pas compris votre question et je ne peux pas aider avec des questions qui incluent des adresses de cryptomonnaie. Pourriez-vous s'il vous plaît fournir plus de détails ou reformuler sans l'adresse ? N'oubliez pas, je suis ici pour aider avec toute demande liée à Ledger."}
        elif locale == 'ru':
            return {'output': "Извините, я не могу понять ваш вопрос, и я не могу помочь с вопросами, содержащими адреса криптовалют. Не могли бы вы предоставить более подробную информацию или перефразировать вопрос без упоминания адреса? Помните, что я готов помочь с любыми вопросами, связанными с Ledger."}
        else: 
            return {'output': "I'm sorry, I didn't quite get your question, and I can't assist with questions that include cryptocurrency addresses. Could you please provide more details or rephrase it without the address? Remember, I'm here to help with any Ledger-related inquiries."}
  
    # Filter out crypto addresses
    if re.search(EVM_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(BITCOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(LITECOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(DOGECOIN_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(COSMOS_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(CARDANO_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(SOLANA_ADDRESS_PATTERN, user_input, re.IGNORECASE) or \
           re.search(XRP_ADDRESS_PATTERN, user_input, re.IGNORECASE):
        if locale == 'fr':
            return {'output': "Je suis désolé, mais je ne peux pas aider avec des questions qui incluent des adresses de cryptomonnaie. Veuillez retirer l'adresse et poser la question à nouveau."}
        elif locale == 'ru':
            return {'output':"Извините, но я не могу помочь с вопросами, которые включают адреса счетов криптовалюты. Пожалуйста, удалите адрес из вашего запроса и напишите ваш запрос еще раз."}
        else:
            return {'output':"I'm sorry, but I can't assist with questions that include cryptocurrency addresses. Please remove the address and ask again"}
    
    # Filter out emails
    if re.search(email_pattern, user_input):
        if locale == 'fr':
            return {'output': "Je suis désolé, mais je ne peux pas aider avec des questions qui incluent des adresses e-mail. Veuillez retirer l'adresse et poser la question à nouveau."}
        elif locale == 'ru':
            return {'output':"Извините, но я не могу ответить на вопросы, содержащие адреса электронной почты. Пожалуйста, удалите адрес электронной почты и задайте вопрос снова."}
        else:
            return{'output': "I'm sorry, but I can't assist with questions that include email addresses. Please remove the address and ask again."}
         
    else:
        
        try:

            # Set clock
            todays_date = datetime.now().strftime("%B %d, %Y")
            #timestamp = datetime.now().strftime("%B %d, %Y %H:%M:%S")
     
            try:
                resp = client.chat.completions.create(
                    temperature=0.0,
                    model='gpt-3.5-turbo',
                    seed=0,
                    messages=[
                        {"role": "system", "content": classifier_prompt},
                        {"role": "user", "content": user_input}
                    ],
                    timeout=5.0,
                    max_tokens=50,
                )
                category = resp.choices[0].message.content.lower()

                # Define message based on locale
                messages = {
                    'eng': 'My issue seems to be with ',
                    'fr': 'Mon problème semble être lié à ',
                    'ru': 'Моя проблема, кажется, связана с '
                }
                message = messages.get(locale, 'My issue seems to be with ')
                # Construct the issue and enriched issue
                my_issue = message + category
                print(my_issue)
                enriched_issue = my_issue + ". " + user_input

                # Filter greetings and request for human support
                server_responses = {
                    "greetings": {
                        "fr": "Bonjour ! Comment puis-je vous aider avec vos problèmes liés à Ledger aujourd'hui ? Plus vous partagerez de détails sur votre problème, mieux je pourrai vous assister. ",
                        "ru": "Здравствуйте! Как я могу помочь вам с вашими вопросами, связанными с Ledger, сегодня? Чем больше деталей вы предоставите о вашей проблеме, тем лучше я смогу вам помочь. Пожалуйста, опишите её максимально подробно!",
                        "eng": "Hello! How can I assist you with your Ledger-related issue today? The more details you share about the problem, the better I can assist you. Feel free to describe it in as much detail as possible!"
                    },
                    "help": {
                        "fr": "Bonjour ! Comment puis-je vous aider avec vos problèmes liés à Ledger aujourd'hui ? Plus vous partagerez de détails sur votre problème, mieux je pourrai vous assister. ",
                        "ru": "Здравствуйте! Как я могу помочь вам с вашими вопросами, связанными с Ledger, сегодня? Чем больше деталей вы предоставите о вашей проблеме, тем лучше я смогу вам помочь. Пожалуйста, опишите её максимально подробно!",
                        "eng": "Hello! How can I assist you with your Ledger-related issue today? The more details you share about the problem, the better I can assist you. Feel free to describe it in as much detail as possible!"
                    },
                    "agent": {
                        "fr": "Pour parler à quelqu'un du support Ledger, cliquez simplement sur le bouton 'Parler à un agent'. Bonne journée !",
                        "ru": "Конечно, чтобы поговорить с кем-то из службы поддержки Ledger, просто нажмите кнопку 'Поговорить с агентом'. Хорошего дня!",
                        "eng": "Certainly! To speak with someone from Ledger Support, just click on the 'Speak to an Agent' button. Have a great day!"
                    }
                }

                # Use the dictionary to get the response
                if category and category in server_responses:
                    return {"output": server_responses[category].get(locale, server_responses[category]["eng"])}

            except Exception as e:
                print(f"An error occurred: {e}")
                enriched_issue = user_input
                print("Error in categorization")

            #############
                       
            async def retrieve(query, contexts=None):
                # Define context box
                contexts = []

                # Prepare Cohere embeddings 
                try:
                 # Choose the model based on the locale
                    model = 'embed-multilingual-v3.0' if locale in ['fr', 'ru'] else 'embed-english-v3.0'

                    # Call the embedding function
                    res_embed = co.embed(
                        texts=[enriched_issue],
                        model=model,
                        input_type='search_query'
                    )
                # Catch errors
                except Exception as e:
                    print(f"Embedding failed: {e}")

                # Grab the embeddings from the response object
                xq = res_embed.embeddings

                # Prepare re-ranking with Cohere
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
                    reranker_model = 'rerank-multilingual-v2.0' if locale in ['fr', 'ru'] else 'rerank-english-v2.0'
                    print(reranker_model)
                    rerank_docs = co.rerank(
                        query=enriched_issue, 
                        documents=docs.keys(), 
                        top_n=2, 
                        model=reranker_model
                    )
                    reranked = rerank_docs[0].document["text"]

                    # Construct the contexts
                    contexts.append(reranked)

                except Exception as e:
                    print(f"Reranking failed: {e}")

                    # Fallback to simpler retrieval without Cohere if reranking fails
                    res_query = index.query(xq, top_k=2, namespace=locale, include_metadata=True)
                    sorted_items = sorted([item for item in res_query['matches'] if item['score'] > 0.50], key=lambda x: x['score'], reverse=True)

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
                    augmented_query = "CONTEXTE: " + "\n\n" + "La date d'aujourdh'hui est: " + todays_date + "\n\n" + "\n\n".join(contexts) + "\n\n-----\n\n" + "HISTORIQUE DU CHAT: \n" +  previous_conversation.strip() + "\n\n-----\n\n" + "Utilisateur: \"" + enriched_issue + "\"\n" + "Assistant: " + "\n"
                elif locale == 'ru':
                    augmented_query = "КОНТЕКСТ: " + "\n\n" + "Сегодня: " + todays_date + "\n\n" + "\n\n".join(contexts) + "\n\n-----\n\n" + "ИСТОРИЯ ПЕРЕПИСКИ: \n" +  previous_conversation.strip() + "\n\n-----\n\n" + "Пользователь: \"" + enriched_issue + "\"\n" + "Краткий ответ ассистента: " + "\n"
                else:
                    augmented_query = "CONTEXT: " + "\n\n" + "Today is: " + todays_date + "\n\n" + "\n\n".join(contexts) + "\n\n-----\n\n" + "CHAT HISTORY: \n" +  previous_conversation.strip() + "\n\n-----\n\n" + "User: \"" + enriched_issue + "\"\n" + "Assistant's short answer: " + "\n"

                return augmented_query

            # Start Retrieval        
            augmented_query = await retrieve(enriched_issue)
            print(augmented_query)

            # Request and return OpenAI RAG
            async def rag(query, contexts=None):

                try: 
                    res = client.chat.completions.create(
                        temperature=0.0,
                        model='gpt-4',
                        #model='gpt-4-1106-preview',
                        messages=[
                            {"role": "system", "content": primer},
                            {"role": "user", "content": augmented_query}
                    ])             
                    reply = res.choices[0].message.content
                    return reply
                
                except Exception as e:
                    print(f"OpenAI completion failed: {e}")
                    
                    # Fallback on Cohere chat model:
                    try:
                        res = co.chat(
                            message=augmented_query,
                            model='command',
                            preamble_override=primer,
                            temperature=0.0,
                        )
                        reply = res.text
                        return reply                   
                    except Exception as e:
                        print(f"Snap! Something went wrong, please try again!")
                        return("Snap! Something went wrong, please try again!")
            
            # Start RAG
            response = await rag(augmented_query)
                                   
            # Save the response to a thread
            user_states[user_id] = {
                'previous_queries': user_states[user_id].get('previous_queries', []) + [(user_input, response)],
                'timestamp': time.time()
            }

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
