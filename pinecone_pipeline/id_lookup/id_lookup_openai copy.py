import os
from openai import OpenAI

client = OpenAI(api_key=openai_api_key)
import pinecone
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

def init_pinecone():
    """
    Initialize Pinecone with API key and environment from environment variables.
    Returns a Pinecone Index instance.
    """
    # Retrieve Pinecone API key and environment from environment variables
    api_key = os.getenv('PINECONE_API_KEY')
    environment = os.getenv('PINECONE_ENVIRONMENT')

    # Check if the necessary environment variables are set
    if not api_key or not environment:
        raise EnvironmentError("Pinecone API key or environment not set")

    # Initialize Pinecone with the retrieved API key and environment
    pinecone.init(api_key=api_key, environment=environment)
    # Return a Pinecone Index instance with the name 'personal'
    return pinecone.Index('prod')

def get_embedding(link, embed_model="text-embedding-ada-002"):
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
    res_embed = client.embeddings.create(input=[link], engine=embed_model)
    # Return the embedding data from the response
    return res_embed['data'][0]['embedding']

def query_pinecone(index, xq):
    """
    Query Pinecone index with a given embedding.
    Returns article ID and title.
    """
    # Query the Pinecone index with the given embedding, requesting the top match with metadata
    res_query = index.query(xq, top_k=1, include_metadata=True, namespace='eng')
    # Retrieve the top match from the query result
    match = res_query['matches'][0]
    # Return the article ID and title from the match metadata
    return match['id'], match['metadata']['source']

def main():
    """
    Main function to execute the steps to delete an article.
    """
    # Initialize Pinecone and get the index instance
    index = init_pinecone()

    # Set the article title or a bit of text from the article you're looking for
    title = "HOW TO CONNECT TO DAPPS WITH LEDGER EXTENSION"
    # Get the embedding for the article link
    xq = get_embedding(title)
    # Query Pinecone to get the article ID and title using the embedding
    article_id, article_title = query_pinecone(index, xq)

    # Print the title of the article to be deleted
    print('Title: ' + article_title + "\n" + 'Article ID: ' + article_id)

# Run the main function if the script is executed
if __name__ == "__main__":
    main()