import os
from dotenv import main
from datetime import datetime
from crewai_tools import tool
from openai import OpenAI, AsyncOpenAI
from pinecone import Pinecone
import cohere

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

@tool("Knowledge Base")
def retriever_tool(query:str) -> str:
    """
    Use this tool to consult your knowledge base when asked a technical question. 
    Always query the tool according to this format: query:{topic}. 
    """
    #Logging
    print(f"...Document retrieval in progress for: {query}...")
    # Define context box
    contexts = []
    # Set clock
    timestamp = datetime.now().strftime("%B %d, %Y")
    # Set locale
    locale = "eng"

    # Define a dictionary to map locales to URL segments
    locale_url_map = {
        "fr": "/fr-fr/",
        "ru": "/ru/",
        "es": "/es/",
        # add other locales as needed
    }

    # Check if the locale is in the map, otherwise default to "/en-us/"
    url_segment = locale_url_map.get(locale, "/en-us/")

    try:            
        # Call the OpenAI embedding function
        res = openai_client.embeddings.create(
            input=query, 
            model='text-embedding-3-large',
        )
        xq = res.data[0].embedding
        
    except Exception as e:
        print(f"Embedding failed: {e}")
        return(e)
    
    # Query Pinecone
    try:
        try:
            # Pull chunks from the serverless Pinecone instance
            res_query = pc_index.query(
                vector=xq,
                top_k=8,
                namespace="eng",
                include_values=True,
                include_metadata=True,
            )

        except Exception as e:
            print(e)
            # Pull chunks from the legacy Pinecone fallback
            print('Serverless response failed, falling back to legacy Pinecone')
            try:
                # Pull chunks from the backup Pinecone instance
                res_query = backup_index.query(
                    vector=xq,
                    top_k=8,
                    namespace="eng",
                    include_values=True,
                    include_metadata=True,
                )

            except Exception as e:
                print(f"Fallback Pinecone query failed: {e}")
                return

        # Format docs from Pinecone response
        learn_more_text = (' Learn more at')
        docs = [f"{x['metadata']['title']}: {x['metadata']['text']}{learn_more_text}: {x['metadata'].get('source', 'N/A').replace('/en-us/', url_segment)}"
        for x in res_query["matches"]]

        
    except Exception as e:
        print(f"Pinecone query failed: {e}")
        return

    # Try re-ranking with Cohere
    try:
        # Dynamically choose reranker model based on locale
        reranker_main = 'rerank-english-v3.0'
        reranker_backup = '04461047-71d5-4a8e-a984-1916adbcd394-ft'

        try:# Rerank docs with Cohere

            rerank_docs = co.rerank(
                model = reranker_main,
                query = query,
                documents = docs,
                top_n = 2,
                return_documents=True
            )

        except Exception as e:
            print(f'Finetuned reranker failed:{e}')
            rerank_docs = co.rerank(
                model = reranker_backup,
                query = query,
                documents = docs,
                top_n = 2,
                return_documents=True
            )

        # Fetch all re-ranked documents
        for result in rerank_docs.results:  # Access the results attribute directly
            reranked = result.document.text  # Access the text attribute of the document
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
    elif locale == 'es':
        augmented_contexts = "La fecha de hoy es: " + timestamp + "\n\n" + "\n\n".join(contexts)
    else:
        augmented_contexts = "Today is: " + timestamp + "\n\n" + "\n\n".join(contexts)

    return augmented_contexts
