import unittest
import os
from src.core.index import extract_text_from_epub

class TestEPUBExtraction(unittest.TestCase):
    def setUp(self):
        self.test_data_dir = os.path.join(os.path.dirname(__file__), '../../test_data')
        self.epub_files = [
            os.path.join(self.test_data_dir, f)
            for f in os.listdir(self.test_data_dir)
            if f.endswith('.epub')
        ]
        self.invalid_file = os.path.join(self.test_data_dir, 'nonexistent.epub')

    def test_extract_text_from_all_epubs(self):
        """Test text extraction from all EPUB files in test_data"""
        for epub_path in self.epub_files:
            with self.subTest(epub_file=os.path.basename(epub_path)):
                text = extract_text_from_epub(epub_path)
                self.assertIsInstance(text, str)
                self.assertGreater(len(text), 0,
                                 f"Extracted text should not be empty for {epub_path}")

    def test_extract_text_from_invalid_file(self):
        # Test error handling for non-existent file
        text = extract_text_from_epub(self.invalid_file)
        self.assertEqual(text, '')

    def test_empty_file_handling(self):
        # Create a temporary empty EPUB file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.epub') as temp_epub:
            text = extract_text_from_epub(temp_epub.name)
            self.assertEqual(text, '')

if __name__ == '__main__':
    unittest.main()