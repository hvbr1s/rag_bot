import pinecone
import time
import os
from dotenv import load_dotenv

load_dotenv()
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY')
PINECONE_ENVIRONMENT = os.getenv('PINECONE_ENVIRONMENT')

def reboot_index(index_name: str = 'prod'):
    # initialize connection to pinecone
    pinecone.init(
        api_key=PINECONE_API_KEY,
        environment=PINECONE_ENVIRONMENT
    )

    if index_name in pinecone.list_indexes():
        # Try to delete the index if it exists
        print(f'{index_name} deletion initiated...\n')
        pinecone.delete_index(
            index_name,
            timeout=60
        )
        print(f'{index_name} deleted!\n')

    # Now, check if index exists (it shouldn't if deleted successfully)
    assert index_name not in pinecone.list_indexes(), "Something went wrong.  Index still exists but it should have been deleted."
    
    # If it doesn't exist, create the index
    print(f'{index_name} creation initiated...\n')
    pinecone.create_index(
        index_name,
        dimension=1536,
        metric='cosine',
        timeout=200
    )
    print(index_name + ' created!')

if __name__ == "__main__":
    reboot_index()