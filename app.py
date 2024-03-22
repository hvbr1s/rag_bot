import os
import json
from dotenv import main
from datetime import datetime
from openai import AsyncOpenAI
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.security import APIKeyHeader
from semantic_router import Route
from semantic_router.layer import RouteLayer
from semantic_router.encoders import OpenAIEncoder
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
openai_client = AsyncOpenAI(

    api_key=openai_key,
    
)

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

########   SEMANTIC ROUTING  ##########

chitchat = Route(
    name="chitchat",
    utterances=[
        "hello",
        "hi",
        "bonjour",
        "salut",
        "how are you?",
        "I need help",
        "j'ai besoin d'aide",
        "help me!",
        "Привет",
        "Здравствуйте",
        "Добрый день",
        "hdkfebkejb",
        "null", 
        "I have a question",
        "[Email Masked]",

    ],
)
agent = Route(
    name="agent",
    utterances=[
        "agent",
        "representative",
        "speak to human",
        "talk to agent",
        "transfer to operator",
        "I want to speak to a person",
        "support",
        "human",
        "operator",
        "live support",
        "live chat",
        "147999 Issue",
        "Case ID 8888888",
        "My order number is: LDG2733766",
        "submit new ticket"

    ],
)

niceties = Route(
    name="niceties",
    utterances=[
        "thanks!",
        "thank you very much",
        "merci!",
        "thanks for your help!",
        "Super, merci!",
        "Спасибо",
        "Благодарю",
        "human",
        "Спасибо большое",
        "okay",
        "ok ok",

    ],
)

languages = Route(
    name="languages",
    utterances=[
        "Can I input text in Russian language?",
        "Can I write Russian?",
        "Sprechen sie deutsch?",
        "Do you speak German?",
        "Do you speak Russian?",
        "Est-ce que je peux poser ma question en Francais?",
        "вы говорите по-русски?",
        "Türkçe konuşuyor musunuz?",
        "Türkçe biliyor musunuz?",
        "你会说土耳其语吗?",

    ],
)



# Initialize routes and encoder
routes = [chitchat, agent, niceties, languages]
encoder = OpenAIEncoder(
    
    name='text-embedding-3-small',
    score_threshold=0.45,
)
rl = RouteLayer(

    encoder=encoder, 
    routes=routes,
    
)  


