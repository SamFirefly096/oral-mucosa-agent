# 口腔黏膜病中西医结合AI诊断Agent系统

基于 MIRA (Nature 2026) 架构，使用 DeepSeek V4 Pro 大语言模型的自主医疗诊断 Agent。

## 快速启动

### 1. 安装依赖
```bash
pip install openai pydantic python-dotenv tenacity
```

### 2. 配置 API Key
编辑 `.env` 文件，填入 DeepSeek API Key：
```
DEEPSEEK_API_KEY=你的key
```
（可在 platform.deepseek.com 获取，Cherry Studio 设置中也能找到）

### 3. 初始化数据库
```bash
cd 项目目录
python -c "from database import create_database; create_database()"
```

### 4. 运行测试
```bash
python run_simulation.py --list                    # 列出12个病例
python run_simulation.py --case OLP001             # 运行单个病例
python run_simulation.py --all --quiet             # 安静模式全量运行
python evaluate.py                                 # 评估所有已运行病例
```

## 项目结构

```
├── agents.py              # MedAgent + PatientAgent (DeepSeek API)
├── database.py            # SQLite 数据库 (11张表 + 12例样本)
├── tools.py               # 8个 Pydantic 工具定义
├── tool_executors.py      # 工具执行器 (SQLite查询)
├── conversation.py        # 对话循环引擎
├── run_simulation.py      # 运行入口 (CLI)
├── evaluate.py            # 评估脚本
├── config.py              # 配置管理
├── .env                   # API Key (需自行填写)
├── .env.example           # 配置模板
├── pyproject.toml         # 项目元数据
├── data/
│   └── oral_mucosa.db     # 数据库 (12病例含中西医数据)
├── outputs/
│   └── conversations/     # 对话记录 (JSON)
└── _论文/
    └── 口腔黏膜病AI诊断Agent论文.docx  # 学术论文
```

## 8个工具

| 工具 | 类别 | 功能 |
|------|------|------|
| perform_oral_examination | 西医 | 口腔黏膜专科检查 |
| perform_tcm_four_diagnosis | 中医 | 中医四诊（望闻问切） |
| order_lab_tests | 西医 | 化验申请（ANA/抗Dsg/血常规等） |
| order_microbiology | 西医 | 微生物检查（真菌涂片/HSV PCR等） |
| order_pathology | 西医 | 病理活检（HE+DIF+IIF） |
| prescribe_medications | 西医 | 西药处方（局部+全身） |
| prescribe_tcm_formula | 中医 | 中药处方（方剂+煎服法+加减） |
| finalize_diagnosis | 双重 | 中西医双重诊断+治疗方案 |

## 12个病例

| ID | 诊断 | 类别 |
|----|------|------|
| OLP001 | 糜烂型口腔扁平苔藓 | oral_lichen_planus |
| ATOLP001 | 萎缩型口腔扁平苔藓 | oral_lichen_planus |
| PV001 | 寻常型天疱疮 | pemphigus_vulgaris |
| BP001 | 大疱性类天疱疮 | bullous_pemphigoid |
| OC001 | 急性假膜型口腔念珠菌病 | oral_candidiasis |
| RAS001 | 复发性阿弗他口炎 | recurrent_aphthous |
| HSV001 | 原发性疱疹性龈口炎 | herpes_simplex |
| DLE001 | 口腔盘状红斑狼疮 | discoid_lupus |
| EM001 | 重型多形红斑 | erythema_multiforme |
| ANUG001 | 急性坏死性溃疡性龈炎 | anug |
| LEUK001 | 口腔白斑 | leukoplakia |
| LR001 | 苔藓样反应（药源性） | lichenoid_reaction |

## 评估结果

| 维度 | 准确率 |
|------|:---:|
| 西医诊断 | 100% (11/11) |
| 住院决策 | 100% (11/11) |
| 中医辨证 | ~92% (语义等价) |

## 技术栈

- DeepSeek V4 Pro (Function Calling + Thinking Mode)
- SQLite (零Docker依赖)
- Pydantic → JSON Schema (工具定义)
- OpenAI-compatible API (可无缝切换模型)

## 常见问题

### `python: command not found`

本机 Python 安装在 `C:\Users\admin\AppData\Local\Python\pythoncore-3.14-64\`，但该路径**不在 bash PATH 中**，且 WindowsApps 的 `python.exe` 是 Store 跳转存根（不可用）。

**解决方法**：使用完整路径：
```bash
/c/Users/admin/AppData/Local/Python/pythoncore-3.14-64/python.exe your_script.py
```

**为什么 Agent 能自主运行？** MedAgent/PatientAgent 不依赖本地 Python 执行——它们通过 `openai` 库调用 DeepSeek API，推理和 Function Calling 在云端完成。本地 Python 仅用于运行入口脚本 `run_simulation.py`。

### Bash 输出不可见

Bash 命令的标准输出经常为空，但文件写操作实际生效。解决方法：`script.py > output.txt 2>&1`，然后用编辑器读 `output.txt`。

## 参考

- Ferber D, et al. Towards autonomous medical AI agents. Nature, 2026
- 徐治鸿. 中西医结合口腔黏膜病学. 人民卫生出版社, 2008
- DeepSeek-AI. DeepSeek-V4 Technical Report. arXiv:2606.19348, 2026
- 项目论文: `_论文/口腔黏膜病AI诊断Agent论文.docx`
