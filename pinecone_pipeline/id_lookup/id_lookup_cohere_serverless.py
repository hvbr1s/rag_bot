import os
import cohere
import pinecone
from pinecone import Pinecone
from pinecone.grpc import PineconeGRPC 
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Initialize Pinecone
pinecone_key = os.environ['PINECONE_API_KEY']
index_name = 'serverless-prod'
pc_host ="https://serverless-prod-e865e64.svc.apw5-4e34-81fa.pinecone.io"
pc = Pinecone(api_key=pinecone_key)
index = pc.Index(
        index_name,
        host=pc_host
    )

def get_embedding(input, model="embed-english-v3.0", input_type='search_query' ):
    """
    Retrieve embedding for a given link using OpenAI.
    """
    # Initialize Cohere
    os.environ["COHERE_API_KEY"] = os.getenv("COHERE_API_KEY") 
    co = cohere.Client(os.environ["COHERE_API_KEY"])

    # Check if OpenAI API key is set in environment variables
    if not co:
        raise EnvironmentError("Cohere API key not set")

    # Create embedding for the given link using the specified embedding model
    res_embed = co.embed(
                texts=[input],
                model=model,
                input_type=input_type
                )
    # Return the embedding data from the response
    return res_embed.embeddings

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
    title = "WINDOWS HELLO"
    # Get the embedding for the article link
    xq = get_embedding(title)
    # Query Pinecone to get the article ID and title using the embedding
    article_id, article_title = query_pinecone(index, xq)

    # Print the title of the article
    print('Title: ' + article_title + "\n" + 'Article ID: ' + article_id)

# Run the main function if the script is executed
if __name__ == "__main__":
    main()