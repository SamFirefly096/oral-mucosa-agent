# oral-mucosa-agent-full — 项目指南

## 高优先级规则（H1）：图片传输一律走 DeepSeek Files API（file.api）

DeepSeek 官方提供 Files API（`POST https://api.deepseek.com/files`，multipart 字段 `file` + `purpose=user_data`，可选 `expires_after[seconds]`，1 小时～30 天），返回 `file_id`（形如 `file-api-...`），vision 模型（`deepseek-v4-flash-vision-exp`）用内容块 `{"type":"file","file_id":"..."}` 引用。相比内联 base64 data URL，file_id 引用显著减少 token 消耗与请求体积，并支持同图跨请求复用。

本环境已对 dsh-llm-deepseek 适配器打补丁（见 `.fileapi/` 目录）：所有图片在发送给 DeepSeek 前自动上传至 Files API 并以 file_id 引用（sha256 内容哈希缓存，同图不重复上传；上传失败自动回退内联 base64）。因此：

1. 凡需向模型传输图片，一律依赖该自动通道；**禁止**手动把图片转成 base64 塞进文本（除非 Files API 不可用）。
2. 需要图片供模型查看时用 read_image 等标准工具，不要手工构造 data URL。
3. 若升级后规则失效（补丁被覆盖），运行 `sudo python3 /opt/oral-mucosa-agent/.fileapi/patch-file-api.py` 重打并 `sudo systemctl restart dsh-web.service`。
4. 上传图片默认 30 天有效期；涉及敏感病例照片时保持该默认，不要设为永久。

## 规则（H2）：图片给用户看 —— 一律通过文档工作流面板

**本 GUI 的对话流不渲染图片**（markdown 图片被剥离为替代文字、工具结果图片不显示）；用户可见图片的可靠通道是「文档工作流」面板（docflow 静态插件）：图片条目显示缩略图，**点击缩略图弹出原图**。因此：

1. 生成、处理、下载完任何图片后，**必须**把图片文件按面板命名规范复制到 `/opt/oral-mucosa-agent/.docflow/uploads/`（`u_dsh_<seq>__<显示名>.<ext>`，seq 用字母递增避免重名），即注册进面板供用户查看。
2. 图片进入模型上下文（需要模型看图时）仍用 read_image（自动走 file.api）。
3. 删除已废弃的 show_image 工具与 /dsh-showimg 路由；对话流内不再承诺渲染图片。
4. 用户要求「看图片/显示图片」时，注册到面板后告知用户刷新面板查看（缩略图 + 点击原图）。

## 项目概述

基于 MIRA (Nature 2026) 架构的口腔黏膜病中西医结合AI诊断Agent系统。使用 DeepSeek V4 Pro 大语言模型，实现医生-患者双Agent对话、8个Function Calling工具、SQLite数据库（24例病例），已运行285次交叉对比实验。

## 多用户系统（v0.2.0）

- 用户账户存于 `data/users.db`（SQLite，PBKDF2 加盐哈希，不入 git）；令牌（token）30 天有效，存 `tokens` 表，服务重启不失效。
- **admin 为内置管理员**，密码 = `ACCESS_PASSWORD`（默认 `20260705`，**密码不变**），拥有最高权限：
  - 可查看/继续/删除**所有用户**的会话；普通用户只能访问自己的会话（后端 403 硬隔离，前端隐藏入口）。
  - 可访问 `/api/cases/debug`、`/api/cases/<id>/full`（含诊断标准答案）；普通用户 403。
  - 用户管理：`/api/admin/users` 系列（列表/创建/重置密码/禁用/删除）。
- 认证方式：登录/注册后前端携带 `X-Auth-Token` 头；401 自动跳转 `/login.html`。旧链接 `/?pw=密码` 兼容：正确则自动登录 admin 并重定向 `/?t=<token>`。
- 会话文件 `outputs/web_sessions/*.json` 已带 `user_id`/`username`；旧会话升级后归属 admin。每用户最多保留 100 个会话。
- 前端：`web/login.html` 登录/注册页；主界面移动端优先（底部Tab、底部弹层、`visualViewport` 键盘适配）。

