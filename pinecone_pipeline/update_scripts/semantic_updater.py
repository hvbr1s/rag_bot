import time
import json
import os
from dotenv import load_dotenv
from tqdm.auto import tqdm
from pinecone import Pinecone
from openai import OpenAI


load_dotenv()

# Initialize Pinecone client
pinecone_key = os.environ['PINECONE_API_KEY']

# Prod DB
index_name = 'serverless-test'
pc_host = 'https://serverless-test-e865e64.svc.apw5-4e34-81fa.pinecone.io' 
# Backup DB
backup_index_name = 'prod'
backup_pc_host = 'https://prod-e865e64.svc.northamerica-northeast1-gcp.pinecone.io'

pc = Pinecone(api_key=pinecone_key)
index = pc.Index(
        index_name,
        host=pc_host
)
backup_index = pc.Index(
        backup_index_name,
        host=backup_pc_host
)

# Initialize OpenAI client
client = OpenAI()

def read_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    return json_data

def run_updater(json_file_path:str = None):
    failed_chunks = 0  # Initialize counter for failed chunks
    pinecone_pipeline_root_directory = os.path.dirname(os.path.dirname(__file__))
    output_folder = os.path.join(pinecone_pipeline_root_directory, 'output_files')
    if not json_file_path:
        json_file_path = os.path.join(output_folder, 'output.json')
    documents = read_json_file(json_file_path)
    
    # Define batch size
    batch_size = 100  # how many embeddings we create and insert at once

    for i in tqdm(range(0, len(documents), batch_size)):
        i_end = min(len(documents), i+batch_size)  # find end of batch
        meta_batch = documents[i:i_end]
        texts = [x['text'] for x in meta_batch]

        embeds = []
        for text in texts:
            res = client.embeddings.create(
                input=text, 
                model='text-embedding-3-large',
                dimensions=3072
            )
            embeds.extend([r.embedding for r in res.data])

        # Upsert embeddings tp DB
        to_upsert = [{'id': meta['id'], 'values': embed, 'metadata': meta} for meta, embed in zip(meta_batch, embeds)]
        try:
            try: 
                index.upsert(
                    vectors=to_upsert, 
                    namespace='eng'
                ) 
                index_stats_response = index.describe_index_stats()
                print(f'\nMain database updated! -> {index_stats_response}')

                backup_index.upsert(
                    vectors=to_upsert,
                    namespace='eng'
                )
                backup_index_stats_response = backup_index.describe_index_stats()
                print(f'\nBackup database updated! -> {backup_index_stats_response}')
            except:
                print(f'Oops something went wrong, trying again!')
                time.sleep(15)
                index.upsert(
                    vectors=to_upsert, 
                    namespace='eng'
                )
                print(f'Main database updated!')
                backup_index.upsert(
                    vectors=to_upsert,
                    namespace='eng'
                ) 
                print(f'Backup database updated!')
 
        except Exception as e:
            print(f"Failed to upsert the following data: {to_upsert}")
            print(f"Error: {e}")
            failed_chunks += 1  # Increment the counter for each failed chunk
            continue

    if failed_chunks > 0:  # If there are any failed chunks, print the count
        print(f"Total number of failed chunks: {failed_chunks}")

if __name__ == "__main__":
    run_updater()
