import os
from dotenv import main
from datetime import datetime
from openai import OpenAI, AsyncOpenAI
from pinecone import Pinecone
import cohere
import httpx

# Initialize environment variables
main.load_dotenv()
# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']
pc = Pinecone(
    api_key=pinecone_key,
)
pc_index = pc.Index("main")
backup_index= pc.Index("backup")
# Initialize Cohere
cohere_key = os.environ["COHERE_API_KEY"]
co = cohere.Client(cohere_key)
# Initialize OpenAI client & Embedding model
openai_key = os.environ['OPENAI_API_KEY']
openai_client = OpenAI(api_key=openai_key)
async_client = AsyncOpenAI(api_key=openai_key)

async def simple_retrieve(user_input):
    # Define context box
    contexts = []
    # Define locale
    locale = "eng"
     # Set clock
    timestamp = datetime.now().strftime("%B %d, %Y")

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
            res = await async_client.embeddings.create(
                input=user_input, 
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
                    "https://main-e865e64.svc.aped-4627-b74a.pinecone.io/query",
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
                        "https://backup-e865e64.svc.eu-west4-gcp.pinecone.io/query",
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
            reranker_main = 'rerank-english-v3.0' # finetuned in May, 2024 
            reranker_backup = '04461047-71d5-4a8e-a984-1916adbcd394-ft'

            try:# Rerank docs with Cohere
                rerank_response = await client.post(
                    "https://api.cohere.ai/v1/rerank",
                    json={

                        "model": reranker_main,
                        "query": user_input, 
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
                        "query": user_input, 
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

        # Construct the augmented query string with locale, contexts, chat history, and user input
        if locale == 'fr':
            augmented_contexts = "La date d'aujourdh'hui est: " + timestamp + "\n\n" + "\n\n".join(contexts)
        elif locale == 'ru':
            augmented_contexts = "Сегодня: " + timestamp + "\n\n" + "\n\n".join(contexts)
        else:
            augmented_contexts = "Today is: " + timestamp + "\n\n" + "\n\n".join(contexts)

    return augmented_contexts
