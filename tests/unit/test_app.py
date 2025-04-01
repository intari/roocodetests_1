import unittest
import json
import os
import tempfile
import shutil
from app import app
from unittest.mock import patch, MagicMock

class BookSearchAPITest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        
        # Create a temporary directory for test books
        self.test_books_dir = tempfile.mkdtemp()
        
        # Create a sample test file
        self.sample_file_path = os.path.join(self.test_books_dir, 'test_sample.txt')
        with open(self.sample_file_path, 'w', encoding='utf-8') as f:
            f.write("This is a test sample file for testing the book search API.")
    
    def tearDown(self):
        # Remove the temporary directory
        shutil.rmtree(self.test_books_dir)
    
    @patch('app.es')
    @patch('app.index_files')
    def test_index_books_api(self, mock_index_files, mock_es):
        # Mock the index_files function
        mock_index_files.return_value = None
        
        # Test the API endpoint
        response = self.client.get('/index_books', headers={'Accept': 'application/json'})
        
        # Check if the response is successful
        self.assertEqual(response.status_code, 200)
        
        # Check if the response contains the expected message
        data = json.loads(response.data)
        self.assertIn('message', data)
        self.assertEqual(data['message'], 'Indexing completed')
        
        # Check if the index_files function was called
        mock_index_files.assert_called_once_with('/books')
    
    @patch('app.es')
    def test_search_api(self, mock_es):
        # Mock the Elasticsearch search method
        mock_search_result = {
            'hits': {
                'hits': [
                    {
                        '_source': {
                            'file_path': '/books/test_sample.txt',
                            'content': 'This is a test sample file for testing the book search API.'
                        }
                    }
                ]
            }
        }
        mock_es.search.return_value = mock_search_result
        
        # Test the API endpoint
        response = self.client.get('/search?query=test', headers={'Accept': 'application/json'})
        
        # Check if the response is successful
        self.assertEqual(response.status_code, 200)
        
        # Check if the response contains the expected data
        data = json.loads(response.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['file_path'], '/books/test_sample.txt')
        self.assertIn('snippet', data[0])
        
        # Check if the Elasticsearch search method was called with the correct parameters
        mock_es.search.assert_called_once()
    
    @patch('app.os.listdir')
    @patch('app.os.path.isfile')
    def test_list_files_api(self, mock_isfile, mock_listdir):
        # Mock the os.listdir function
        mock_listdir.return_value = ['test_sample.txt', 'another_file.txt']
        # Mock the os.path.isfile function to always return True
        mock_isfile.return_value = True
        
        # Test the API endpoint
        response = self.client.get('/files', headers={'Accept': 'application/json'})
        
        # Check if the response is successful
        self.assertEqual(response.status_code, 200)
        
        # Check if the response contains the expected data
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['name'], 'test_sample.txt')
        self.assertEqual(data[1]['name'], 'another_file.txt')
        
        # Check if the os.listdir function was called with the correct parameters
        mock_listdir.assert_called_once_with('/books')
    
    @patch('app.open')
    @patch('app.os.path.isfile')
    @patch('app.os.path.abspath')
    def test_get_file_api(self, mock_abspath, mock_isfile, mock_open):
        # Mock the necessary functions
        mock_isfile.return_value = True
        mock_abspath.side_effect = lambda x: x  # Return the input unchanged
        
        # Mock the open function
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "This is a test sample file."
        mock_open.return_value = mock_file
        
        # Test the API endpoint
        response = self.client.get('/file/test_sample.txt', headers={'Accept': 'application/json'})
        
        # Check if the response is successful
        self.assertEqual(response.status_code, 200)
        
        # Check if the response contains the expected data
        self.assertEqual(response.data.decode('utf-8'), "This is a test sample file.")
        
        # Check if the open function was called with the correct parameters
        mock_open.assert_called_once()

if __name__ == '__main__':
    unittest.main()