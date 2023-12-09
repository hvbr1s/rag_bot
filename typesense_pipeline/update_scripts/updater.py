import requests
import json
import os
from dotenv import load_dotenv

# Initialize environment variables
load_dotenv()


# Function to convert JSON to JSONL (JSON Lines)
def json_to_jsonl(json_file):
    with open(json_file, 'r') as f:
        data = json.load(f)
    jsonl_data = '\n'.join(json.dumps(record) for record in data)
    return jsonl_data

# Your Typesense API Key and the endpoint
typesense_api_key = os.getenv("ADMIN_API_KEY")
#endpoint = "https://07guspnvcq5mlx1wp-1.a1.typesense.net/collections/help_center/documents/import?action=create"
endpoint = "https://07guspnvcq5mlx1wp-1.a1.typesense.net/collections/help_center_articles/documents/import?action=create"

# Convert your JSON file to JSONL
jsonl_data = json_to_jsonl('/home/danledger/knowledge_bot/typesense_pipeline/output_files/ts_output.json')

# Headers for the request
headers = {
    'X-TYPESENSE-API-KEY': typesense_api_key,
    'Content-Type': 'text/plain'
}

# Make the POST request to upload the data
response = requests.post(endpoint, headers=headers, data=jsonl_data)

# Check the response
if response.status_code == 200:
    print("Upload successful")
else:
    print(f"Error: {response.status_code}, {response.text}")

