import time
import json
import os
from os import path
import shutil
from dotenv import load_dotenv
import openai
from tqdm.auto import tqdm
import pinecone
import cohere

load_dotenv()


# Initialize Cohere
os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY") 
co = cohere.Client(os.environ["COHERE_API_KEY"])

def read_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    return json_data

def run_updater(json_file_path:str = None, index_name = 'database'):
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

    # Define batch size
    batch_size = 100  # how many embeddings we create and insert at once

    for i in tqdm(range(0, len(documents), batch_size)):
        i_end = min(len(documents), i+batch_size)  # find end of batch
        meta_batch = documents[i:i_end]
        texts = [x['text'] for x in meta_batch]
        
        try:
            res = co.embed(
                texts=texts,
                model='embed-english-v3.0',
                input_type='search_document'
                )
        except Exception:
            time.sleep(240)
            res = co.embed(
                texts=[texts],
                model='embed-english-v3.0',
                input_type='search_document'
                )


        embeds = res.embeddings
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

    # Define output_directory
    output_directory = os.path.join(pinecone_pipeline_root_directory, 'output_files')

    # Delete the output_files directory
    if path.exists(output_directory):
        shutil.rmtree(output_directory)
        print(f"Deleted the folder: {output_directory}")
    else:
        print(f"The folder {output_directory} does not exist.")

if __name__ == "__main__":
    run_updater()