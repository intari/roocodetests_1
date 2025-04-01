
# What it IS?

## TypeMind Plugin: EPUB/PDF/TXT Search Integration  

A plugin for [TypeMind](https://docs.typingmind.com/plugins/build-a-typingmind-plugin) that mimics the **WebSearch** feature but focuses on retrieving books/documents. Users can query, e.g., *"Find me books about Hecate"*, and the plugin returns **clickable links** to relevant files (EPUB, PDF, TXT).  

### Features  
- **File Formats**: Supports EPUB, PDF, and TXT (assumed compatibility).  
- **Requirement**: Users must provide their own files for indexing.  

### Technical Context  
- **Language**: Python.  
- **Skill Level**:  
  - My Python knowledge is **extremely rusty** (last project: a not too simple game bot years ago).  
  - Self-assessment: **Python novice**.  
- **Tools Used**:  
  - **Sonnet 3.7** and **DeepSeek-V3-0324** (for AI/ML integration).  
  - **RooCode** 

### Purpose  
1. **Experiment**: Test RooCode’s capabilities and identify practical applications.  
2. **Non-Production**: **⚠️ Do NOT deploy this in production** (even if "fixed" by someone).  

---

### Key Notes  
- Humor/self-deprecation preserved (e.g., "extremely rusty," "novice").  
- Technical terms standardized (Sonnet 3.7, DeepSeek-V3-0324).  
- Critical warnings emphasized (**bold + emoji** for production risk).  



# Application Deployment Guide (Ubuntu LTS)

## Prerequisites

### System Requirements
- Ubuntu 22.04 LTS (64-bit)
- Minimum 2 CPU cores, 4GB RAM
- 20GB free disk space
- Open ports: 8000 (app), 9200 (Elasticsearch)

### Required Software
```bash
# Update package lists
sudo apt update

# Install Docker and Docker Compose
sudo apt install -y docker.io docker-compose
sudo systemctl enable --now docker

# Add current user to docker group (logout required)
sudo usermod -aG docker $USER
```

## Environment Configuration

1. Clone the repository:
```bash
git clone https://github.com/intari/roocodetests_1.git
cd roocodetests_1
```

2. Configure environment variables:
```bash
# Copy example .env file
cp .env.example .env

# Edit configuration (nano/vim)
nano .env
```
Key variables to configure:
- `BASE_URL`: Public URL of your application
- `ELASTICSEARCH_PASSWORD`: Secure password for Elasticsearch
- `CPU_LIMIT`: CPU cores to allocate (default: 2)

## Application Deployment

1. Start all services:
```bash
docker-compose up -d
```

2. Verify services are running:
```bash
docker-compose ps
```

3. Check application logs:
```bash
docker-compose logs -f api
```

4. Access the application:
- Web interface: http://your-server-ip:8000
- Elasticsearch: http://your-server-ip:9200

## Maintenance

## restart & rebuild
```bash
docker-compose down && docker-compose up -d --build
```

Logs 
```bash
 docker logs booksearch_app  -f
```

### Log Rotation
Configure Docker log rotation in `/etc/docker/daemon.json`:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```
Then restart Docker:
```bash
sudo systemctl restart docker
```

### Backups
1. Create backup script (`/usr/local/bin/backup-app.sh`):
```bash
#!/bin/bash
BACKUP_DIR=/var/backups/app
mkdir -p $BACKUP_DIR
docker-compose exec -T elasticsearch curl -X POST "localhost:9200/_snapshot/backup_repo/_all" -H "Content-Type: application/json"
docker-compose exec -T elasticsearch curl -X GET "localhost:9200/_snapshot/backup_repo/snapshot_$(date +%Y-%m-%d)?pretty"
```

2. Make executable and schedule daily cron job:
```bash
sudo chmod +x /usr/local/bin/backup-app.sh
sudo crontab -e
# Add: 0 3 * * * /usr/local/bin/backup-app.sh
```

### Updates
1. Pull latest changes:
```bash
git pull origin main
```

2. Rebuild containers:
```bash
docker-compose up -d --build
```

## Troubleshooting

### Common Issues

**Application not starting:**
```bash
# Check container status
docker ps -a

# View logs
docker-compose logs api
```

**Elasticsearch health issues:**
```bash
# Check cluster health
curl -X GET "localhost:9200/_cluster/health?pretty"

# Check node stats
curl -X GET "localhost:9200/_nodes/stats?pretty"
```

**Port conflicts:**
```bash
# Check used ports
sudo netstat -tulnp

# Change ports in docker-compose.yml if needed
```

### Debugging
1. Access running container shell:
```bash
docker-compose exec api bash
```

2. Check resource usage:
```bash
docker stats
```

## Check Request via JSON :
curl -H "Accept: application/json" -X GET https://booksearch.yourdomain.com/search?query=android

# Simple search
curl -H "Accept: application/json" "https://booksearch.yourdomain.com/search?query=android"

# Search with format parameter
curl "https://booksearch.yourdomain.com/search?query=android&format=json"

# Error case
curl -H "Accept: application/json" "https://booksearch.yourdomain.com/search"


## API Endpoints

### Search API
```
GET /search?query={query}[&format=json]
```

### Reset Elasticsearch Index
```
POST /reset_index
Headers:
- Authorization: Basic base64(username:password)
```

Example:
```bash
curl -X POST -u admin:securepassword123 https://booksearch.yourdomain.com/reset_index
```

## References
- [Ubuntu Docker Installation](https://docs.docker.com/engine/install/ubuntu/)
- [Docker Compose Reference](https://docs.docker.com/compose/reference/)
- [Elasticsearch Documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html)


## Plugin-alt
method:get 
https://booksearch.yourdomain.com/search?query={prompt}&format=json
alt version for plugin
request headers 
{
"Accept": "application/json"
}