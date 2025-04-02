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

# TODO: remove old version?
def extract_text_from_epub_old(epub_path):
    book = epub.read_epub(epub_path)
    text = ''
    for item in book.get_items():
        if item.media_type == 'application/xhtml+xml':
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text += soup.get_text()
    return text

# TODO: remove old version?
def extract_text_from_epub_interim(epub_path):
    text = ''
    try:
        try:
            book = epub.read_epub(epub_path)
        except Exception as e:
            with progress_lock:
                indexing_progress['errors'].append(f"EPUB structure error in {epub_path}: {str(e)}")
            return text  # Return empty if we can't even read the EPUB

        for item in book.get_items():
            current_item_id = getattr(item, 'id', 'no_id')
            try:
                # Attempt to process all text-containing formats
                if item.media_type in ['application/xhtml+xml', 'text/html', 'application/html']:
                    try:
                        content = item.get_content()
                    except Exception as e:
                        with progress_lock:
                            indexing_progress['errors'].append(
                                f"Content extraction failed in {epub_path} item {current_item_id}: {str(e)}")
                        continue

                    try:
                        soup = BeautifulSoup(content, 'html.parser', from_encoding='utf-8')
                        item_text = soup.get_text(separator='\n', strip=True)
                        text += f"\n{item_text}\n"
                    except Exception as e:
                        with progress_lock:
                            indexing_progress['errors'].append(
                                f"HTML parsing failed in {epub_path} item {current_item_id}: {str(e)}")
                        # Fallback to raw content extraction
                        text += f"\n{content.decode('utf-8', errors='replace')}\n"

            except Exception as e:
                with progress_lock:
                    indexing_progress['errors'].append(
                        f"Unexpected error processing {epub_path} item {current_item_id}: {str(e)}")
                continue

    except Exception as e:
        with progress_lock:
            indexing_progress['errors'].append(f"Critical failure processing {epub_path}: {str(e)}")

    return text

# TODO: remove old version?
def extract_text_from_epub_interim2(epub_path, progress_lock=None, indexing_progress=None):
    """Extract text from EPUB using generator stabilization."""
    text = ''
    errors = []
    info_messages = []
    
    def add_error(msg):
        errors.append(msg)
        if indexing_progress and progress_lock:
            with progress_lock:
                indexing_progress['errors'].append(msg)

    # Validate file existence
    if not os.path.exists(epub_path):
        add_error(f"File not found: {epub_path}")
        return '', errors

    try:
        # --- EPUB Initialization ---
        try:
            book = epub.read_epub(epub_path)
            info_messages.append(f"[MAIN] Processing EPUB: {os.path.basename(epub_path)}")
        except Exception as e:
            add_error(f"EPUB read failure: {str(e)}")
            return '', errors

        # --- Metadata Extraction ---
        md = lambda ns,name: book.get_metadata(ns, name)[0][0] if book.get_metadata(ns, name) else 'N/A'
        info_messages.extend([
            "[METADATA]",
            f"Title: {md('DC', 'title')}",
            f"Creator: {md('DC', 'creator')}",
            f"Language: {md('DC', 'language')}",
            f"Identifier: {md('DC', 'identifier')}"
        ])

        # --- Critical Section: Resolve Generator Early ---
        try:
            raw_items = book.get_items()
            item_cache = list(raw_items)  # Convert generator to list IMMEDIATELY
            item_map = {item.id: item for item in item_cache}
            info_messages.append(f"[STRUCTURE] Found {len(item_cache)} items in manifest")
        except Exception as e:
            add_error(f"Item collection failed: {str(e)}")
            return '', errors

        # --- Spine Reconciliation ---
        spine_items = []
        try:
            spine_ids = [s[0] for s in book.spine]
            spine_items = [item_map.get(sid) for sid in spine_ids]
            missing = len([sid for sid in spine_ids if sid not in item_map])
            
            info_messages.append(
                f"[SPINE] Contains {len(spine_ids)} entries "
                f"({len(spine_items)-missing} valid, {missing} missing)"
            )
        except Exception as e:
            add_error(f"Spine analysis failed: {str(e)}")

        # --- Content Processing ---
        content_blocks = []
        processed_items = 0
        
        for item in item_cache:  # Use stabilized list
            if item.media_type not in {'application/xhtml+xml', 'text/html'}:
                continue
                
            try:
                # Filter items safely
                if item.size == 0:
                    info_messages.append(f"[SKIP] Empty item: {item.id}")
                    continue

                try_context = f"Item {item.id} ({item.media_type})"
                
                # Content decoding
                try:
                    content = item.get_content().decode('utf-8-sig')  # Handle BOM
                except UnicodeError:
                    content = item.get_content().decode('latin-1', errors='replace')

                # Text extraction
                soup = BeautifulSoup(content, 'html.parser')
                text = soup.get_text(separator='\n', strip=True)
                
                content_blocks.append(text)
                processed_items += 1
                info_messages.append(f"[PROCESSED] {try_context} ({len(text)} chars)")

            except Exception as e:
                add_error(f"Processing failed for {item.id}: {str(e)}")

        # --- Final Assembly ---
        info_messages.append(
            f"[STATS] Processed {processed_items}/{len(item_cache)} items "
            f"({len(content_blocks)} valid blocks)"
        )
        
        full_text = '\n'.join(info_messages) + '\n\n' + '\n'.join(content_blocks)
        return full_text.strip(), errors

    except Exception as e:
        add_error(f"Critical failure: {str(e)}")
        return '', errors

def extract_text_from_epub(epub_path):
    text = ''
    try:
        try:
            book = epub.read_epub(epub_path)
        except Exception as e:
            with progress_lock:
                indexing_progress['errors'].append(f"EPUB structure error in {epub_path}: {str(e)}")
            return text

        # Collect all items first to handle generator issues
        collected_items = []
        try:
            for item in book.get_items():
                collected_items.append(item)
        except Exception as e:
            with progress_lock:
                indexing_progress['errors'].append(f"Item collection failed in {epub_path}: {str(e)}")

        for item in collected_items:
            current_item_id = getattr(item, 'id', 'no_id')
            try:
                if item.media_type in ['application/xhtml+xml', 'text/html', 'application/html']:
                    try:
                        content = item.get_content()
                    except Exception as e:
                        with progress_lock:
                            indexing_progress['errors'].append(
                                f"Content extraction failed in {epub_path} item {current_item_id}: {str(e)}")
                        continue

                    try:
                        soup = BeautifulSoup(content, 'html.parser', from_encoding='utf-8')
                        item_text = soup.get_text(separator='\n', strip=True)
                        text += f"\n{item_text}\n"
                    except Exception as e:
                        with progress_lock:
                            indexing_progress['errors'].append(
                                f"HTML parsing failed in {epub_path} item {current_item_id}: {str(e)}")
                        text += f"\n{content.decode('utf-8', errors='replace')}\n"

            except Exception as e:
                with progress_lock:
                    indexing_progress['errors'].append(
                        f"Unexpected error processing {epub_path} item {current_item_id}: {str(e)}")
                continue

    except Exception as e:
        with progress_lock:
            indexing_progress['errors'].append(f"Critical failure processing {epub_path}: {str(e)}")

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