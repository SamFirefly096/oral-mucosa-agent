#!/bin/bash
# ============================================================
#  口腔黏膜病AI诊断Agent — 首次部署脚本
#  在云服务器上执行: curl -fsSL <raw-url>/deploy.sh | bash
#  或: bash deploy.sh
# ============================================================
set -e

APP_DIR="/opt/oral-mucosa-agent"
REPO_URL="${REPO_URL:-}"  # 如果使用 git 部署，填入仓库地址
BRANCH="${BRANCH:-master}"

echo "========================================"
echo " 口腔黏膜病AI诊断Agent — 首次部署"
echo "========================================"

# ── 1. 检查环境 ──
command -v python3 >/dev/null 2>&1 || { echo "请先安装 Python 3.12+"; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo "请先安装 pip3"; exit 1; }

# ── 2. 创建目录 ──
sudo mkdir -p "$APP_DIR" /var/log/oral-mucosa
sudo chown -R "$USER:$USER" "$APP_DIR"

# ── 3. 上传代码（选择一种方式） ──
if [ -n "$REPO_URL" ]; then
    echo "[*] 从 git 克隆..."
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
else
    echo "[!] 未设置 REPO_URL，请手动上传代码到 $APP_DIR"
    echo "    推荐: rsync -avz ./ oral-mucosa-agent user@server:$APP_DIR/"
    echo "    或: scp -r ./ user@server:$APP_DIR/"
fi

# ── 4. 配置环境 ──
cd "$APP_DIR"
if [ ! -f .env ]; then
    echo "[*] 创建 .env 文件..."
    cp .env.example .env
    echo ">>> 请编辑 $APP_DIR/.env，填入 DEEPSEEK_API_KEY"
fi

# ── 5. 安装依赖 ──
echo "[*] 安装 Python 依赖..."
pip3 install -r requirements.txt

# ── 6. 设置 systemd 服务 ──
echo "[*] 配置 systemd 服务..."
sudo tee /etc/systemd/system/oral-mucosa.service > /dev/null <<'SYSTEMD'
[Unit]
Description=口腔黏膜病AI诊断Agent
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/oral-mucosa-agent
EnvironmentFile=/opt/oral-mucosa-agent/.env
ExecStart=/usr/bin/python3 -m gunicorn wsgi:app -w 4 -b 127.0.0.1:5000 --access-logfile /var/log/oral-mucosa/access.log --error-logfile /var/log/oral-mucosa/error.log
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SYSTEMD

# ── 7. 启动服务 ──
sudo systemctl daemon-reload
sudo systemctl enable oral-mucosa
sudo systemctl start oral-mucosa

# ── 8. 配置 Nginx ──
if command -v nginx >/dev/null 2>&1; then
    echo "[*] 配置 Nginx..."
    sudo cp deploy/nginx.conf /etc/nginx/conf.d/oral-mucosa.conf
    echo ">>> 请编辑 /etc/nginx/conf.d/oral-mucosa.conf，将 your-domain.com 替换为实际域名"
    sudo nginx -t && sudo systemctl reload nginx
else
    echo "[!] 未检测到 nginx，请手动安装并配置反向代理"
    echo "    配置模板: $APP_DIR/deploy/nginx.conf"
fi

# ── 9. 验证 ──
sleep 2
echo ""
echo "========================================"
echo " 部署完成"
echo "========================================"
echo " 健康检查: curl http://127.0.0.1:5000/api/cases"
echo " 服务状态: sudo systemctl status oral-mucosa"
echo " 查看日志: sudo journalctl -u oral-mucosa -f"
echo "========================================"
