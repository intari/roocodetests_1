#!/bin/bash

# Get absolute path to project root
PROJECT_ROOT=$(dirname $(dirname $(realpath $0)))

# Build the test image
docker build -t booksearch_tests .

# Run the test container
docker run --rm \
  -v $PROJECT_ROOT/test_data:/app/test_data \
  -v $PROJECT_ROOT/tests:/app/tests \
  --name booksearch_tests \
  booksearch_tests \
  sh -c "cd /app && PYTHONPATH=/app python -m unittest tests.unit.test_epub_extraction -v"
