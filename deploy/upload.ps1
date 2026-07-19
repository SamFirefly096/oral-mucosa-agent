# ============================================================
#  ⛔ 已废弃 — 请勿使用！
#  v0.1.0起改用纯Git工作流：commit → push → 服务器自动pull
#  服务器每2分钟自动检测GitHub更新并部署（cron + auto_pull.sh）
#
#  如需紧急部署：ssh root@123.56.96.19 "/opt/oral-mucosa-agent/deploy/auto_pull.sh"
# ============================================================
#  一键上传部署脚本 (Windows PowerShell) — 【已废弃，仅保留供参考】
#  用法: .\deploy\upload.ps1 -Server user@1.2.3.4
#
#  前提条件:
#    1. Windows 已安装 OpenSSH Client (Win10+ 自带)
#    2. 服务器已按 deploy/deploy.sh 完成首次部署
#    3. 已配置 SSH 密钥免密登录: ssh-copy-id user@server
# ============================================================
param(
    [Parameter(Mandatory=$true, HelpMessage="服务器地址，如 root@1.2.3.4")]
    [string]$Server,

    [Parameter(HelpMessage="服务器项目路径，默认 /opt/oral-mucosa-agent")]
    [string]$RemotePath = "/opt/oral-mucosa-agent",

    [Parameter(HelpMessage="仅上传代码，不重启服务")]
    [switch]$NoRestart,

    [Parameter(HelpMessage="上传后仅重启，不传输文件")]
    [switch]$RestartOnly
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ProjectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  口腔黏膜病AI诊断Agent — 一键部署" -ForegroundColor Cyan
Write-Host "  目标: $Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($RestartOnly) {
    Write-Host "[*] 仅重启服务..." -ForegroundColor Yellow
    ssh $Server "sudo systemctl restart oral-mucosa && sudo systemctl status oral-mucosa --no-pager"
    exit 0
}

# ── 1. 上传代码 ──
$excludeFile = Join-Path $ProjectRoot ".rsyncignore"
if (-not (Test-Path $excludeFile)) {
    @"
.env
.git/
__pycache__/
.venv/
venv/
outputs/
*.db
*.pyc
"@ | Out-File -FilePath $excludeFile -Encoding UTF8
}

Write-Host "[1/3] 上传代码..." -ForegroundColor Green
# 使用 scp (Windows 自带) — 增量上传项目文件
# 排除 .git, outputs, __pycache__, .env 等
$excludeItems = @(
    ".git", "__pycache__", ".venv", "venv", "outputs",
    "*.pyc", ".env", ".rsyncignore", "Thumbs.db", "Desktop.ini"
)

# 构建 rsync 命令 (如果服务器有 rsync) 或 fallback 到 tar+scp
Write-Host "  检查服务器 rsync 可用性..."
$hasRsync = (ssh $Server "command -v rsync && echo YES || echo NO") -match "YES"

if ($hasRsync) {
    Write-Host "  使用 rsync 增量同步 (仅传输变更文件)..." -ForegroundColor Green
    # 从 Windows 端使用 rsync (需要安装 Git Bash 的 rsync 或 WSL)
    # Fallback: 使用 scp 打包方式
    $tempTar = Join-Path $env:TEMP "oral-mucosa-deploy.tar.gz"
    $excludeArgs = ($excludeItems | ForEach-Object { "--exclude=$_" }) -join " "

    # rsync via WSL if available
    $wslCheck = wsl --status 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  通过 WSL rsync 同步..."
        $winPath = ($ProjectRoot -replace '\\', '/') -replace '^([A-Z]):', '/mnt/$1'
        $winPath = $winPath.ToLower()
        wsl rsync -avz --delete $excludeArgs "$winPath/" "$Server`:$RemotePath/"
    } else {
        Write-Host "  rsync 不可用，使用 scp 打包上传..." -ForegroundColor Yellow
        # tar + gzip + scp + remote extract
        $tarCmd = "tar czf $tempTar -C `"$ProjectRoot`" $excludeArgs ."
        cmd /c $tarCmd 2>$null
        # Actually let's just use scp -r with individual files for simplicity
        Write-Host "  使用 scp 上传 (首次可能较慢)..." -ForegroundColor Yellow
        scp -r -o StrictHostKeyChecking=no (
            Get-ChildItem $ProjectRoot -File -Exclude $excludeItems | Where-Object { $_.DirectoryName -notmatch '\.git|__pycache__|\.venv|outputs' }
        ) "$Server`:$RemotePath/"
    }
} else {
    Write-Host "  使用 tar+scp 打包上传..." -ForegroundColor Yellow
    $tempTar = Join-Path $env:TEMP "oral-mucosa-deploy.tar.gz"

    # Create tar.gz excluding unnecessary files
    Push-Location $ProjectRoot
    $filesToArchive = Get-ChildItem -Recurse -File |
        Where-Object {
            $rel = $_.FullName.Substring($ProjectRoot.Length).TrimStart('\','/')
            -not ($rel -match '\\\.git\\|\\\.git$|\\__pycache__\\|\\outputs\\|\\\.venv\\|\.pyc$|\\\.env$|Thumbs\.db|Desktop\.ini')
        }

    # Use Git Bash tar if available
    $gitBashTar = "C:\Program Files\Git\usr\bin\tar.exe"
    if (Test-Path $gitBashTar) {
        & $gitBashTar czf $tempTar --exclude=.git --exclude=__pycache__ --exclude=outputs --exclude=.venv --exclude=.env -C $ProjectRoot .
    }
    Pop-Location

    Write-Host "  上传 $((Get-Item $tempTar).Length / 1KB) KB ..."
    scp $tempTar "$Server`:/tmp/oral-mucosa-deploy.tar.gz"

    Write-Host "  服务器解压..."
    ssh $Server "cd $RemotePath && sudo tar xzf /tmp/oral-mucosa-deploy.tar.gz && rm /tmp/oral-mucosa-deploy.tar.gz"
    Remove-Item $tempTar -Force
}

# ── 2. 安装依赖 ──
if (-not $NoRestart) {
    Write-Host "[2/3] 检查并更新依赖..." -ForegroundColor Green
    ssh $Server "cd $RemotePath && pip3 install -r requirements.txt -q"
}

# ── 3. 重启服务 ──
if (-not $NoRestart) {
    Write-Host "[3/3] 重启服务..." -ForegroundColor Green
    ssh $Server "sudo systemctl restart oral-mucosa && sleep 2 && sudo systemctl is-active oral-mucosa"

    # ── 健康检查 ──
    Write-Host "  健康检查..." -ForegroundColor Green
    $health = ssh $Server "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5000/api/cases --max-time 5"
    if ($health -match "200|401") {
        Write-Host "  [OK] 服务正常 (HTTP $health)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] 服务异常 (HTTP $health)，请检查日志" -ForegroundColor Red
        Write-Host "  ssh $Server 'sudo journalctl -u oral-mucosa -n 30'" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  部署完成" -ForegroundColor Cyan
Write-Host "  查看日志: ssh $Server 'sudo journalctl -u oral-mucosa -f'" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