## 语音功能（v0.2.0）

- **语音播报（TTS）**：浏览器 `speechSynthesis`，无 HTTPS 要求，直接可用。每条患者/医生回复下有「朗读」按钮；用户菜单可开启「自动朗读回复」。
- **语音输入（STT）**：Web Speech API（`SpeechRecognition`），**需要 HTTPS 安全上下文**（当前站点为 http://IP，入口按钮会置灰并提示）。接入 HTTPS（域名+证书）后即可用；否则需要第三方 ASR（讯飞/百度云等）或手机输入法语音键。
- 两种能力均浏览器端实现，服务器零改动。

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
| `app.py` | Flask Web服务（训练+咨询+检查+评分+导师+用户系统） | 多个API端点 |
| `user_store.py` | 用户账户/令牌（SQLite+PBKDF2，admin种子） | `check_login()`, `grant_token()`, `resolve_token()`, 管理员接口 |
| `config.py` | 全局配置（API密钥、模型、路径） | `DEEPSEEK_API_KEY`, `DATABASE_PATH`, `DIAGNOSIS_CATEGORIES` |
| `wang_cases.py` | 王雨田10个病例数据 | `add_cases()` |
| `add_clinical_cases.py` | 科室2个病例数据（脱敏） | `add_cases()` |
| `web/index.html` | 前端界面（三模式，移动端优先） | 训练（问诊+检查+诊断+评分+导师）/测试/咨询 |
| `web/login.html` | 登录/注册页面 | 用户系统入口 |

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
| `/` | GET | 主页面（未登录由前端跳转登录页；`?pw=`旧链接兼容） |
| `/login.html` | GET | 登录/注册页 |
| `/api/auth/login` | POST | 登录 `{username, password}` → `{token, user}` |
| `/api/auth/register` | POST | 注册 `{username, password, display_name}` → 自动登录 |
| `/api/auth/logout` | POST | 注销当前令牌 |
| `/api/auth/me` | GET | 当前用户信息 |
| `/api/auth/change_password` | POST | 修改自己密码 `{old_password, new_password}` |
| `/api/admin/users` | GET/POST | 用户列表 / 创建用户（仅admin） |
| `/api/admin/users/<id>/password` | POST | 重置密码（仅admin） |
| `/api/admin/users/<id>/disabled` | POST | 禁用/启用（仅admin） |
| `/api/admin/users/<id>` | DELETE | 删除用户（仅admin） |
| `/api/cases` | GET | 返回病例列表（训练模式不暴露诊断） |
| `/api/cases/debug` | GET | 全部病例+标准答案（**仅admin**） |
| `/api/cases/<id>/full` | GET | 单病例完整信息（**仅admin**） |
| `/api/chat/start` | POST | 初始化会话 `{mode, case_id?}` |
| `/api/chat/send` | POST | 发送消息 `{session_id, message}` |
| `/api/chat/examination` | POST | 申请检查 `{session_id, tool, params}` |
| `/api/chat/evaluate` | POST | 提交诊断评分 `{session_id, diagnosis, tcm_syndrome, treatment}` |
| `/api/chat/tutor_review` | POST | 导师点评 |
| `/api/chat/history?session_id=` | GET | 会话完整记录（仅归属者/admin） |
| `/api/sessions` | GET | 会话列表（普通用户仅自己的；admin全部） |
| `/api/sessions/<id>` | DELETE | 删除会话（仅归属者/admin） |
| `/api/photos/<case_id>` | GET | 获取病例照片URL列表 |
| `/api/photo/<path>` | GET | 提供照片文件 |

**认证**：所有 `/api/*`（除 login/register）需在 Header 携带 `X-Auth-Token: <token>`；401 → 前端跳转登录页。会话按用户隔离（普通用户 403 无法访问他人会话，admin 可访问全部）。

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

## GitHub 仓库

