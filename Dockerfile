FROM python:3.9-alpine

WORKDIR /app

# Install dependencies
RUN pip install flask elasticsearch ebooklib beautifulsoup4 PyPDF2 pytz

# Create books directory with proper permissions
RUN mkdir -p /books && chmod 777 /books

# Create project directory structure
RUN mkdir -p src/api/static src/api/templates src/core tests/unit

# Copy the API code and static files
COPY src/api/app.py src/api/
COPY src/api/static src/api/static
COPY src/api/templates src/api/templates

# Expose the API port
EXPOSE 5000

# Copy the indexing script
COPY src/core/index.py src/core/

# Copy test files
COPY tests/unit/ tests/unit/

# Add a dummy file to invalidate cache
ADD dummy.txt .

# Set Python path
ENV PYTHONPATH=/app/src

# Command to run the API
CMD ["python", "src/api/app.py"]