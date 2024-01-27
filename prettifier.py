import json

def process_and_save_json(input_file_path, output_file_path):
    try:
        with open(input_file_path, 'r') as input_file:
            data = json.load(input_file)

        with open(output_file_path, 'w') as output_file:
            output_file.write('[\n')
            for i, entry in enumerate(data):
                json.dump(entry, output_file)
                if i < len(data) - 1:
                    output_file.write(',\n')
            output_file.write('\n]')
    except Exception as e:
        print(f"An error occurred: {e}")

# Replace 'your_file.json' with the path to your JSON file
process_and_save_json('/home/dan/knowledge_bot/examples.json', '/home/dan/knowledge_bot/examplez.json' )
