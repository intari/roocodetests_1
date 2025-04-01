import os
import pytest
import tempfile
import shutil
from app import app
from unittest.mock import patch, MagicMock
from ebooklib import epub

def create_test_epub():
    """Create a simple test EPUB file"""
    # Create a simple EPUB file
    book = epub.EpubBook()
    
    # Set metadata
    book.set_identifier('test123456')
    book.set_title('Test EPUB Book')
    book.set_language('en')
    book.add_author('Test Author')
    
    # Add a chapter
    c1 = epub.EpubHtml(title='Chapter 1', file_name='chap_01.xhtml', lang='en')
    c1.content = '<html><body><h1>Chapter 1</h1><p>This is a test EPUB file.</p></body></html>'
    book.add_item(c1)
    
    # Add navigation
    book.toc = [c1]
    book.spine = ['nav', c1]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    epub_path = os.path.join(temp_dir, 'test.epub')
    
    # Write the EPUB file
    epub.write_epub(epub_path, book)
    
    return epub_path, temp_dir

@pytest.fixture
def client():
    """Create a test client for the Flask app"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def test_epub():
    """Create a test EPUB file and clean up after the test"""
    epub_path, temp_dir = create_test_epub()
    
    # Mock the books directory
    original_join = os.path.join
    
    def mock_join(path, *paths):
        if path == "/books" and paths and paths[0] == "test.epub":
            return epub_path
        return original_join(path, *paths)
    
    def mock_abspath(path):
        if path == os.path.join("/books", "test.epub"):
            return "/books/test.epub"
        elif path == epub_path:
            return "/books/test.epub"
        return path
    
    with patch('os.path.join', side_effect=mock_join):
        with patch('os.path.isfile', return_value=True):
            with patch('os.path.abspath', side_effect=mock_abspath):
                yield epub_path
    
    # Clean up
    shutil.rmtree(temp_dir)

def test_epub_viewer_page(client, test_epub):
    """Test that the EPUB viewer page loads correctly"""
    response = client.get('/file/test.epub')
    
    assert response.status_code == 200
    assert b'<!DOCTYPE html>' in response.data
    assert b'<title>test.epub</title>' in response.data
    assert b'<div id="viewer"></div>' in response.data
    assert b'<script src="https://cdn.jsdelivr.net/npm/epubjs' in response.data

def test_epub_file_endpoint(client, test_epub):
    """Test that the EPUB file is served with correct headers"""
    response = client.get('/epub/test.epub')
    
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/epub+zip'
    assert response.headers['Access-Control-Allow-Origin'] == '*'
    
    # Check that the response contains EPUB data (at least the magic number)
    assert response.data.startswith(b'PK')

def test_epub_viewer_integration(client, test_epub):
    """Test the integration between the viewer and the EPUB file"""
    # This test would ideally use Selenium or Playwright to test the actual rendering
    # Since we can't run a browser in this environment, we'll check for the correct setup
    
    # First, check that the viewer page loads
    viewer_response = client.get('/file/test.epub')
    assert viewer_response.status_code == 200
    
    # Check that the JavaScript is correctly set up to load the EPUB
    assert b'/epub/test.epub' in viewer_response.data
    
    # Check that the EPUB file is accessible
    epub_response = client.get('/epub/test.epub')
    assert epub_response.status_code == 200
    assert epub_response.headers['Content-Type'] == 'application/epub+zip'

if __name__ == '__main__':
    pytest.main(['-xvs', __file__])