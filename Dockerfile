FROM python:3.9-alpine

WORKDIR /app

# Install dependencies
RUN pip install flask elasticsearch ebooklib beautifulsoup4 PyPDF2 pytz

# Create books directory with proper permissions
RUN mkdir -p /books && chmod 777 /books

# Copy the API code and static files
COPY api/app.py .
COPY api/static /app/static
COPY api/templates /app/templates

# Expose the API port
EXPOSE 5000

# Copy the indexing script
COPY index.py .

# Copy the test file
COPY api/test_app.py .

# Add a dummy file to invalidate cache
ADD dummy.txt .

# Command to run the API
CMD ["python", "app.py"]