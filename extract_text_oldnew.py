import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import time
from threading import Lock
from elasticsearch import Elasticsearch
import PyPDF2

# Elasticsearch Configuration
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST", "localhost")
ELASTICSEARCH_PORT = int(os.environ.get("ELASTICSEARCH_PORT", 9200))
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

# Initialize Elasticsearch client
es = None
try:
    es = Elasticsearch([{'host': ELASTICSEARCH_HOST, 'port': ELASTICSEARCH_PORT, 'scheme': 'http'}])
except Exception as e:
    print(f"Error connecting to Elasticsearch: {e}")

def create_index():
    """Create the Elasticsearch index if it doesn't exist."""
    if es and not es.indices.exists(index=INDEX_NAME):
        es.indices.create(index=INDEX_NAME, body={
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "file_path": {"type": "keyword"},
                    "content": {"type": "text"}
                }
            }
        })

def extract_text_from_epub(epub_path, progress_lock=None, indexing_progress=None):
    """Extract text from EPUB with robust error handling.
    Args:
        epub_path: Path to EPUB file
        progress_lock: Optional threading lock for progress updates
        indexing_progress: Optional dict containing 'errors' list for tracking
    Returns tuple of (extracted_text, error_messages)"""
    text = ''
    errors = []
    
    def add_error(msg):
        errors.append(msg)
        if indexing_progress is not None and progress_lock is not None:
            with progress_lock:
                indexing_progress['errors'].append(msg)
    
    if not os.path.exists(epub_path):
        add_error(f"EPUB file not found: {epub_path}")
        return '', errors
        
    try:
        # Start with book parsing information
        info_messages = []
        info_messages.append(f"[INFO] Starting to parse EPUB file: {epub_path}")
        
        book = epub.read_epub(epub_path)
        
        # Add book metadata
        info_messages.append("[INFO] Book Metadata:")
        info_messages.append(f"[INFO]   Title: {book.get_metadata('DC', 'title')[0][0] if book.get_metadata('DC', 'title') else 'Unknown'}")
        info_messages.append(f"[INFO]   Author: {book.get_metadata('DC', 'creator')[0][0] if book.get_metadata('DC', 'creator') else 'Unknown'}")
        info_messages.append(f"[INFO]   ID: {book.get_metadata('DC', 'identifier')[0][0] if book.get_metadata('DC', 'identifier') else 'Unknown'}")
        info_messages.append(f"[INFO]   Language: {book.get_metadata('DC', 'language')[0][0] if book.get_metadata('DC', 'language') else 'Unknown'}")
        
        items = book.get_items()
        if items is None:
            return '\n'.join(info_messages), errors
        
            
        # Add EPUB structure summary and get items collection (it doesn't work otherwise on some test fixes)
        media_types = {}
        collected_items =[]
        for item in items:
            media_types[item.media_type] = media_types.get(item.media_type, 0) + 1
            # This is necessary to work around a bug in some test files where items not returned otherwise
            collected_items.append(item)            

        info_messages.append("[INFO] EPUB Structure Summary:")
        for media_type, count in media_types.items():
            info_messages.append(f"[INFO]   {media_type}: {count} items")


        # Get spine items first to validate references
        spine_items = []
        try:
            spine = book.spine
            spine_items = [book.get_item_with_id(item[0]) for item in spine]
            info_messages.append(f"[INFO] Parsing spine (reading order)...")
            info_messages.append(f"[INFO]   Found {len(spine_items)} items in spine")
            
            # Handle None items in spine
            for i, item in enumerate(spine_items):
                if item is None:
                    add_error(f"Skipping missing spine item {spine[i][0]} in {epub_path}")
        except Exception as e:
            add_error(f"Error getting EPUB spine: {str(e)}")
            
        info_messages.append("[INFO] Extracting text from content documents...")
        content_text = ''
        content_items = 0
        for item in collected_items:
            if item.media_type == 'application/xhtml+xml':
                try:
                    # Safely get item name for logging
                    item_name = getattr(item, 'get_name', lambda: 'unnamed')()
                    #info_messages.append(f"[INFO]   Processing content document: {item_name} (in spine: {item in spine_items})")
                    
                    content = item.get_content().decode('utf-8')
                    soup = BeautifulSoup(content, 'html.parser')
                    extracted = soup.get_text(separator=' ', strip=True)
                    content_text += extracted + '\n'
                    info_messages.append(f"{item_name} contains {len(extracted)} characters")
                    content_items += 1
                except UnicodeDecodeError:
                    try:
                        content = item.get_content().decode('latin-1')
                        soup = BeautifulSoup(content, 'html.parser')
                        extracted = soup.get_text(separator=' ', strip=True)
                        content_text += extracted + '\n'
                        info_messages.append(f"[INFO]     Extracted {len(extracted)} characters from {item_name} (using latin-1 fallback)")
                        content_items += 1
                    except Exception as e:
                        add_error(f"Error parsing EPUB item {item_name}: {str(e)}")
                except Exception as e:
                    add_error(f"Error parsing EPUB item {item_name}: {str(e)}")
                    
        # Combine info messages and content
        full_text = '\n'.join(info_messages)
        full_text += f"\n[INFO] Completed text extraction: {len(content_text)} characters from {content_items} content documents"
        full_text += f"\n[INFO] Total extracted text length: {len(content_text)} characters"
        full_text += f"\n\n{content_text.strip()}"
        return full_text, errors
    except Exception as e:
        add_error(f"Error processing EPUB {epub_path}: {str(e)}")
        return text, errors

