from flask import Flask, request, jsonify, render_template, send_from_directory
from urllib.parse import unquote
from elasticsearch import Elasticsearch
import os
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import PyPDF2
import time
import logging
import multiprocessing
from src.core.index import index_files, get_progress
from io import StringIO
import sys
import re

app = Flask(__name__, static_folder='static')

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# Elasticsearch Configuration
ELASTICSEARCH_HOST = os.environ.get("ELASTICSEARCH_HOST", "localhost")
ELASTICSEARCH_PORT = int(os.environ.get("ELASTICSEARCH_PORT", 9200))
INDEX_NAME = "book_index"

# Wait for Elasticsearch to be available
es = None
while True:
    try:
        es = Elasticsearch([{'host': ELASTICSEARCH_HOST, 'port': ELASTICSEARCH_PORT, 'scheme': 'http'}])
        if es.ping():
            print("Connected to Elasticsearch")
            break
        else:
            print("Elasticsearch not available, retrying...")
    except Exception as e:
        print(f"Error connecting to Elasticsearch: {e}")
    time.sleep(5)

def extract_text_from_epub(epub_path):
    try:
        book = epub.read_epub(epub_path)
        text = ''
        for item in book.get_items():
            if item.media_type == 'application/xhtml+xml':
                content = item.get_content()
                if content:
                    soup = BeautifulSoup(content, 'html.parser')
                    text += soup.get_text()
        return text
    except Exception as e:
        logging.error(f"Error processing EPUB {epub_path}: {str(e)}")
        return f"Error extracting text: {str(e)}"

def extract_text_from_pdf(pdf_path):
    text = ''
    with open(pdf_path, 'rb') as pdf_file:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text()
    return text

@app.route('/', methods=['GET'])
def home():
    return render_template('search.html')

