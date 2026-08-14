# 文档工作流（docflow）

本目录是「文档工作流」动态 Cordis 插件的运行时文件，由插件自动使用，请勿手工改动。

| 路径 | 用途 |
| --- | --- |
| `venv/` | Python 虚拟环境（python-docx / python-pptx / pdfplumber / reportlab） |
| `engine/docflow_engine.py` | 文档引擎：创建/编辑/提取 docx、pptx、pdf、md、txt |
| `uploads/` | 用户上传的原始文件（文件名格式：`u_<id>__<原名>`） |
| `outputs/` | 插件生成的文档（文件名格式：`o_<id>__<文件名>`） |
| `tmp/` | 临时文件 |

引擎命令行（stdin 传 JSON spec）：

```
venv/bin/python engine/docflow_engine.py decode <out>
venv/bin/python engine/docflow_engine.py extract <file>
venv/bin/python engine/docflow_engine.py create <fmt> <out>   # stdin: spec JSON
venv/bin/python engine/docflow_engine.py edit   <fmt> <in> <out>  # stdin: spec JSON
venv/bin/python engine/docflow_engine.py meta   <file>
```

支持主题：`blue / green / red / purple / gold / slate`（6 套配色，自动应用到封面、标题、表格、引用块、页眉页脚）。
