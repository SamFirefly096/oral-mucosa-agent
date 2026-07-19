#!/bin/bash
# Auto-pull from GitHub and deploy if new commits detected.
# Triggered by cron every 2 minutes. Logs to /var/log/oral-mucosa/auto_pull.log
set -e

cd /opt/oral-mucosa-agent
git fetch origin master 2>/dev/null

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] New commit detected, deploying..."
    git pull origin master
    sudo systemctl restart oral-mucosa
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Deploy complete, service restarted."
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] No update."
fi
