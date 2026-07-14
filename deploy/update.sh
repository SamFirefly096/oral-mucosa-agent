#!/bin/bash
# ============================================================
#  口腔黏膜病AI诊断Agent — 更新脚本
#  用法: bash update.sh [选项]
#
#  选项:
#    --restart    仅重启服务
#    --logs       查看最近日志
#    --status     查看服务状态
#    --rollback   回滚到上一个备份
#   (无参数)      执行完整更新流程
# ============================================================
set -e

APP_DIR="/opt/oral-mucosa-agent"
BACKUP_DIR="/opt/oral-mucosa-backups"
SERVICE="oral-mucosa"
REPO_URL="${REPO_URL:-}"
BRANCH="${BRANCH:-master}"

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }

# ── 仅重启 ──
if [ "$1" = "--restart" ]; then
    echo "重启服务..."
    sudo systemctl restart "$SERVICE"
    sleep 2
    sudo systemctl status "$SERVICE" --no-pager
    exit 0
fi

# ── 查看日志 ──
if [ "$1" = "--logs" ]; then
    sudo journalctl -u "$SERVICE" -n 50 --no-pager -f
    exit 0
fi

# ── 状态 ──
if [ "$1" = "--status" ]; then
    sudo systemctl status "$SERVICE" --no-pager
    echo ""
    curl -s http://127.0.0.1:5000/api/cases | python3 -m json.tool | head -20
    exit 0
fi

# ── 回滚 ──
if [ "$1" = "--rollback" ]; then
    LATEST=$(ls -dt "$BACKUP_DIR"/*/ 2>/dev/null | head -1)
    if [ -z "$LATEST" ]; then
        err "没有可用的备份"
        exit 1
    fi
    echo "准备回滚到: $LATEST"
    echo -n "确认回滚? 服务将短暂中断 [y/N]: "
    read -r CONFIRM
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "已取消"
        exit 0
    fi
    sudo systemctl stop "$SERVICE"
    rsync -av --delete "$LATEST" "$APP_DIR/"
    sudo systemctl start "$SERVICE"
    sleep 2
    sudo systemctl status "$SERVICE" --no-pager
    info "回滚完成"
    exit 0
fi

# ════════════════════════════════════════
#  完整更新流程
# ════════════════════════════════════════

echo "========================================"
echo " 口腔黏膜病AI诊断Agent — 更新"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

# ── 1. 备份当前版本 ──
BACKUP_PATH="$BACKUP_DIR/$(date '+%Y%m%d_%H%M%S')"
info "备份到 $BACKUP_PATH"
sudo mkdir -p "$BACKUP_PATH"
sudo cp -r "$APP_DIR"/* "$BACKUP_PATH/" 2>/dev/null || true
# 只保留最近 5 个备份
sudo ls -dt "$BACKUP_DIR"/*/ 2>/dev/null | tail -n +6 | sudo xargs rm -rf 2>/dev/null || true

# ── 2. 拉取最新代码 ──
cd "$APP_DIR"
if [ -n "$REPO_URL" ] && [ -d .git ]; then
    info "拉取最新代码..."
    git fetch origin "$BRANCH"
    git reset --hard "origin/$BRANCH"
elif [ -f wsgi.py ]; then
    info "代码已存在，执行文件级别的增量更新"
else
    err "代码不存在且未配置 REPO_URL，请手动上传代码"
    exit 1
fi

# ── 3. 安装/更新依赖 ──
info "检查依赖..."
if [ -f requirements.txt ]; then
    pip3 install -r requirements.txt --quiet
fi

# ── 4. 重启服务（零停机 — 逐 worker 重启） ──
info "重启服务..."
sudo systemctl restart "$SERVICE"
sleep 2

# ── 5. 健康检查 ──
info "健康检查..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/api/cases --max-time 5 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "401" ]; then
    info "服务健康 (HTTP $HTTP_CODE)"
else
    err "健康检查失败 (HTTP $HTTP_CODE)，正在回滚..."
    sudo systemctl stop "$SERVICE"
    rsync -av --delete "$BACKUP_PATH/" "$APP_DIR/"
    sudo systemctl start "$SERVICE"
    sleep 2
    err "已回滚到备份版本，请检查日志"
    exit 1
fi

# ── 6. 验证 ──
echo ""
info "更新完成"
echo "  服务状态: $(sudo systemctl is-active $SERVICE)"
echo "  监听端口: $(ss -tlnp | grep 5000 | head -1)"
echo "  查看日志: bash update.sh --logs"