- 地址：https://github.com/SamFirefly096/oral-mucosa-agent
- Remote：`git@github.com:SamFirefly096/oral-mucosa-agent.git`（SSH）
- 更新流程：
```bash
cd "E:\OneDrive\智能体文章写作空间\oral-mucosa-agent-full"
git add -A
git commit -m "描述改动内容"
git push origin master
```
- `.gitignore` 排除了 `.env`、`outputs/`、`README_完整.md` 等敏感/本地文件
- 推送前检查 `git status`，确认不包含密钥或本地路径

## 版本与部署

**版本号**：`VERSION` 文件 + Git tag（当前 v0.1.0），每次发布递增。

**部署工作流（唯一通道）**：
```
本地改代码 → git commit → git push origin master → 等待2分钟 → 服务器自动部署
```

服务器通过 cron 每2分钟执行 `deploy/auto_pull.sh`：
1. `git fetch origin master` 检查新提交
2. 检测到新提交 → `git pull` → `systemctl restart oral-mucosa`
3. 日志：`/var/log/oral-mucosa/auto_pull.log`

**紧急手动部署**：
```bash
ssh root@123.56.96.19 "/opt/oral-mucosa-agent/deploy/auto_pull.sh"
```

**⛔ upload.ps1 已废弃** — scp直传绕过版本管理，曾导致服务器代码回退事故。禁止使用。

**版本发布清单**：
1. `echo "0.1.1" > VERSION`（递增版本号）
2. `git add -A && git commit -m "v0.1.1: 改动简述"`
3. `git tag -a v0.1.1 -m "v0.1.1: 改动简述"`
4. `git push origin master --tags`
5. 等待2分钟自动部署，或SSH手动触发

## 评分逻辑

- **西医诊断 (70%)**：关键词模糊匹配，答中核心疾病词即高分
- **治疗方案 (30%)**：8大方向匹配（局部/全身/抗炎/免疫/抗感染/止痛/卫生/随访），不要求具体药名
- **中医辨证**：额外加分 +0~10，关键词匹配（如脾、湿、热）
- 标准答案使用 ICD-11 中文名称，数据库已全部中文化
- 评分函数在 `app.py` 的 `evaluate()` 路由中

## 注意事项

- Bash环境输出经常为空，需 `script.py > output.txt 2>&1` 后Read读取
- 管理员账号：`admin` / `20260705`（= `.env` 的 `ACCESS_PASSWORD`，密码不变；修改 .env 只影响新库种子）
- 项目论文不引用王雨田相关内容
- 伦理审批为投稿前置条件（尚未获批）
- 本地完整说明在 `README_完整.md`（含服务器IP等敏感信息，不入git）

## 会场闸门与演示实例（v0.2.1+）

- **闸门**：生产实例设 `OM_GATE_DEMO=1` 后，访问 `/`、`/index.html`、`/login.html` 的普通访客一律 302 到 `/demo/`；
  管理员不受影响。三种放行方式：① `?pw=ACCESS_PASSWORD`（管理员引导登录）② `?t=<有效管理员令牌>` ③ 管理员登录时种下的 `om_prod_token` Cookie（HttpOnly，30 天，注销即清）。
  需要额外放行某个非管理员账号时设 `OM_GATE_EXCEPT_USERS=用户名1,用户名2`。
- **管理员入口**：https://<域名>/?pw=<ACCESS_PASSWORD> ，进入后自动种 Cookie，之后直接访问即可。
- **演示实例**：systemd `oral-mucosa-demo`（127.0.0.1:5001，nginx `/demo/` 反代，单 worker + 64 线程）。
  白名单仅 10 例虚构病例；照片接口 403 且 `PHOTO_DIR` 指向空目录；每账号 3 次问诊、每次 15 轮、全站日 200 次熔断；
  页面顶部注入免责横幅（fixed 整行居中，脚本按实际高度给 body 让位）。
  **注意**：会话是进程内存态，多 worker 会丢会话，必须保持 `-w 1`。
