#!/bin/bash

echo "Setting up test environment..."

echo "Checking Python version..."
python3 --version || {
    echo "Python 3 not found. Please install Python 3.10+ first."
    exit 1
}

echo "Installing Python dependencies..."
python3 -m pip install --upgrade pip --user || {
    echo "Failed to upgrade pip"
    exit 1
}

pip3 install -r requirements.txt --user || {
    echo "Failed to install dependencies" 
    exit 1
}

echo "Running EPUB viewer tests..."
cd api
python3 -m pytest test_epub_viewer.py -v || {
    echo "Some tests failed"
    exit 1
}

echo "All tests completed successfully!"