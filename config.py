"""
口腔黏膜病 AI Agent 配置
基于 MIRA (Nature 2026) 架构，适配 DeepSeek API / 讯飞星辰 MaaS（OpenAI 兼容）
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

# ── LLM 提供方切换 ─────────────────────────────────
# MIRA_LLM_PROVIDER=deepseek（默认：Web/旧实验） | xfyun（讯飞星辰 MaaS：Spark-X2.5-4B 全套实验）
LLM_PROVIDER = os.getenv("MIRA_LLM_PROVIDER", "deepseek").strip().lower()

# 讯飞星辰 MaaS（OpenAI 兼容）：https://maas.xfyun.cn/modelSquare
XFYUN_API_KEY = os.getenv("XFYUN_API_KEY", "")
XFYUN_BASE_URL = os.getenv("XFYUN_BASE_URL", "https://maas-api.cn-huabei-1.xf-yun.com/v2")
XFYUN_MODEL = os.getenv("MIRA_XFYUN_MODEL", "spark-x2.5-4b")

if LLM_PROVIDER == "xfyun":
    if not XFYUN_API_KEY:
        raise RuntimeError("MIRA_LLM_PROVIDER=xfyun 但未设置 XFYUN_API_KEY（.env 或环境变量）")
    if "xf-yun.com" not in XFYUN_BASE_URL:
        raise RuntimeError(f"xfyun 模式禁止使用非讯飞端点: {XFYUN_BASE_URL}")
    LLM_API_KEY = XFYUN_API_KEY
    LLM_BASE_URL = XFYUN_BASE_URL
    LLM_THINKING_WIRE = "string"   # 讯飞 X2.5/MaaS 协议：thinking 为字符串枚举
    DEEPSEEK_API_KEY = ""          # 硬隔离：xfyun 模式下 DeepSeek 密钥不可用（任何取用即失败）
    _DEFAULT_MODEL = XFYUN_MODEL
else:
    LLM_API_KEY = DEEPSEEK_API_KEY
    LLM_BASE_URL = DEEPSEEK_BASE_URL
    LLM_THINKING_WIRE = "object"   # DeepSeek 协议：thinking 为 {type: ...}
    # 官方支持的 API 模型名只有两个：deepseek-flash（V4.1 Flash）与 deepseek-v4-pro。
    # 早期使用的 deepseek-v4-flash-vision-exp / deepseek-v4-flash 均为其别名（服务端响应 model 字段
    # 回显为 deepseek-flash），此处统一用规范名，避免再出现"实验名"当正式名调用。
    _DEFAULT_MODEL = "deepseek-flash"

# 模型选择（MIRA_MEDICAL_MODEL / MIRA_PATIENT_MODEL 可覆盖；xfyun 模式默认 spark-x2.5-4b）
MEDICAL_MODEL = os.getenv("MIRA_MEDICAL_MODEL") or _DEFAULT_MODEL
PATIENT_MODEL = os.getenv("MIRA_PATIENT_MODEL") or _DEFAULT_MODEL

# 推理参数
MEDICAL_TEMPERATURE = float(os.getenv("MIRA_MEDICAL_TEMPERATURE", "0.01"))
PATIENT_TEMPERATURE = float(os.getenv("MIRA_PATIENT_TEMPERATURE", "0.3"))
MAX_STEPS = int(os.getenv("MIRA_MAX_STEPS", "25"))

# 思考模式（DeepSeek 优先启用；spark-x2.5-4b 实测「始终思考」，参数不影响实际行为）
ENABLE_THINKING = os.getenv("MIRA_ENABLE_THINKING", "true").lower() == "true"
REASONING_EFFORT = os.getenv("MIRA_REASONING_EFFORT", "high")  # low | medium | high | max


def thinking_extra_param(enabled: bool) -> dict:
    """返回当前提供方约定的 thinking 参数（作为 OpenAI SDK 的 extra_body 一部分）。

    - DeepSeek：{"thinking": {"type": "enabled" | "disabled"}}
    - 讯飞星辰 MaaS（X2.5 协议）：{"thinking": "enabled" | "disabled"}（字符串枚举）
    """
    value = "enabled" if enabled else "disabled"
    if LLM_THINKING_WIRE == "string":
        return {"thinking": value}
    return {"thinking": {"type": value}}


# ── 数据库 ────────────────────────────────────────
DATABASE_PATH = PROJECT_ROOT / "data" / "oral_mucosa.db"

# ── 输出路径 ──────────────────────────────────────
EVALUATION_MODE = True  # 必须启用
OUTPUT_DIR = PROJECT_ROOT / "outputs"
SAVE_DIR = OUTPUT_DIR / "conversations"
RESULTS_DIR = OUTPUT_DIR / "results"
LOGS_DIR = OUTPUT_DIR / "logs"

for d in [OUTPUT_DIR, SAVE_DIR, RESULTS_DIR, LOGS_DIR]:
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


# ── 演示实例（DEMO_MODE）与子路径部署 ──────────────────────────
# OM_DEMO_MODE=1            演示限制：病例白名单 + 关闭临床照片 + 限额 + 免责横幅
# OM_DEMO_CASES=V001,V002   演示可用病例（留空 = 仅开放全部虚拟病例）
# OM_DEMO_MAX_SESSIONS=3    每账号最多建立的会话数
# OM_DEMO_MAX_TURNS=15      每会话最多对话轮次
# OM_DEMO_DAILY_CAP=200     全站每日新建会话上限（熔断）
# OM_BASE_PATH=/demo        反向代理子路径部署（页面内绝对路径自动加前缀）
DEMO_MODE = os.getenv("OM_DEMO_MODE", "") == "1"
DEMO_CASE_IDS = [x.strip() for x in os.getenv("OM_DEMO_CASES", "").split(",") if x.strip()]
DEMO_MAX_SESSIONS = int(os.getenv("OM_DEMO_MAX_SESSIONS", "3"))
DEMO_MAX_TURNS = int(os.getenv("OM_DEMO_MAX_TURNS", "15"))
DEMO_DAILY_CAP = int(os.getenv("OM_DEMO_DAILY_CAP", "200"))
BASE_PATH = os.getenv("OM_BASE_PATH", "").rstrip("/")

if DEMO_MODE:
    # 演示实例第二层保险：照片根目录强制指向空目录（接口层已返回 403）
    _empty = PROJECT_ROOT / "outputs" / "demo_photos_empty"
    _empty.mkdir(parents=True, exist_ok=True)
    PHOTO_DIR = os.getenv("OM_DEMO_PHOTO_DIR") or str(_empty)

# ── 会场闸门：默认把访客导入演示版 /demo/，管理员除外 ──────────
# OM_GATE_DEMO=1                 开启闸门（生产实例开启；演示实例无需开启）
# OM_GATE_EXCEPT_USERS=a,b       额外放行的用户名（默认仅 admin 角色）
GATE_DEMO = os.getenv("OM_GATE_DEMO", "") == "1"
GATE_EXCEPT_USERS = [x.strip() for x in os.getenv("OM_GATE_EXCEPT_USERS", "").split(",") if x.strip()]
