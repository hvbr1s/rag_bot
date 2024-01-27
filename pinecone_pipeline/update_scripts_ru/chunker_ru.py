import hashlib
import json
import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
from tqdm.auto import tqdm
from collections import Counter
import tiktoken

################### HC CHUNKER ######################
class Document:
    def __init__(self, page_content, metadata):
        self.page_content = page_content
        self.metadata = metadata

def load_html_file(file_path):
    file_name = Path(file_path).name
    assert os.path.isfile(file_path) and file_name.lower().endswith('.html'), f'{file_path} is not a valid HTML file'
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    soup = BeautifulSoup(content, "html.parser")

    # Remove <span> tags from the content
    for span_tag in soup.find_all("span"):
        span_tag.unwrap()

    # Remove <path> tags from the content
    for path_tag in soup.find_all("path"):
        path_tag.decompose()

    title_tag = soup.find("h1")
    title = title_tag.text if title_tag else file_name

    # Extract all metadata into a dictionary
    metadata = {}
    meta_tags = soup.find_all("meta")
    for meta_tag in meta_tags:
        metadata.update({meta_tag.get("name"): meta_tag.get("content")})

    # Extract the text, discarding the HTML tags
    text_without_tags = soup.get_text()
    # Collapse any instances of multiple whitespaces down to a single whitespace
    text_with_collapsed_whitespace = re.sub(r'\s+', ' ', text_without_tags)
    return Document(page_content=text_with_collapsed_whitespace, metadata=metadata)

def load_files(directory_path):
    docs = []
    for file_name in os.listdir(directory_path):
        file_path = os.path.join(directory_path, file_name)
        doc = load_html_file(file_path)
        docs.append(doc)
    return docs

class TextChunker:
    def __init__(self, chunk_size, chunk_overlap, length_function, separators, minimum_chunk_size=5):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        self.separators = separators
        self.minimum_chunk_size = minimum_chunk_size

    def split_text(self, text: str):
        if self.length_function(text) <= self.chunk_size:
            return [text]

        for sep in self.separators:
            chunks = text.split(sep)
            if len(chunks) > 1:
                break

        if len(chunks) == 1:
            return [text]

        chunks_with_overlap = []
        current_chunk = ""
        for chunk in chunks:
            if self.length_function(f'{current_chunk} {chunk}') <= self.chunk_size:
                current_chunk = f'{current_chunk} {chunk}'
            else:
                if current_chunk:
                    chunks_with_overlap.append(current_chunk)
                current_chunk = chunk

        if current_chunk:
            chunks_with_overlap.append(current_chunk)

        # Create overlapping chunks
        overlapping_chunks = []
        for i in range(len(chunks_with_overlap)):
            current_chunk = chunks_with_overlap[i]
            if i < len(chunks_with_overlap) - 1:
                next_chunk = chunks_with_overlap[i + 1]
                overlap_start = max(len(current_chunk) - self.chunk_overlap, 0)
                current_chunk = f'{current_chunk} {next_chunk[:overlap_start]}'
            if len(current_chunk.split()) >= self.minimum_chunk_size:
                # only append the chunk if it has at least the minimum number of words to be considered relevant
                overlapping_chunks.append(current_chunk)

        return overlapping_chunks

# Define the length function
def tiktoken_len(text):
    # Initialize the tokenizer
    tokenizer = tiktoken.get_encoding('cl100k_base')
    tokens = tokenizer.encode(text, disallowed_special=())
    return len(tokens)

def count_chars_in_json(file_name):
    # Read the json file
    with open(file_name, 'r') as f:
        data = json.load(f)

    # Initialize a counter
    char_counts = Counter()

    # Check if data is a list
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                # Get the text
                text = item.get('text', '')

                # Count the characters and update the overall counter
                char_counts.update(Counter(text))

    return char_counts


def run_chunker(output_directory_path: str = None, chunk_size: int = 512, chunk_overlap: int = 50, minimum_chunk_size: int = 5):
    # Initialize the loader and load documents
    if not output_directory_path:
        pinecone_pipeline_root_directory = os.path.dirname(os.path.dirname(__file__))
        output_directory_path = os.path.join(pinecone_pipeline_root_directory, 'output_files')
    scraped_articles_folder = os.path.join(output_directory_path, 'articles')
    output_json_file_path = os.path.join(output_directory_path, 'output.json')
    chunk_list = [] # list of chunks to be written to the json file

    # Initialize the text splitter
    text_splitter = TextChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=tiktoken_len,
        separators=['\n\n', '\n', '| |', ' ', ''],
        minimum_chunk_size=minimum_chunk_size
    )

    # Process each document
    with open(output_json_file_path, 'w+', encoding='utf-8') as f:
        for file_name in tqdm(os.listdir(scraped_articles_folder)):
            file_path = os.path.join(scraped_articles_folder, file_name)
            doc = load_html_file(file_path)
            if 'source' in doc.metadata:
                url = doc.metadata['source']
                # Initialize the MD5 hash object
                md5 = hashlib.md5(url.encode('utf-8'))
                uid = md5.hexdigest()[:12]
            else:
                url = None
                uid = "unknown"

            chunks = text_splitter.split_text(doc.page_content)

            # Create an entry for each chunk
            # Include all metadata, plus the chunk text and the generated chunk ID
            for i, chunk in enumerate(chunks):
                entry = {}
                entry.update(doc.metadata)
                entry.update({
                    'id': f'{uid}-{i}',
                    'chunk-uid': uid,
                    'chunk-page-index': i,
                    'text': chunk.strip()
                    })
                chunk_list.append(entry)
        json.dump(chunk_list, f, ensure_ascii=False) # write the list of chunks to the json file

    # Character count
    counts = count_chars_in_json(output_json_file_path)

    # Compute total number of characters
    total_chars = sum(counts.values())
    print(f'Total characters: {total_chars}')
    return output_json_file_path

if __name__ == "__main__":
    run_chunker()