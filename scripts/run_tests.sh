#!/bin/bash

# Get absolute path to project root
PROJECT_ROOT=$(dirname $(dirname $(realpath $0)))

# Run the test container
docker-compose -f $PROJECT_ROOT/docker-compose.yml up -d booksearch_tests

# Follow the logs
docker logs -f booksearch_tests

# Clean up
docker-compose -f $PROJECT_ROOT/docker-compose.yml down
