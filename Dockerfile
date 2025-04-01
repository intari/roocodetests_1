FROM python:3.9-alpine

WORKDIR /app

# Install dependencies
RUN pip install flask elasticsearch ebooklib beautifulsoup4 PyPDF2 pytz

# Create books directory with proper permissions
RUN mkdir -p /books && chmod 777 /books

# Copy the API code and static files
COPY src/api/app.py .
COPY src/api/static /app/static
COPY src/api/templates /app/templates

# Expose the API port
EXPOSE 5000

# Copy the indexing script
COPY src/core/index.py .

# Copy the test file
COPY tests/unit/test_app.py .

# Add a dummy file to invalidate cache
ADD dummy.txt .

# Command to run the API
CMD ["python", "app.py"]