# oral-mucosa-agent-full — 项目指南

## 项目概述

基于 MIRA (Nature 2026) 架构的口腔黏膜病中西医结合AI诊断Agent系统。使用 DeepSeek V4 Pro 大语言模型，实现医生-患者双Agent对话、8个Function Calling工具、SQLite数据库（24例病例），已运行285次交叉对比实验。

## 快速启动

```bash
# 安装依赖
pip install flask flask-cors openai pydantic python-dotenv tenacity

# 启动Web服务（医学生训练+患者咨询）
python app.py
# 访问 http://localhost:5000，密码 20260705

# 终端命令行模式
python run_simulation.py --case OLP001              # 单例交互
python run_simulation.py --all --quiet              # 全量运行
python wang_cases.py                                # 追加王雨田病例
python add_clinical_cases.py                        # 追加科室病例
python evaluate.py                                  # 评估
```

## 核心模块

| 文件 | 功能 | 关键类/函数 |
|------|------|------------|
| `agents.py` | 原始Agent（MedAssistant + PatientAssistant） | `MedAssistant.chat()`, `PatientAssistant.chat()` |
| `agents_enhanced.py` | 增强版Agent（3类医生 + 2类患者 + 融合型） | `LearningMedAgent`, `TextbookMedAgent`, `ChiefMedAgent`, `OriginalPatientAgent`, `RealisticPatientAgent` |
| `tools.py` | 8个Pydantic工具定义（JSON Schema） | `OralExamination`, `TCMFourDiagnosis`, `DiagnosisAndPlan` 等 |
| `tool_executors.py` | 工具执行器（SQLite查询→格式化返回） | `FUNC_MAP = {tool_name: executor_fn}` |
| `database.py` | SQLite 11表 + 24例数据 + TCM数据 | `create_database()`, `query_table()`, `get_hpi_text()` |
| `conversation.py` | 对话流程引擎 | `run_conversation(med, pat, ctx, complaint, max_turns)` |
| `run_simulation.py` | CLI运行入口 | `--case`, `--all`, `--quiet`, `--list` |
| `evaluate.py` | 评估脚本 | `evaluate_all()`, `evaluate_case()` |
| `app.py` | Flask Web服务（训练+咨询+检查+评分+导师） | 多个API端点 |
| `config.py` | 全局配置（API密钥、模型、路径） | `DEEPSEEK_API_KEY`, `DATABASE_PATH`, `DIAGNOSIS_CATEGORIES` |
| `wang_cases.py` | 王雨田10个病例数据 | `add_cases()` |
| `add_clinical_cases.py` | 科室2个病例数据（脱敏） | `add_cases()` |
| `web/index.html` | 前端界面（双模式） | 训练模式（问诊+检查+诊断+评分+导师） |
| `web/login.html` | 登录页面 | 密码验证 |

## 24例病例来源

| 批次 | 数量 | 来源 | hadm_id前缀 |
|------|:--:|------|------------|
| 原始教学病例 | 12 | 教科书+指南构建 | OLP001,PV001,OC001,RAS001,HSV001,DLE001,LEUK001,EM001,ANUG001,LR001,ATOLP001,BP001 |
| 王雨田病例报告 | 10 | PDF提取→脱敏→入库 | ROM001,LEUK002,PV002,HZ001,EM002,AOU001,MRAS001,OLL001,WSN001,CC001 |
| 科室真实病例 | 2 | 临床诊疗记录脱敏 | PIM001,MRS001 |

## 6组实验架构

```
3类医生Agent × 2类患者Agent = 6组
├── LearningMedAgent (经验驱动/24例模式/t=0.01)
├── TextbookMedAgent (纯教科书/t=0.01)
└── ChiefMedAgent (融合型/双重验证/t=0.01)

×
├── OriginalPatientAgent (条理清晰/t=0.3)
└── RealisticPatientAgent (混乱矛盾跑题/t=0.7/max_tokens=300)
```

累计285次独立运行，结果见 `outputs/results/eval_latest.txt`。

## 电池分析脚本（E:\工作目录\tmp\）

| 文件 | 功能 |
|------|------|
| `run_4_compare.py` | 4组对比实验 |
| `compare_using_conversation.py` | 使用项目conversation的对比 |
| `batch_Lrn_Org.py` 等4个 | 批量运行（4组×24例） |
| `batch_Chief_Org.py` 等2个 | Chief Agent批量运行 |
| `analyze_all_6.py` | 6组统计分析→`all6_report.txt` |
| `run_one_experiment.py` | 单实验运行 `--med learn/text --pat orig/real` |
| `full_eval.py` | 全量评估（22例） |
| `retry_chief.py` | 重试失败Chief实验 |

## Web服务API

| 端点 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 主页面（需密码） |
| `/api/cases` | GET | 返回24例列表 |
| `/api/chat/start` | POST | 初始化会话 `{mode, case_id?}` |
| `/api/chat/send` | POST | 发送消息 `{session_id, message}` |
| `/api/chat/examination` | POST | 申请检查 `{session_id, tool, params}` |
| `/api/chat/evaluate` | POST | 提交诊断评分 `{session_id, diagnosis, tcm_syndrome, treatment}` |
| `/api/chat/tutor_review` | POST | 导师点评 |
| `/api/photos/<case_id>` | GET | 获取病例照片URL列表 |
| `/api/photo/<path>` | GET | 提供照片文件 |

所有API需在Header中携带 `X-Access-Password: 20260705`。

## 关键数据路径

- 数据库：`data/oral_mucosa.db`
- 对话记录：`outputs/conversations/`（命名：`{病例}_{医生}_{患者}_{时间戳}.json`）
- 评估报告：`outputs/results/eval_latest.txt`
- 6组报告：`E:\工作目录\tmp\all6_report.txt`
- 临床照片：`E:\工作目录\病例\{hadm_id}/`（12/24例有照片，共106张）
- 投稿稿件：`E:\OneDrive\智能体文章写作空间\输出\课题申报\口腔黏膜病AI诊断Agent论文_投稿版v3.docx`
- 伦理材料：`E:\OneDrive\智能体文章写作空间\输出\课题申报\伦理材料\`
- 技术路线图：`E:\OneDrive\智能体文章写作空间\输出\课题申报\技术路线图.html`

## 环境要求

- Python 3.14：`C:\Users\admin\AppData\Local\Python\pythoncore-3.14-64\python.exe`
- .env文件配置 `DEEPSEEK_API_KEY`
- 依赖：openai, pydantic, python-dotenv, tenacity, flask, flask-cors

## 注意事项

- Bash环境输出经常为空，需 `script.py > output.txt 2>&1` 后Read读取
- 训练模式密码：`20260705`
- 项目论文不引用王雨田相关内容
- 伦理审批为投稿前置条件（尚未获批）
