import json

def map_data_to_schema(data, schema):
    mapped_data = []
    for item in data:
        mapped_item = {}
        for field in schema['fields']:
            field_name = field['name']
            if field_name in item:
                # Directly map the field if it's not an int32 type
                if field['type'] != 'int32':
                    mapped_item[field_name] = item[field_name]
                else:
                    # For int32 fields, try to convert to int
                    try:
                        mapped_item[field_name] = int(item[field_name])
                    except ValueError:
                        mapped_item[field_name] = item[field_name]
        mapped_data.append(mapped_item)
    return mapped_data

# Path to the input and output JSON files
input_file_path = "/home/danledger/knowledge_bot/typesense_pipeline/output_files/output.json" 
output_file_path = "/home/danledger/knowledge_bot/typesense_pipeline/output_files/ts_output.json"  

# Read data from the input JSON file
with open(input_file_path, 'r') as file:
    data_list = json.load(file)

# Schema for TypeSense collection
collection_schema = {
    "name": "help_center",
    "fields": [
        {"name": "title", "type": "string"},
        {"name": "source", "type": "string"},
        {"name": "zd-article-id", "type": "int32", "facet": True},
        {"name": "classification", "type": "string"},
        {"name": "locale", "type": "string"},
        {"name": "text", "type": "string"},
        {"name": "last-updated", "type": "string"}  # Ensure this is included
    ],
    "default_sorting_field": "title",
    "enable_nested_fields": True
}

# Mapping the data
mapped_data = map_data_to_schema(data_list, collection_schema)

# Write the transformed data to the output JSON file
with open(output_file_path, 'w') as file:
    json.dump(mapped_data, file, indent=2)

# Optional: Print a sample from the output for verification
with open(output_file_path, 'r') as file:
    sample_output = json.load(file)
    print("Sample output data:", sample_output[:1])