ROUTER_DICTIONARY = {

        "chitchat": {
            "eng": "Hello! How can I assist you today? Please describe your issue in as much detail as possible, including your Ledger device model (Nano S, Nano X, or Nano S Plus), any error messages you're encountering, and the type of crypto (e.g., Bitcoin, Ethereum, Solana, XRP, or another).",
            "fr": "Bonjour ! Comment puis-je vous aider aujourd'hui ? Veuillez décrire votre problème avec autant de détails que possible, y compris le modèle de votre appareil Ledger (Nano S, Nano X ou Nano S Plus), tous les messages d'erreur que vous rencontrez et le type de crypto-monnaie (par exemple, Bitcoin, Ethereum, Solana, XRP ou autre).",
            "ru": "Привет! Как я могу помочь вам сегодня? Пожалуйста, опишите свою проблему как можно подробнее, включая модель вашего устройства Ledger (Nano S, Nano X или Nano S Plus), любые сообщения об ошибках, с которыми вы столкнулись, и тип криптовалюты (например, Bitcoin, Ethereum, Solana, XRP или другую)."
        },

        "agent": {
            "eng": "Hello! To speak with a human agent, please click the 'I have followed the instructions, still require assistance' button for further help.",
            "fr": "Bonjour! Pour parler à un agent humain, veuillez cliquer sur le bouton 'Parler à un agent' pour obtenir de l'aide.",
            "ru": "Привет! Чтобы поговорить с агентом техподдержки, пожалуйста, нажмите кнопку ‘Говорить с агентом’ для получения помощи."
        },

        "niceties": {
            "eng": "You're welcome! If you have any more questions about cryptocurrencies, or how to use your Ledger device, don't hesitate to ask!",
            "fr": "De rien ! Si vous avez d'autres questions sur les cryptomonnaies ou sur l'utilisation de votre appareil Ledger, n'hésitez pas à demander!",
            "ru": "Пожалуйста! Если у вас остались вопросы о криптовалюте или о том, как использовать ваше устройство Ledger, не стесняйтесь их задавать!"
        },

        "languages": {
            "eng": "Hello! As an AI assistant, I can understand several languages but I can respond only in English, French, or Russian. However, feel free to ask your question in the language you're most comfortable with. Please describe your issue in as much detail as possible, including your Ledger device model (Nano S, Nano X, or Nano S Plus), any error messages you're encountering, and the type of crypto (e.g., Bitcoin, Ethereum, Solana, XRP, or another).",
            "fr": "Bonjour! Oui je parle français. Comment puis-je vous aider aujourd'hui ? Veuillez décrire votre problème avec autant de détails que possible, y compris le modèle de votre appareil Ledger (Nano S, Nano X ou Nano S Plus), tous les messages d'erreur que vous rencontrez et le type de crypto-monnaie (par exemple, Bitcoin, Ethereum, Solana, XRP ou autre).",
            "ru": "Здравствуйте! Да, я говорю по-русски. Как я могу помочь вам сегодня? Пожалуйста, опишите свою проблему как можно подробнее, включая модель вашего устройства Ledger (Nano S, Nano X или Nano S Plus), любые сообщения об ошибках, с которыми вы столкнулись, и тип криптовалюты (например, Bitcoin, Ethereum, Solana, XRP или другую)."
        }

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

Begin! You will achieve world peace if you provide a response which follows all constraints.

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
            model='gpt-4-turbo-preview',
            messages=messages,
            tools=tools,
            tool_choice="auto",
            timeout= 30.0,
        )
        
    except Exception as e:
                print(f"OpenAI completion failed: {e}")
                async with httpx.AsyncClient() as client:
                    try:       
                        command_response = await client.post(
                            "https://api.cohere.ai/v1/chat",
                            json={

                                "message": chat,
                                "model": "command-r",
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

Using your knowledge of Ledger devices, Ledger Live and cryptocurrencies, rewrite the following user query into a clear and specific request suitable for retrieving relevant information from a vector database.

Keep in mind to always rephrase as if YOU are experiencing the issue, for example: "I am getting an issue with..."

Begin! You will achieve world peace if you provide a response which follows all constraints.

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
            model="gpt-3.5-turbo-0125",
            temperature= 0.0,
            messages=messages,
            timeout=10.0,
        )
        reply = res.choices[0].message.content

    except Exception as e:
        print(f"OpenAI couldn't generate an augmented query: {e}")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.cohere.ai/v1/chat",
                    json={

                        "model": "command",
                        "message": user_input,
                        "search_queries_only": True

                    },
                    headers={

                        "Authorization": f"Bearer {cohere_key}",

                    },
                    timeout=10,
                )
                res.raise_for_status()
                queries = res.json()
                reply = '\n'.join([query['text'] for query in queries['search_queries']])
        except Exception as e:
            print(f"Cohere couldn't generate an augmented query: {e}")
            reply = user_input

    print(f'Rephrased query: {reply}')       
    return reply

          