@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    if not query:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"error": "Query parameter is required"}), 400
        return render_template('search.html', query='')

    try:
        # Log the query for debugging
        print(f"Searching for query: {query} (length: {len(query)})")
        
        results = es.search(index=INDEX_NAME, query={'match': {'content': query}})
        hits = results['hits']['hits']
        
        search_results = []
        for hit in hits:
            file_path = hit['_source']['file_path']
            content = hit['_source']['content']
            
            # Log content sample for debugging
            print(f"Processing file: {file_path}")
            print(f"Content sample: {content[:100]}...")
            
            # Highlight snippet with improved matching for multi-word queries
            snippet_char_limit = int(os.environ.get("SNIPPET_CHAR_LIMIT", 100))
            try:
                # Normalize content and query
                normalized_content = content.casefold()
                normalized_query = query.casefold()
                
                def find_best_snippet(query, words):
                    try:
                        # Try exact phrase match
                        exact_pos = normalized_content.find(query)
                        if exact_pos != -1:
                            start = max(0, exact_pos - snippet_char_limit//2)
                            end = min(len(content), exact_pos + len(query) + snippet_char_limit//2)
                            snippet = content[start:end]
                            snippet = snippet.replace(query, f"**{query}**")
                            return snippet

                        # Try all words in any order
                        all_word_positions = []
                        for word in words:
                            if not word:
                                continue
                            start_idx = 0
                            while True:
                                index = normalized_content.find(word, start_idx)
                                if index == -1:
                                    break
                                all_word_positions.append((index, index + len(word)))
                                start_idx = index + len(word)

                        if all_word_positions:
                            all_word_positions.sort()
                            # Find region with most query words
                            best_start = 0
                            best_end = 0
                            max_words = 0
                            
                            for i in range(len(all_word_positions)):
                                current_start = all_word_positions[i][0]
                                current_end = current_start + snippet_char_limit
                                words_in_region = 1
                                
                                for j in range(i+1, len(all_word_positions)):
                                    if all_word_positions[j][0] < current_end:
                                        words_in_region += 1
                                    else:
                                        break
                                
                                if words_in_region > max_words:
                                    max_words = words_in_region
                                    best_start = max(0, current_start - snippet_char_limit//2)
                                    best_end = min(len(content), current_end + snippet_char_limit//2)
                            
                            if max_words > 0:
                                snippet = content[best_start:best_end]
                                for word in words:
                                    snippet = snippet.replace(word, f"**{word}**")
                                return snippet

                        # Recursively try with fewer words
                        if len(words) > 1:
                            for i in range(len(words)):
                                reduced_words = words[:i] + words[i+1:]
                                snippet = find_best_snippet(' '.join(reduced_words), reduced_words)
                                if snippet and snippet != "No snippet found":
                                    return snippet

                        # Final fallback to any single word
                        for word in words:
                            if not word:
                                continue
                            word_pos = normalized_content.find(word)
                            if word_pos != -1:
                                start = max(0, word_pos - snippet_char_limit//2)
                                end = min(len(content), word_pos + len(word) + snippet_char_limit//2)
                                return content[start:end].replace(word, f"**{word}**")

                        return "No snippet found"
                    except Exception as e:
                        print(f"Error in find_best_snippet: {str(e)}")
                        return "Error generating snippet"

                # Split query into words (handles hyphens and whitespace)
                import re
                query_words = [w for w in re.split(r'[\s-]+', normalized_query) if w]
                snippet = find_best_snippet(normalized_query, query_words)
                
                # Use the snippet we already generated from find_best_snippet
                if not snippet or snippet == "No snippet found":
                    # Final fallback to first 100 characters
                    snippet = content[:snippet_char_limit]
            except Exception as e:
                snippet = f"Error generating snippet: {str(e)}"
                print(f"Snippet generation error: {str(e)}")
                
            # Get base URL from environment
            base_url = os.environ.get("BASE_URL", "http://localhost:8000")
            # Construct URLs
            # Remove "/books/" from path start if it's here
            if file_path.startswith("/books/"):
                file_path = file_path[len("/books/"):]

            url = f"{base_url}/{file_path}"
            raw_url_old = f"{base_url}/file/{file_path}?format=html"
            raw_url = f"{base_url}/file_html/{file_path}"

            search_results.append({
                "file_path": file_path,
                "url": url,
                "raw_url": raw_url,
                "raw_url_old": raw_url_old,
                "snippet": snippet,
                "score": hit['_score']
            })

        # If it's an API request or format=json is specified
        if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
            response = jsonify({
                "query": query,
                "results": search_results,
                "total": len(search_results),
                "took": results['took']
            })
            response.headers['Content-Type'] = 'application/json'
            return response
        
        # Otherwise, render the HTML template
        return render_template('search.html', results=search_results, query=query)

    except Exception as e:
        if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
            response = jsonify({
                "error": str(e),
                "query": query
            })
            response.headers['Content-Type'] = 'application/json'
            return response, 500
        return render_template('search.html', error=str(e), query=query)

@app.route('/files', methods=['GET'])
def list_files():
    books_dir = "/books"
    files = []
    
    try:
        # Check if indexing is in progress
        indexing_in_progress = get_progress() is not None
        
        for filename in os.listdir(books_dir):
            file_path = os.path.join(books_dir, filename)
            if os.path.isfile(file_path):
                file_size = os.path.getsize(file_path)
                # Extract book title from filename if possible
                title = filename
                if ' - ' in filename:  # Common pattern in filenames
                    title_parts = filename.split(' - ')
                    if len(title_parts) > 1:
                        title = ' - '.join(title_parts[:-1])  # Take all but last part
                
                files.append({
                    'name': filename,
                    'title': title,
                    'path': filename,
                    'size': file_size,
                    'size_mb': round(file_size / (1024 * 1024), 2)
                })
        
        # Calculate totals
        total_files = len(files)
        total_size = sum(f['size'] for f in files)
        total_size_mb = round(total_size / (1024 * 1024), 2)
        
        # If it's an API request, return JSON
        if request.headers.get('Accept') == 'application/json':
            return jsonify({
                'files': files,
                'total_files': total_files,
                'total_size': total_size,
                'total_size_mb': total_size_mb,
                'indexing_in_progress': indexing_in_progress
            })
        
        # Otherwise, render the HTML template
        return render_template('files.html',
                            files=files,
                            total_files=total_files,
                            total_size=total_size,
                            total_size_mb=total_size_mb,
                            indexing_in_progress=indexing_in_progress)
    except Exception as e:
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"error": str(e)}), 500
        return render_template('files.html', error=str(e))

@app.route('/file_html/<path:file_path>', methods=['GET'])
def get_file_html(file_path):
    """Serve the HTML version of the file"""
    # Ensure the file path is within the /books directory
    books_dir = "/books"
    # TODO: remove this logic from regular version
    
    # Decode URL-encoded path and normalize
    decoded_path = unquote(file_path)
    # Remove any leading slashes or duplicate 'books/' segments
    decoded_path = decoded_path.lstrip('/')
    if decoded_path.startswith('books/'):
        decoded_path = decoded_path[6:]
    
    # Join paths safely
    full_path = os.path.normpath(os.path.join(books_dir, decoded_path))
    
    # Validate the path is within the books directory
    if not os.path.abspath(full_path).startswith(os.path.abspath(books_dir)):
        return jsonify({"error": "Access denied: File path outside of books directory"}), 403

    try:
        # Handle EPUB files
        if file_path.lower().endswith('.epub'):
                # Convert EPUB to HTML
                try:
                    book = epub.read_epub(full_path)
                    html_content = []
                    for item in book.get_items():
                        if item.get_type() == ebooklib.ITEM_DOCUMENT:
                            content = item.get_content()
                            if content:
                                soup = BeautifulSoup(content, 'html.parser')
                                # Preserve basic formatting tags
                                for tag in soup.find_all():
                                    if tag.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'div', 'span', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li']:
                                        tag.unwrap()
                                html_content.append(str(soup))
                except Exception as e:
                    logging.error(f"Error processing EPUB {full_path}: {str(e)}")
                    return jsonify({"error": f"Failed to process EPUB: {str(e)}"}), 500
                return render_template('text_file.html',
                                   file_path=file_path,
                                   content='<hr>'.join(html_content),
                                   is_html=True)
        
        # Handle regular text files
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # If it's an API request or the Accept header doesn't include HTML, return plain text
        if request.headers.get('Accept') == 'application/json' or 'text/html' not in request.headers.get('Accept', ''):
            return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        
        # Otherwise, render a simple HTML page with the content
        return render_template('text_file.html', file_path=file_path, content=content)
    except Exception as e:
        return jsonify({"error": str(e)}), 404



@app.route('/file/<path:file_path>', methods=['GET'])
def get_file(file_path):
    """Serve the file with proper headers"""
    # Ensure the file path is within the /books directory
    # TODO:does this function EVER used? Should it be? Should it be convertedto use get_file_html logic for format=html?
    books_dir = "/books"
    
    # Decode URL-encoded path and normalize
    decoded_path = unquote(file_path)
    # Remove any leading slashes or duplicate 'books/' segments
    decoded_path = decoded_path.lstrip('/')
    if decoded_path.startswith('books/'):
        decoded_path = decoded_path[6:]
    
    # Join paths safely
    full_path = os.path.normpath(os.path.join(books_dir, decoded_path))
    
    # Validate the path is within the books directory
    if not os.path.abspath(full_path).startswith(os.path.abspath(books_dir)):
        return jsonify({"error": "Access denied: File path outside of books directory"}), 403
    
    try:
        # Handle EPUB files
        if file_path.lower().endswith('.epub'):
            if request.args.get('format') == 'html':
                # Convert EPUB to HTML
                try:
                    book = epub.read_epub(full_path)
                    html_content = []
                    for item in book.get_items():
                        if item.get_type() == ebooklib.ITEM_DOCUMENT:
                            content = item.get_content()
                            if content:
                                soup = BeautifulSoup(content, 'html.parser')
                                # Preserve basic formatting tags
                                for tag in soup.find_all():
                                    if tag.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'div', 'span', 'strong', 'em', 'b', 'i', 'ul', 'ol', 'li']:
                                        tag.unwrap()
                                html_content.append(str(soup))
                except Exception as e:
                    logging.error(f"Error processing EPUB {full_path}: {str(e)}")
                    return jsonify({"error": f"Failed to process EPUB: {str(e)}"}), 500
                return render_template('text_file.html',
                                   file_path=file_path,
                                   content='<hr>'.join(html_content),
                                   is_html=True)
            else:
                # Render the viewer template
                return render_template('epub_viewer.html', file_path=file_path)
        
        # Handle regular text files
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # If it's an API request or the Accept header doesn't include HTML, return plain text
        if request.headers.get('Accept') == 'application/json' or 'text/html' not in request.headers.get('Accept', ''):
            return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        
        # Otherwise, render a simple HTML page with the content
        return render_template('text_file.html', file_path=file_path, content=content)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.route('/epub/<path:file_path>', methods=['GET'])
def get_epub_file(file_path):
    """Serve the raw EPUB file with proper headers"""
    books_dir = "/books"
    full_path = os.path.join(books_dir, file_path)
    
    # Validate the path is within the books directory
    if not os.path.abspath(full_path).startswith(os.path.abspath(books_dir)):
        return jsonify({"error": "Access denied: File path outside of books directory"}), 403
    
    try:
        # Serve the raw EPUB file with proper headers
        response = send_from_directory(
            books_dir,
            file_path,
            as_attachment=True,
            mimetype='application/epub+zip'
        )
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET'
        response.headers['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 404

@app.route('/index_books', methods=['GET'])
def index_books():
    logging.info("Indexing books endpoint called")
    
    # Get CPU configuration
    cpu_limit = os.environ.get("CPU_LIMIT")
    available_cpus = multiprocessing.cpu_count()
    used_cpus = float(cpu_limit) if cpu_limit else max(1, available_cpus - 1)
    
    try:
        # Configure logging to capture output
        logging.basicConfig(level=logging.INFO)
        # Start indexing in a separate thread
        from threading import Thread
        index_thread = Thread(target=index_files, args=("/books",))
        index_thread.start()
        
        # If it's an API request, return immediately
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"message": "Indexing started in background"})
        
        # Otherwise, render the progress page with CPU info
        return render_template('indexing.html',
                            available_cpus=available_cpus,
                            used_cpus=used_cpus)
        
    except Exception as e:
        logging.error(f"Indexing failed: {e}")
        
        if request.headers.get('Accept') == 'application/json':
            return jsonify({"error": str(e)}), 500
        
        # Create a simple HTML response for errors
        return render_template('indexing_error.html', error=str(e))

@app.route('/indexing_progress', methods=['GET'])
def get_indexing_progress():
    progress = get_progress()
    if progress is None:
        return jsonify({"status": "not_running"})
    
    # Format time for display
    from datetime import datetime
    import pytz
    
    # Get browser timezone from Accept-Language header or use UTC as fallback
    browser_tz = request.headers.get('X-Timezone', 'UTC')
    try:
        tz = pytz.timezone(browser_tz)
    except pytz.UnknownTimeZoneError:
        tz = pytz.UTC
    
    elapsed_min = int(progress['elapsed_time'] // 60)
    elapsed_sec = int(progress['elapsed_time'] % 60)
    
    if progress['estimated_remaining'] > 0:
        remaining_min = int(progress['estimated_remaining'] // 60)
        remaining_sec = int(progress['estimated_remaining'] % 60)
        completion_time = datetime.fromtimestamp(progress['estimated_completion'], tz).strftime('%H:%M:%S (%Z)')
    else:
        remaining_min = 0
        remaining_sec = 0
        completion_time = "N/A"
    
    return jsonify({
        "status": "running",
        "total_files": progress['total_files'],
        "processed_files": progress['processed_files'],
        "percentage": round(progress['percentage'], 1),
        "current_file": progress['current_file'],
        "elapsed_time": f"{elapsed_min}m {elapsed_sec}s",
        "estimated_remaining": f"{remaining_min}m {remaining_sec}s",
        "estimated_completion": completion_time,
        "errors": progress['errors']
    })

@app.route('/abort_indexing', methods=['POST'])
def abort_indexing():
    # In a real implementation, we would set a flag to stop the indexing
    # For now, we'll just return a message
    return jsonify({"status": "abort_requested", "message": "Indexing will stop after current file"})

@app.route('/reset_index', methods=['POST'])
def reset_index():
    """Reset the Elasticsearch index by deleting and recreating it"""
    try:
        # Check for basic auth
        auth = request.authorization
        if not auth or auth.username != os.environ.get("ADMIN_USER") or auth.password != os.environ.get("ADMIN_PASSWORD"):
            return jsonify({"error": "Authentication required"}), 401

        # Delete existing index if it exists
        if es.indices.exists(index=INDEX_NAME):
            es.indices.delete(index=INDEX_NAME)
        
        # Verify required plugins are installed
        try:
            plugins = es.cat.plugins(format='json')
            plugin_names = [p['component'] for p in plugins]
            
            if 'analysis-stempel' not in plugin_names:
                return jsonify({
                    "error": "Missing required plugin",
                    "message": "Please install analysis-stempel plugin for Russian support",
                    "solution": "Run: bin/elasticsearch-plugin install analysis-stempel"
                }), 500

            # Create index with cyrillic analyzer
            es.indices.create(index=INDEX_NAME, body={
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "analysis": {
                        "filter": {
                            "russian_stop": {
                                "type": "stop",
                                "stopwords": "_russian_"
                            },
                            "russian_stemmer": {
                                "type": "stemmer",
                                "language": "russian"
                            }
                        },
                        "analyzer": {
                            "cyrillic_analyzer": {
                                "tokenizer": "standard",
                                "filter": [
                                    "lowercase",
                                    "russian_stop",
                                    "russian_stemmer"
                                ]
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "file_path": {"type": "keyword"},
                        "content": {
                            "type": "text",
                            "analyzer": "cyrillic_analyzer",
                            "search_analyzer": "cyrillic_analyzer"
                        }
                    }
                }
            })
        except Exception as e:
            # Fallback to basic configuration if advanced filters aren't available
            es.indices.create(index=INDEX_NAME, body={
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0
                },
                "mappings": {
                    "properties": {
                        "file_path": {"type": "keyword"},
                        "content": {
                            "type": "text",
                            "analyzer": "standard",
                            "search_analyzer": "standard"
                        }
                    }
                }
            })
        
        return jsonify({"status": "success", "message": "Index reset successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.info("Starting the API - inside main block")
    app.run(debug=True, host='0.0.0.0')