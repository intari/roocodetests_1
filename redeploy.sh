#!/bin/bash
git reset --hard
git pull -v
docker-compose down
docker-compose up --force-recreate --build -d