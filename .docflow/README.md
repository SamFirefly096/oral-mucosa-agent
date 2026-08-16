# DSH 文档工作流（docflow）

在 DeepSeek Harness（DSH）中以 **Cordis 动态插件**形式运行的文档处理工作流：上传或拖入 docx/pdf/ppt/txt 文件，按对话要求**生成 / 修改精美文档**（docx / pptx / pdf），并支持**真实文献检索、核查、提炼与审阅**，浏览器一键下载。

## 功能一览

| 能力 | 说明 |
| --- | --- |
| 📎 文件上传 | 浏览器面板 + 输入区按钮 + **拖入输入区**（图片拖入放行原生附件） |
| 📄 文档生成 | markdown → 精美 docx / pptx / pdf（封面、6 套主题配色、表格、引用、代码块、页眉页脚页码） |
| ✏️ 文档修改 | 查找替换、改标题、追加内容、换主题色（输出为新文件） |
| 🔄 格式转换 | docx / pptx / pdf 互转 |
| 📚 文献检索 | **PubMed/Medline**（NCBI E-utilities 官方 API）真实检索，含 PMID、DOI、摘要 |
| 🔍 Crossref 补充 | DOI 权威注册库检索（中文期刊、会议论文、专著章节） |
| ✅ 文献核查 | 逐条与 PubMed / Crossref 官方数据比对，**防止引用不存在的文献** |
| 📖 引文格式 | **GB/T 7714-2015 顺序编码制**（中华口腔医学会格式），自动生成 `作者. 题名[J]. 刊名, 年, 卷(期): 页码.` |

## 目录结构

```
.docflow/
├── engine/docflow_engine.py   # Python 文档引擎（生成/编辑/提取/文献检索核查，单文件无依赖）
├── plugin/docflow-host.js     # 插件 Host 半体（RPC、模型工具、下载路由）
├── plugin/docflow-client.js   # 插件 Client 半体（浏览器面板、上传按钮、拖放层）
├── plugin/docflow.json        # 插件定义元数据（自动恢复说明）
└── README.md                  # 本说明
```

运行时目录（不入库）：`venv/`（Python 虚拟环境）、`uploads/`、`outputs/`、`tmp/`。

## 快速开始

### 1. 准备引擎环境（一次性）

```bash
cd .docflow
python3 -m venv venv
venv/bin/pip install python-docx python-pptx pdfplumber reportlab
```

### 2. 在 DSH 会话中定义并运行插件

以 `cordis_define`（`code.host` ← `docflow-host.js`，`code.client` ← `docflow-client.js`）定义插件，再 `cordis_run` 激活；Client 半体需用户批准一次。

> 动态插件在 DSH 进程重启后丢失。已提供持久化定义与「文档工作流」agent preset（会话启动自动恢复）。

### 3. 引擎命令行（也可独立使用）

```bash
venv/bin/python engine/docflow_engine.py decode-file <b64文件> <out>      # base64 → 二进制
venv/bin/python engine/docflow_engine.py extract <file>                    # 提取全文 → JSON
venv/bin/python engine/docflow_engine.py create <fmt> <out> [spec.json]   # 生成 docx/pptx/pdf/md/txt
venv/bin/python engine/docflow_engine.py edit <fmt> <in> <out> [spec.json] # 修改文档
venv/bin/python engine/docflow_engine.py lit-search <term> [n]            # PubMed 检索
venv/bin/python engine/docflow_engine.py lit-crossref <query> [n]         # Crossref 检索
venv/bin/python engine/docflow_engine.py lit-verify <refs.json>           # 引文真实性核查
```

### 4. 模型工具（插件运行后自动注册）

| 工具 | 用途 |
| --- | --- |
| `docflow_create_document` | 按 markdown 生成精美文档 |
| `docflow_edit_document` | 修改已有文档 |
| `docflow_parse_document` | 提取文档纯文本 |
| `docflow_list_documents` | 列出全部文件与下载地址 |
| `docflow_export_document` | 格式转换 |
| `docflow_literature_search` | PubMed 真实检索（含摘要与 GB/T 7714 引文） |
| `docflow_literature_crossref` | Crossref 补充检索 |
| `docflow_literature_verify` | 引文真实性二次核查 |

## 主题配色

`blue / green / red / purple / gold / slate`——自动应用到封面、标题、表格表头、引用块与页脚。

## 技术说明

- **下载**：插件通过 `webServer` 注册 `/dsh-docflow/download/<id>` 前缀路由；地址为相对路径，浏览器按当前页面 origin 解析，任意访问方式（IP/域名/端口转发）均可下载。
- **文件传参**：上传 base64 与生成 spec 均先落盘再交给 Python 处理，规避沙箱 stdin 传递的不确定性；所有 fs/shell 写操作显式声明 `workspace-write` 沙箱策略。
- **文献来源**：PubMed/Medline（NCBI E-utilities：esearch → esummary → efetch）与 Crossref REST API，均为官方公开接口；检索带速率控制（NCBI 3 req/s）。
