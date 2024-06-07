import os
import cohere
from openai import OpenAI
from pinecone import Pinecone
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']
index_name = 'main'
pc_host ="https://main-e865e64.svc.aped-4627-b74a.pinecone.io"
pc = Pinecone(api_key=pinecone_key)
index = pc.Index(
        index_name,
        host=pc_host
    )
# Initialize OpenAI
openai_api_key = os.environ['OPENAI_API_KEY']
client = OpenAI(api_key=openai_api_key)

def get_embedding(link, embed_model="text-embedding-3-large"):
    """
    Retrieve embedding for a given link using OpenAI.
    """
    # Retrieve OpenAI API key from environment variables
    openai_api_key = os.getenv('OPENAI_API_KEY')

    # Check if OpenAI API key is set in environment variables
    if not openai_api_key:
        raise EnvironmentError("OpenAI API key not set")

    # Set OpenAI API key
    # Create embedding for the given link using the specified embedding model
    res_embed = client.embeddings.create(input=[link], model=embed_model)
    # Return the embedding data from the response
    return res_embed.data[0].embedding

def query_pinecone(index, xq):
    """
    Query Pinecone index with a given embedding.
    Returns article ID and title.
    """
    # Query the Pinecone index with the given embedding, requesting the top match with metadata
    res_query = index.query( 
        vector=xq, 
        top_k=1,
        include_metadata=True, 
        namespace='eng'
    )
    # Retrieve the top match from the query result
    match = res_query['matches'][0]
    # Return the article ID and title from the match metadata
    return match['id'], match['metadata']['source']

def main():
    """
    Main function to execute the steps to lookup an article.
    """
    # Set the article title or a bit of text from the article you're looking for
    article_excerpt = "SWAP CRYPTO WITH RANGO EXCHANGE"
    # Get the embedding for the article link
    xq = get_embedding(article_excerpt)
    # Query Pinecone to get the article ID and title using the embedding
    article_id, article_title = query_pinecone(index, xq)

    # Print the title of the article
    print('Title: ' + article_title + "\n" + 'Article ID: ' + article_id)

# Run the main function if the script is executed
if __name__ == "__main__":
    main()