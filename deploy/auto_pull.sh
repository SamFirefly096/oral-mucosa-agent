#!/bin/bash
# 自动部署：仅在「远端领先且工作区干净」时快进合并。
# 严禁 git reset --hard —— 服务器上可能存在未提交改动或本地提交（如现场修复），
# 旧版脚本会因 LOCAL != REMOTE 直接 reset，导致这些工作被静默丢弃（2026-09-11 事故）。
set -u
cd /opt/oral-mucosa-agent

git fetch origin master 2>/dev/null || { echo "[$(date '+%F %T')] fetch 失败，跳过"; exit 0; }
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/master)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "[$(date '+%F %T')] 无更新。"
    exit 0
fi

# 本地领先或历史分叉 → 绝不覆盖
if ! git merge-base --is-ancestor "$LOCAL" "$REMOTE"; then
    echo "[$(date '+%F %T')] 本地领先/分叉（LOCAL=$LOCAL REMOTE=$REMOTE），跳过自动部署，请人工处理。"
    exit 0
fi

# 工作区有未提交改动 → 不部署，避免覆盖
if [ -n "$(git status --porcelain)" ]; then
    echo "[$(date '+%F %T')] 工作区有未提交改动，跳过自动部署，请人工处理。"
    exit 0
fi

echo "[$(date '+%F %T')] 快进部署 $LOCAL -> $REMOTE"
git merge --ff-only origin/master || { echo "  merge 失败，已中止"; exit 1; }
sudo systemctl restart oral-mucosa
echo "[$(date '+%F %T')] 部署完成，服务已重启。"
