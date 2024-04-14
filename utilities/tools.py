import os
import cohere
import httpx
from openai import AsyncOpenAI


# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']

# Initialize OpenAI client & Embedding model
openai_key = os.environ['OPENAI_API_KEY']
openai_client = AsyncOpenAI(api_key=openai_key)
embed_model = "text-embedding-3-large"

# Initialize Cohere
co = cohere.Client(os.environ["COHERE_API_KEY"])
cohere_key = os.environ["COHERE_API_KEY"]

async def retrieve(user_input, locale):
    # Define context box
    contexts = []

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
            reranker_main = 'rerank-multilingual-v3.0' if locale in ['fr', 'ru'] else '04461047-71d5-4a8e-a984-1916adbcd394-ft' # finetuned on March 11, 2024
            reranker_backup = 'rerank-multilingual-v3.0' if locale in ['fr', 'ru'] else 'rerank-english-v3.0'

            try:# Rerank docs with Cohere
                rerank_response = await client.post(
                    "https://api.cohere.ai/v1/rerank",
                    json={

                        "model": reranker_main,
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
                print(f'Finetuned reranker failed:{e}')
                rerank_response = await client.post(
                    "https://api.cohere.ai/v1/rerank",
                    json={

                        "model": reranker_backup,
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

    return (contexts, docs)

async def rag(primer, timestamp, contexts, locale, concise_query, docs, previous_conversations):

    # Prepare LLMs
    main_llm = 'gpt-4-turbo'
    first_backup_llm = 'gpt-4'
    second_backup_llm = 'command-r'

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
