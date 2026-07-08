"""
口腔黏膜病 AI Agent 配置
基于 MIRA (Nature 2026) 架构，适配 DeepSeek API
"""
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

# ── DeepSeek API ──────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_BETA_URL = "https://api.deepseek.com/beta"  # strict function calling

# 模型选择
MEDICAL_MODEL = os.getenv("MIRA_MEDICAL_MODEL", "deepseek-v4-pro")
PATIENT_MODEL = os.getenv("MIRA_PATIENT_MODEL", "deepseek-v4-pro")

# 推理参数
MEDICAL_TEMPERATURE = float(os.getenv("MIRA_MEDICAL_TEMPERATURE", "0.01"))
PATIENT_TEMPERATURE = float(os.getenv("MIRA_PATIENT_TEMPERATURE", "0.3"))
MAX_STEPS = int(os.getenv("MIRA_MAX_STEPS", "25"))

# DeepSeek thinking mode (独有优势)
ENABLE_THINKING = os.getenv("MIRA_ENABLE_THINKING", "true").lower() == "true"
REASONING_EFFORT = os.getenv("MIRA_REASONING_EFFORT", "high")  # low | medium | high | max

# ── 数据库 ────────────────────────────────────────
DATABASE_PATH = PROJECT_ROOT / "data" / "oral_mucosa.db"

# ── 输出路径 ──────────────────────────────────────
EVALUATION_MODE = True  # 必须启用
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SAVE_DIR = OUTPUT_DIR / "conversations"
RESULTS_DIR = OUTPUT_DIR / "results"

for d in [OUTPUT_DIR, SAVE_DIR, RESULTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Web 服务配置 ─────────────────────────────────
ACCESS_PASSWORD = os.getenv("ACCESS_PASSWORD", "20260705")
PHOTO_DIR = os.getenv("PHOTO_DIR", str(PROJECT_ROOT.parent.parent / "工作目录" / "病例"))

# ── 诊断类别 ──────────────────────────────────────
DIAGNOSIS_CATEGORIES = [
    "oral_lichen_planus",       # 口腔扁平苔藓
    "pemphigus_vulgaris",       # 寻常型天疱疮
    "oral_candidiasis",         # 口腔念珠菌病
    "recurrent_aphthous",       # 复发性阿弗他口炎
    "herpes_simplex",           # 口腔单纯疱疹
    "erythema_multiforme",      # 多形红斑
    "leukoplakia",              # 口腔白斑
    "discoid_lupus",            # 盘状红斑狼疮
    "anug",                     # 急性坏死性溃疡性龈炎
    "lichenoid_reaction",       # 苔藓样反应（药源性）
    "bullous_pemphigoid",       # 大疱性类天疱疮
    # 以下为王雨田病例报告新增类别
    "radiation_induced_oral_mucositis",  # 放射性口腔黏膜炎
    "herpes_zoster",                     # 带状疱疹
    "allergic_oral_ulceration",          # 过敏性口炎
    "major_recurrent_aphthous",          # 重型复发性阿弗他溃疡
    "oral_lichenoid_lesion",             # 口腔苔藓样病变
    "white_sponge_nevus",                # 白色海绵状斑痣
    "chronic_cheilitis",                 # 慢性唇炎
    # 以下为临床真实病例新增类别
    "peri_implant_mucositis",            # 种植体周围黏膜炎
    "melkersson_rosenthal_syndrome",     # 梅罗综合征
]
