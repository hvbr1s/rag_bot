import time
import json
import os
from os import path
import shutil
from dotenv import load_dotenv
import openai
from tqdm.auto import tqdm
import pinecone
from openai.error import RateLimitError

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

def read_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    return json_data

def run_updater(json_file_path:str = None, index_name = 'prod'):
    failed_chunks = 0  # Initialize counter for failed chunks
    if not json_file_path:
        pinecone_pipeline_root_directory = os.path.dirname(os.path.dirname(__file__))
        output_folder = os.path.join(pinecone_pipeline_root_directory, 'output_files')
        json_file_path = os.path.join(output_folder, 'output.json')
    documents = read_json_file(json_file_path)
    
    # initialize connection to pinecone
    pinecone.init(
        api_key=os.getenv('PINECONE_API_KEY'),
        environment=os.getenv('PINECONE_ENVIRONMENT')
    )

    # connect to index
    index = pinecone.Index(index_name)

    # define embed model
    embed_model = "text-embedding-ada-002"

    batch_size = 100  # how many embeddings we create and insert at once

    for i in tqdm(range(0, len(documents), batch_size)):
        i_end = min(len(documents), i+batch_size)  # find end of batch
        meta_batch = documents[i:i_end]
        texts = [x['text'] for x in meta_batch]
        
        try:
            res = openai.Embedding.create(input=texts, engine=embed_model)
        except RateLimitError:
            time.sleep(240)
            res = openai.Embedding.create(input=texts, engine=embed_model)

        embeds = [record['embedding'] for record in res['data']]
        
        to_upsert = [{'id': meta['id'], 'values': embed, 'metadata': meta} for meta, embed in zip(meta_batch, embeds)]

        try:
            #index.upsert(vectors=to_upsert, namespace='fr') # use to update the FR database
            index.upsert(vectors=to_upsert, namespace='eng') # use to update the ENG database
        except Exception as e:
            print(f"Failed to upsert the following data: {to_upsert}")
            print(f"Error: {e}")
            failed_chunks += 1  # Increment the counter for each failed chunk
            continue

    print('Database updated!')
    if failed_chunks > 0:  # If there are any failed chunks, print the count
        print(f"Total number of failed chunks: {failed_chunks}")
    index_stats_response = index.describe_index_stats()
    print(index_stats_response)

    # # Delete the output_files directory
    # if path.exists(output_folder):
    #     shutil.rmtree(output_folder)
    #     print(f"Deleted the folder: {output_folder}")
    # else:
    #     print(f"The folder {output_folder} does not exist.")


if __name__ == "__main__":
    run_updater()