def get_progress():
    """Get the current indexing progress.
    Returns None if indexing is not running, otherwise returns a dictionary with progress information."""
    with progress_lock:
        if not indexing_progress['is_running']:
            return None
        
        progress = indexing_progress.copy()
        if progress['total_files'] > 0:
            progress['percentage'] = (progress['processed_files'] / progress['total_files']) * 100
        else:
            progress['percentage'] = 0
            
        elapsed = time.time() - progress['start_time'] if progress['start_time'] else 0
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

def extract_text_from_pdf(pdf_path, progress_lock=None, indexing_progress=None):
    """Extract text from PDF with robust error handling.
    Args:
        pdf_path: Path to PDF file
        progress_lock: Optional threading lock for progress updates
        indexing_progress: Optional dict containing 'errors' list for tracking
    Returns tuple of (extracted_text, error_messages)"""
    text = ''
    errors = []
    
    def add_error(msg):
        errors.append(msg)
        if indexing_progress is not None and progress_lock is not None:
            with progress_lock:
                indexing_progress['errors'].append(msg)
    
    # Validate input file
    if not os.path.exists(pdf_path):
        add_error(f"File not found: {pdf_path}")
        return '', errors
    if not os.access(pdf_path, os.R_OK):
        add_error(f"File not readable: {pdf_path}")
        return '', errors
    
    try:
        with open(pdf_path, 'rb') as pdf_file:
            try:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                total_pages = len(pdf_reader.pages)
                
                for page_num in range(total_pages):
                    try:
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    except Exception as page_error:
                        add_error(f"Page {page_num+1}/{total_pages}: {str(page_error)}")
                        continue
                        
            except Exception as pdf_error:
                add_error(f"PDF processing error: {str(pdf_error)}")
                
    except Exception as file_error:
        add_error(f"File access error: {str(file_error)}")
        
    return text, errors

def index_files(directory):
    """Index files in the specified directory.
    This function scans the directory for EPUB, PDF, and TXT files,
    extracts text from them, and indexes the content in Elasticsearch."""
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
        # Create the Elasticsearch index if it doesn't exist
        if es:
            create_index()
        else:
            with progress_lock:
                indexing_progress['errors'].append("Elasticsearch connection not available")
                return
        
        # First count all files
        total_files = 0
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(('.epub', '.pdf', '.txt')):
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
                    text = ""
                    errors = []
                    
                    if file_path.lower().endswith(".epub"):
                        text, errors = extract_text_from_epub(
                            file_path,
                            progress_lock=progress_lock,
                            indexing_progress=indexing_progress
                        )
                    elif file_path.lower().endswith(".pdf"):
                        text, errors = extract_text_from_pdf(
                            file_path,
                            progress_lock=progress_lock,
                            indexing_progress=indexing_progress
                        )
                    elif file_path.lower().endswith(".txt"):
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                text = f.read()
                        except Exception as e:
                            with progress_lock:
                                indexing_progress['errors'].append(f"Error reading {file_path}: {str(e)}")
                            continue
                    else:
                        print(f"Skipping unsupported file type: {file_path}")
                        continue

                    # Index the document in Elasticsearch
                    if es and text:
                        doc = {
                            'file_path': file_path,
                            'content': text
                        }
                        es.index(index=INDEX_NAME, document=doc)
                        print(f"Indexed: {file_path}")
                    
                    with progress_lock:
                        indexing_progress['processed_files'] += 1
                    
                except Exception as e:
                    error_msg = f"Error indexing {file_path}: {str(e)}"
                    print(error_msg)
                    with progress_lock:
                        indexing_progress['errors'].append(error_msg)
        
    finally:
        with progress_lock:
            indexing_progress['is_running'] = False