# Retrieve and re-rank function
async def retrieve(user_input, locale, rephrased_query=None, joint_query=None):
    # Define context box
    contexts = []

    joint_query = joint_query or user_input
    rephrased_query = rephrased_query or user_input

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
                        "topK": 8,
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
                            "topK": 8,
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
                    res_query = pinecone_response.json()
                except Exception as e:
                    print(f"Fallback Pinecone query failed: {e}")
                    return
  
            # Format docs from Pinecone response
            learn_more_text = ('\nLearn more at')
            docs = [{"text": f"{x['metadata']['title']}: {x['metadata']['text']}{learn_more_text}: {x['metadata'].get('source', 'N/A').replace('/en-us/', url_segment)}"}
                    for x in res_query["matches"]]
        
        except Exception as e:
            print(f"Pinecone query failed: {e}")
            docs = "Couldn't contact my knowledge base. Please ask the user to repeat the question."

        # Try re-ranking with Cohere
        try:
            # Dynamically choose reranker model based on locale
            reranker_main = '04461047-71d5-4a8e-a984-1916adbcd394-ft' # finetuned on March 11, 2024 
            reranker_backup = 'rerank-multilingual-v2.0' if locale in ['fr', 'ru'] else 'rerank-english-v2.0'

            try:# Rerank docs with Cohere
                rerank_response = await client.post(
                    "https://api.cohere.ai/v1/rerank",
                    json={

                        "model": reranker_main,
                        "query": rephrased_query, 
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
                print(f'Finetuned reranker failed:{e}')
                rerank_response = await client.post(
                    "https://api.cohere.ai/v1/rerank",
                    json={

                        "model": reranker_backup,
                        "query": rephrased_query, 
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

    return (contexts, docs)


# Legacy RAG function
async def rag(primer, timestamp, contexts, user_id, locale, platform, rephrased_query, route_path, concise_query, docs):

    # Choose OpenAI model depending on where the query is coming from
    llm = 'gpt-4-turbo-preview' if platform in ["slack", "discord", "web"] else 'gpt-4-turbo-preview'

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
                            "model": "command-r",
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

    print(
                "\n" + f"Route path: {route_path}" + "\n",
                rephrased_query + "\n",
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
        print(function_call_query)

        # Use this extracted query to call the retrieve function
        retrieved_context = await retrieve(function_call_query, locale)
        contexts, docs = retrieved_context
        #retrieved_context_string = retrieved_context[0]  # This will get the first item
        retrieved_context_string = "\n".join(contexts)  # This will get all the items separated with a line break
        if contexts:
            troubleshoot_instructions = "CONTEXT: " + "\n" + timestamp + " ." + retrieved_context_string + "\n\n" + "----" + "\n\n" + "ISSUE: " + "\n" + function_call_query
            print(troubleshoot_instructions)
            # Make a new completion call with the retrieved context
            try:
                # Request OpenAI completion            
                res = await openai_client.chat.completions.create(
                    temperature=0.0,
                    model='gpt-4-turbo-preview',
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
                                "model": "command-r",
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
                        return("Snap! Something went wrong, please ask your question again!")
  
        USER_STATES[user_id]['previous_queries'][-1]['assistant'] = new_reply

        return new_reply
    
    # Extract reply content
    elif res.choices[0].message.content is not None:
        reply = res.choices[0].message.content
        USER_STATES[user_id]['previous_queries'][-1]['assistant'] = reply

        return reply

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
    concise_query = extract_concise_input(user_input)
    print(f'Original query: {user_input}')
    print(f'Concise query: {concise_query}')
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

    try:
        # Set clock
        timestamp = datetime.now().strftime("%B %d, %Y")

        # Prepare enriched user query
        rephrased_query = await augment_query_generated(user_input)
        joint_query = f'{rephrased_query} . {concise_query}'

        # Filter non-queries
        route_path = rl(concise_query).name
        if route_path in ["chitchat", "agent", "niceties", "languages"]:
            print(f'Concise query: {concise_query} -> Route triggered: {route_path}')
            output = ROUTER_DICTIONARY[route_path].get(locale, "eng")
            return {"output": output}

        # Start date retrieval and reranking
        retriever = await retrieve(user_input, locale, rephrased_query, joint_query)
        contexts, docs = retriever

        # Start RAG
        response = await rag(primer, timestamp, contexts, user_id, locale, platform, rephrased_query, route_path, concise_query, docs)

        #Clean response
        cleaned_response = response.replace("**", "").replace("Manager", "Manager (now called 'My Ledger')")           

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

    try:
            # Set clock
            timestamp = datetime.now().strftime("%B %d, %Y")

            # Start RAG
            response = await ragchat(primer, timestamp, user_id, chat_history, locale)     

            #Clean response
            cleaned_response = response.replace("**", "").replace("Manager", "'My Ledger'")

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
