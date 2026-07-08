# Oral Mucosa AI Diagnosis Agent

基于 **MIRA (Nature 2026)** 架构的口腔黏膜病中西医结合AI诊断系统。使用大语言模型的 Function Calling 能力，实现自主医疗诊断 Agent。

## 快速启动

```bash
# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 初始化数据库
python -c "from database import create_database; create_database()"

# 运行仿真
python run_simulation.py --list          # 列出所有病例
python run_simulation.py --case OLP001   # 单例交互
python run_simulation.py --all --quiet   # 全量运行
python evaluate.py                       # 评估结果
```

## Web 服务

```bash
python app.py
# 访问 http://localhost:5000（默认密码见 .env）
```

提供两种模式：
- **医学生训练**：模拟真实患者问诊，支持口腔检查/化验/病理/中医四诊等 5 类辅助检查，诊断后自动评分 + 导师点评
- **患者咨询**：主任医师Agent在线答疑

## 项目结构

```
├── agents.py / agents_enhanced.py  # MedAgent + PatientAgent
├── database.py                     # SQLite 数据库
├── tools.py / tool_executors.py    # 8个 Function Calling 工具
├── conversation.py                 # 对话循环引擎
├── run_simulation.py               # CLI 运行入口
├── app.py / config.py              # Web 服务 + 配置
├── wsgi.py                         # 生产入口 (gunicorn/waitress)
├── Dockerfile / docker-compose.yml # 容器部署
├── deploy/                         # 部署脚本 + nginx 配置
├── web/                            # 前端 (index.html + app.js)
├── data/                           # 数据库文件
├── outputs/                        # 对话记录 + 评估报告
└── scripts/                        # 辅助脚本
```

## 实验架构

6 组交叉实验（3 类医生 × 2 类患者），累计 285 次独立运行：

| 医生 Agent | 患者 Agent |
|-----------|-----------|
| LearningMedAgent (经验驱动) | OriginalPatientAgent (条理清晰) |
| TextbookMedAgent (纯教科书) | RealisticPatientAgent (混乱矛盾) |
| ChiefMedAgent (融合型双重验证) | |

## 部署

### Docker
```bash
docker compose up -d
```

### 裸机
```bash
bash deploy/deploy.sh
```

### GitHub Actions (push 自动部署)
配置仓库 Secrets：`SSH_HOST` / `SSH_USER` / `SSH_KEY`，推送即部署。

## 参考文献

- Ferber D, et al. Towards autonomous medical AI agents. *Nature*, 2026
- 徐治鸿. 中西医结合口腔黏膜病学. 人民卫生出版社, 2008
