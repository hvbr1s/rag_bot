import requests
import json
import os
from dotenv import load_dotenv

# Initialize environment variables
load_dotenv()

# Typesense API key and search endpoint
typesense_api_key = os.getenv("ADMIN_API_KEY")
search_endpoint = "https://07guspnvcq5mlx1wp-1.a1.typesense.net/collections/help_center/documents/search"

# Search parameters
search_params = {
    'q': 'Metamask',  # Replace with your actual search query
    'query_by': 'title,text',  # Fields to search in
    # Add other search parameters as needed
}

# Headers for the request
headers = {
    'X-TYPESENSE-API-KEY': typesense_api_key
}

# Make the GET request
response = requests.get(search_endpoint, headers=headers, params=search_params)

# Check the response
if response.status_code == 200:
    print("Search Results:")
    print(response.json())  # This will print the search results
else:
    print(f"Error: {response.status_code}, {response.text}")