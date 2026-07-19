# 操作日志

## v0.1.1 (2026-07-19)
- **Git自动部署**：服务器配置cron每2分钟执行auto_pull.sh，检测GitHub新提交自动git reset --hard + 重启服务
- **废弃upload.ps1**：scp直传通道已废弃（曾导致服务器代码回退事故），统一使用Git工作流
- **修复**：auto_pull.sh改用reset --hard替代git pull，避免未跟踪文件冲突
- **权限修复**：修复服务器上auto_pull.sh执行权限丢失问题

## v0.1.0 (2026-07-19)
- **版本管理建立**：创建VERSION文件，Git tag v0.1.0
- **恢复测试模式**：部署完整开发版到服务器，恢复 /api/cases/debug 调试端点、test_mode会话配置、SearchClinicalKnowledge知识检索工具
- **图片恢复**：服务器cases_photos被误删，从本地E:\工作目录\病例打包上传217张图片（357MB）恢复
- **Git历史合并**：拉取服务器2个额外提交（.gitignore + 分支统一），合并本地6个修改文件
- **服务器信息记录**：将云服务器IP、配置、常用命令写入工作区记忆

## 项目初始化 (2026-07-02 ~ 2026-07-08)
- **Initial commit** (c4109ae)：口腔黏膜病AI诊断Agent初始代码
- **CI/CD workflow** (adbf86d)：添加GitHub Actions工作流（后移除cf64a50）
- **分支统一** (0d4e1a0)：统一分支名为master
- **.gitignore** (8fbe594)：cases_photos加入忽略列表
- **首轮实验**：22例基准评估（西医81.8%匹配），6组Agent全量对比（285次独立运行），11例验证集（西医100%匹配）

## 部署基础 (2026-07-08前)
- 阿里云ECS首次部署：2vCPU/2GB/40G SSD，公网IP 123.56.96.19
- 环境搭建：Python 3.12+, systemd (oral-mucosa), Nginx反向代理 :80→:5000
- 数据库：SQLite 14张表，24例病例数据（12教学+10王雨田+2科室）
