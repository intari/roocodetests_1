from elasticsearch import Elasticsearch
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import PyPDF2
import time
from threading import Lock

# Elasticsearch Configuration
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST", "localhost")
ELASTICSEARCH_PORT = int(os.environ.get("ELASTICSEARCH_PORT", 9200))
es = Elasticsearch([{'host': ELASTICSEARCH_HOST, 'port': ELASTICSEARCH_PORT, 'scheme': 'http'}])
INDEX_NAME = "book_index"

# Global variables for progress tracking
indexing_progress = {
    'total_files': 0,
    'processed_files': 0,
    'start_time': None,
    'is_running': False,
    'current_file': '',
    'errors': []
}
progress_lock = Lock()

def create_index():
    if not es.indices.exists(index=INDEX_NAME):
        es.indices.create(index=INDEX_NAME)

def extract_text_from_epub(epub_path):
    book = epub.read_epub(epub_path)
    text = ''
    for item in book.get_items():
        if item.media_type == 'application/xhtml+xml':
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text += soup.get_text()
    return text

def extract_text_from_pdf(pdf_path):
    text = ''
    with open(pdf_path, 'rb') as pdf_file:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text()
    return text

def get_progress():
    with progress_lock:
        if not indexing_progress['is_running']:
            return None
        
        progress = indexing_progress.copy()
        if progress['total_files'] > 0:
            progress['percentage'] = (progress['processed_files'] / progress['total_files']) * 100
        else:
            progress['percentage'] = 0
            
        elapsed = time.time() - progress['start_time']
        progress['elapsed_time'] = elapsed
        if progress['processed_files'] > 0:
            time_per_file = elapsed / progress['processed_files']
            remaining_files = progress['total_files'] - progress['processed_files']
            progress['estimated_remaining'] = time_per_file * remaining_files
            progress['estimated_completion'] = time.time() + progress['estimated_remaining']
        else:
            progress['estimated_remaining'] = 0
            progress['estimated_completion'] = 0
            
        return progress

def index_files(directory):
    global indexing_progress
    
    with progress_lock:
        indexing_progress = {
            'total_files': 0,
            'processed_files': 0,
            'start_time': time.time(),
            'is_running': True,
            'current_file': '',
            'errors': []
        }
    
    try:
        create_index()
        
        # First count all files
        total_files = 0
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(('.epub', '.pdf', '.txt')):
                    total_files += 1
        
        with progress_lock:
            indexing_progress['total_files'] = total_files
        
        # Now process files
        for root, _, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                
                with progress_lock:
                    indexing_progress['current_file'] = file_path
                
                try:
                    encoded_file_path = file_path.encode('utf-8').decode('utf-8')
                    if file_path.endswith(".epub"):
                        text = extract_text_from_epub(file_path)
                    elif file_path.endswith(".pdf"):
                        text = extract_text_from_pdf(file_path)
                    elif file_path.endswith(".txt"):
                        with open(encoded_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            text = f.read()
                    else:
                        print(f"Skipping unsupported file type: {file_path}")
                        continue

                    doc = {
                        'file_path': file_path,
                        'content': text
                    }
                    es.index(index=INDEX_NAME, document=doc)
                    print(f"Indexed: {file_path}")
                    
                    with progress_lock:
                        indexing_progress['processed_files'] += 1
                    
                except Exception as e:
                    error_msg = f"Error indexing {file_path}: {type(e)}, {e}"
                    print(error_msg)
                    with progress_lock:
                        indexing_progress['errors'].append(error_msg)
        
    finally:
        with progress_lock:
            indexing_progress['is_running'] = False

if __name__ == '__main__':
    BOOKS_DIR = "/books"  # This should match the volume mount in docker-compose.yml
    index_files(BOOKS_DIR)