"""
口腔黏膜病AI诊断Agent — Web前端服务
模式1: 医学生训练 (RealisticPatientAgent)
模式2: 患者咨询 (ChiefMedAgent)
"""
import sys, os, json, random, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["MIRA_ENABLE_THINKING"] = "false"

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from database import get_hpi_text, query_table, list_cases
from agents_enhanced import ChiefMedAgent, RealisticPatientAgent, PatientContext
from config import ACCESS_PASSWORD, PHOTO_DIR

app = Flask(__name__, static_folder="web", static_url_path="")
CORS(app)

def get_pw():
    """Extract password from request header or query param."""
    return request.headers.get("X-Access-Password", "") or request.args.get("pw", "")

@app.before_request
def check_auth():
    """Require password for all routes."""
    if request.path.startswith("/api/photo/"): return
    if request.path.startswith("/favicon"): return
    if request.path in ("/", "/index.html") or request.path.endswith(".html"):
        pw = request.args.get("pw", "")
        if pw == ACCESS_PASSWORD: return
        return send_from_directory("web", "login.html")
    if request.path.startswith("/api/"):
        if get_pw() != ACCESS_PASSWORD:
            return jsonify({"error": "密码错误"}), 401

# Photo mapping: hadm_id -> list of photo subdirectory names
import glob as _glob
PHOTO_MAP = {
    "PIM001": ["何小龙（种植体周围黏膜炎）"],
    "MRS001": ["林强（梅罗综合征）"],
}
_ALL_HIDS = [row[0] for row in list_cases()]
for _f in _glob.glob(PHOTO_DIR + "/*"):
    _name = os.path.basename(_f)
    for _hid in _ALL_HIDS:
        if _name == _hid or _name.startswith(_hid):
            PHOTO_MAP[_hid] = [_name]
            break

# ── Session store ──
sessions = {}  # session_id -> {mode, agent, patient_agent, ctx, history}

# ── Session persistence ──
# 会话落盘到 outputs/web_sessions/（outputs 已被 .gitignore 排除），
# 服务重启/自动部署后自动恢复，历史会话不再丢失。
SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "web_sessions")
MAX_SESSIONS = 100
_session_lock = threading.Lock()

def _agent_to_dict(agent):
    """序列化 Agent 的可重建状态（不含 API client）。"""
    if agent is None:
        return None
    d = {"type": type(agent).__name__, "model": agent.model,
         "message_history": getattr(agent, "message_history", [])}
    if hasattr(agent, "temperature"): d["temperature"] = agent.temperature
    if hasattr(agent, "max_tokens"): d["max_tokens"] = agent.max_tokens
    if hasattr(agent, "thinking"): d["thinking"] = agent.thinking
    for k in ("tool_call_count", "current_step", "completed", "diagnosis_submitted", "total_time"):
        if hasattr(agent, k): d[k] = getattr(agent, k)
    return d

def _agent_from_dict(d, ctx=None):
    """从序列化状态重建 Agent（不调用 LLM）。"""
    if not d:
        return None
    t = d.get("type")
    model = d.get("model", "deepseek-chat")
    agent = None
    if t == "RealisticPatientAgent":
        agent = RealisticPatientAgent(model=model)
        if ctx:
            agent.init_with_patient(PatientContext(
                hadm_id=ctx.get("hadm_id", ""),
                patient_info_text=ctx.get("patient_info_text", ""),
                age=ctx.get("age"), gender=ctx.get("gender")))
    elif t == "ChiefMedAgent":
        agent = ChiefMedAgent(model=model, thinking=bool(d.get("thinking", False)))
    if agent is None:
        return None
    agent.message_history = d.get("message_history") or agent.message_history
    if "temperature" in d: agent.temperature = d["temperature"]
    if "max_tokens" in d: agent.max_tokens = d["max_tokens"]
    for k in ("tool_call_count", "current_step", "completed", "diagnosis_submitted", "total_time"):
        if k in d: setattr(agent, k, d[k])
    return agent

def _session_file(session_id):
    return os.path.join(SESSION_DIR, f"{session_id}.json")

def _save_session(session_id):
    """将单个会话原子写入磁盘，并裁剪超过上限的旧会话。"""
    s = sessions.get(session_id)
    if not s:
        return
    try:
        os.makedirs(SESSION_DIR, exist_ok=True)
        payload = {
            "session_id": session_id,
            "mode": s.get("mode"),
            "case_id": s.get("case_id"),
            "title": s.get("title", "医学生"),
            "started_at": s.get("started_at", ""),
            "last_active": s.get("last_active", 0.0),
            "patient_info": s.get("patient_info"),
            "ctx": s.get("_ctx"),
            "history": s.get("history", []),
            "patient_agent": _agent_to_dict(s.get("patient_agent")),
            "doctor_agent": _agent_to_dict(s.get("doctor_agent")),
        }
        tmp = _session_file(session_id) + ".tmp"
        with _session_lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, _session_file(session_id))
        _prune_sessions()
    except Exception as e:
        print(f"[sessions] save {session_id} failed: {e}", flush=True)

def _load_sessions():
    """启动时从磁盘恢复全部会话（Agent 用保存的 message_history 重建）。"""
    try:
        os.makedirs(SESSION_DIR, exist_ok=True)
    except Exception:
        return
    files = sorted(_glob.glob(os.path.join(SESSION_DIR, "*.json")),
                   key=os.path.getmtime, reverse=True)
    restored = 0
    for fp in files:
        sid = os.path.basename(fp)[:-5]
        try:
            with open(fp, "r", encoding="utf-8") as f:
                d = json.load(f)
            mode = d.get("mode")
            if mode not in ("training", "test", "consult"):
                continue
            ctx = d.get("ctx")
            sessions[sid] = {
                "mode": mode,
                "case_id": d.get("case_id"),
                "patient_agent": _agent_from_dict(d.get("patient_agent"), ctx),
                "doctor_agent": _agent_from_dict(d.get("doctor_agent")),
                "ctx": None,
                "history": d.get("history", []),
                "title": d.get("title", "医学生"),
                "started_at": d.get("started_at", ""),
                "last_active": d.get("last_active", 0.0),
                "patient_info": d.get("patient_info"),
                "_ctx": ctx,
                "_restored": True,
            }
            restored += 1
        except Exception as e:
            print(f"[sessions] skip restore {sid}: {e}", flush=True)
    if restored:
        print(f"[sessions] restored {restored} session(s) from disk", flush=True)

def _prune_sessions():
    """保留最新 MAX_SESSIONS 个会话（磁盘+内存同步裁剪）。"""
    try:
        files = sorted(_glob.glob(os.path.join(SESSION_DIR, "*.json")),
                       key=os.path.getmtime, reverse=True)
        with _session_lock:
            for fp in files[MAX_SESSIONS:]:
                sid = os.path.basename(fp)[:-5]
                try:
                    os.remove(fp)
                except OSError:
                    pass
                sessions.pop(sid, None)
    except Exception:
        pass

# 启动时恢复历史会话
_load_sessions()

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

@app.route("/app.js")
def serve_app_js():
    return send_from_directory("web", "app.js")

@app.route("/login.html")
def serve_login():
    return send_from_directory("web", "login.html")

# Anonymized display codes for training mode
_CASE_CODES = {}

def _get_display_code(hadm_id):
    if hadm_id not in _CASE_CODES:
        _CASE_CODES[hadm_id] = f"Case-{len(_CASE_CODES)+1:02d}"
    return _CASE_CODES[hadm_id]

@app.route("/api/cases")
def get_cases():
    """Return list of available patient cases for training mode (diagnosis hidden)."""
    cases = []
    for row in list_cases():
        hid = row[0]
        cases.append({
            "id": hid,
            "display": _get_display_code(hid),
            "age": row[1],
            "gender": "女" if row[2] == "F" else "男",
            "category": row[4],
            "has_photos": hid in PHOTO_MAP,
        })
    return jsonify(cases)

@app.route("/api/cases/debug")
def debug_cases():
    """Debug endpoint — returns full case info including diagnosis and treatment."""
    cases = []
    for row in list_cases():
        hid = row[0]
        diag = query_table("diagnoses", hid)
        tcm = query_table("tcm_diagnoses", hid)
        treat = query_table("treatments", hid)
        cc = query_table("chief_complaints", hid)
        cases.append({
            "id": hid,
            "display": _get_display_code(hid),
            "age": row[1],
            "gender": "女" if row[2] == "F" else "男",
            "category": row[4],
            "diagnosis": diag.get("primary_diagnosis", "") if diag else "",
            "icd11": diag.get("icd11_code", "") if diag else "",
            "tcm_syndrome": tcm.get("syndrome_differentiation", "") if tcm else "",
            "treatment": (treat.get("topical_treatment", "") or "") + "；" + (treat.get("systemic_treatment", "") or "") if treat else "",
            "chief_complaint": cc.get("chief_complaint", "")[:100] if cc else "",
            "has_photos": hid in PHOTO_MAP,
            "photo_count": len(PHOTO_MAP.get(hid, [])),
        })
    cases.sort(key=lambda c: c["id"])
    return jsonify(cases)

@app.route("/api/cases/<case_id>/full")
def case_full_detail(case_id):
    """Return all information for a single case."""
    from database import query_table, get_hpi_text
    tables = ["patients", "chief_complaints", "oral_examinations", "lab_results",
              "microbiology_results", "pathology_results", "diagnoses",
              "tcm_diagnoses", "treatments", "tcm_four_diagnosis"]
    result = {"case_id": case_id, "has_photos": case_id in PHOTO_MAP}
    for t in tables:
        row = query_table(t, case_id)
        if row:
            result[t] = dict(row)
    # Photos
    if case_id in PHOTO_MAP:
        photos = []
        for d in PHOTO_MAP[case_id]:
            dpath = os.path.join(PHOTO_DIR, d)
            if os.path.isdir(dpath):
                for ext in ["*.jpg","*.JPG","*.png","*.PNG","*.jpeg","*.JPEG"]:
                    for f in sorted(_glob.glob(os.path.join(dpath, "**", ext), recursive=True)):
                        photos.append("/api/photo/" + os.path.relpath(f, PHOTO_DIR).replace(os.sep, "/"))
        result["photos"] = photos
    return jsonify(result)

# ── Comments system ──
COMMENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "comments")
os.makedirs(COMMENTS_DIR, exist_ok=True)

def _load_comments(case_id):
    fpath = os.path.join(COMMENTS_DIR, f"{case_id}.json")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return __import__("json").load(f)
    return []

def _save_comments(case_id, comments):
    fpath = os.path.join(COMMENTS_DIR, f"{case_id}.json")
    with open(fpath, "w", encoding="utf-8") as f:
        __import__("json").dump(comments, f, ensure_ascii=False, indent=2)

@app.route("/api/cases/<case_id>/comments", methods=["GET", "POST"])
def case_comments(case_id):
    if request.method == "GET":
        return jsonify(_load_comments(case_id))
    # POST
    data = request.json
    author = (data.get("author") or "匿名用户").strip()[:20] or "匿名用户"
    content = (data.get("content") or "").strip()[:2000]
    if not content:
        return jsonify({"error": "内容不能为空"}), 400
    comments = _load_comments(case_id)
    comment = {
        "id": str(__import__("random").randint(10000, 99999)),
        "author": author,
        "content": content,
        "up": 0, "down": 0,
        "created_at": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    comments.append(comment)
    _save_comments(case_id, comments)
    return jsonify(comment)

@app.route("/api/comments/<comment_id>/vote", methods=["POST"])
def comment_vote(comment_id):
    data = request.json
    case_id = data.get("case_id", "")
    vote = data.get("vote", "up")  # "up" or "down"
    if not case_id:
        return jsonify({"error": "缺少case_id"}), 400
    comments = _load_comments(case_id)
    for c in comments:
        if c.get("id") == comment_id:
            c[vote] = c.get(vote, 0) + 1
            _save_comments(case_id, comments)
            return jsonify(c)
    return jsonify({"error": "评论不存在"}), 404

@app.route("/api/chat/start", methods=["POST"])
def start_chat():
    """Initialize a new chat session."""
    data = request.json
    mode = data.get("mode", "training")  # "training", "test", or "consult"
    case_id = data.get("case_id", "")
    session_id = str(random.randint(10000, 99999))
    while session_id in sessions:
        session_id = str(random.randint(10000, 99999))

    if mode in ("training", "test"):
        # Medical student interviews a realistic patient
        if not case_id:
            return jsonify({"error": "请选择训练病例"}), 400

        patient = query_table("patients", case_id)
        cc = query_table("chief_complaints", case_id)
        if not patient or not cc:
            return jsonify({"error": f"病例 {case_id} 不存在"}), 404

        hpi = get_hpi_text(case_id)
        ctx = PatientContext(hadm_id=case_id, patient_info_text=hpi,
                            age=patient.get("age"), gender=patient.get("gender"))

        # Realistic patient for training/test
        pat = RealisticPatientAgent(model="deepseek-chat")
        pat.init_with_patient(ctx)

        # Test mode extras
        title = data.get("title", "医学生") if mode == "test" else "医学生"

        sessions[session_id] = {
            "mode": mode,
            "case_id": case_id,
            "patient_agent": pat,
            "doctor_agent": None,
            "ctx": ctx,
            "history": [],
            "title": title,
            "started_at": __import__("datetime").datetime.now().isoformat(),
            "last_active": time.time(),
            "_ctx": {
                "hadm_id": case_id,
                "patient_info_text": hpi,
                "age": patient.get("age"),
                "gender": patient.get("gender"),
            },
            "patient_info": {
                "age": patient.get("age"),
                "gender": "女" if patient.get("gender") == "F" else "男",
                "hint": cc.get("chief_complaint", "")[:80],
            },
        }

        # First patient message
        starter = "医生您好，我来看病。"
        resp = pat.chat(starter)
        sessions[session_id]["history"].append({"role": "patient", "content": resp.messages})
        _save_session(session_id)

        return jsonify({
            "session_id": session_id,
            "mode": mode,
            "title": title,
            "patient_info": sessions[session_id]["patient_info"],
            "first_message": resp.messages,
        })

    elif mode == "consult":
        # Patient consults Chief Physician
        chief = ChiefMedAgent(thinking=False, model="deepseek-chat")
        sessions[session_id] = {
            "mode": mode,
            "doctor_agent": chief,
            "patient_agent": None,
            "ctx": None,
            "history": [],
            "title": "患者咨询",
            "started_at": __import__("datetime").datetime.now().isoformat(),
            "last_active": time.time(),
            "_ctx": None,
            "patient_info": None,
        }
        greeting = "您好，我是口腔黏膜病主任医师。请问您有什么口腔问题需要咨询？请详细描述您的症状，包括部位、持续时间、有无疼痛等。"
        sessions[session_id]["history"].append({"role": "doctor", "content": greeting})
        _save_session(session_id)
        return jsonify({
            "session_id": session_id,
            "mode": mode,
            "first_message": greeting,
        })

    return jsonify({"error": "未知模式"}), 400

@app.route("/api/chat/send", methods=["POST"])
def send_message():
    """Send a message and get response."""
    data = request.json
    session_id = data.get("session_id", "")
    message = data.get("message", "")

    if session_id not in sessions:
        return jsonify({"error": "会话已过期，请重新开始"}), 400

    session = sessions[session_id]

    if session["mode"] in ("training", "test"):
        # Student sends message -> Realistic patient responds
        pat = session["patient_agent"]
        resp = pat.chat(message)
        session["history"].append({"role": "student", "content": message})
        session["history"].append({"role": "patient", "content": resp.messages})
        session["last_active"] = time.time()
        _save_session(session_id)
        return jsonify({
            "response": resp.messages,
            "role": "patient",
        })

    elif session["mode"] == "consult":
        # Patient sends message -> Chief doctor responds
        chief = session["doctor_agent"]
        resp = chief.chat(message)
        session["history"].append({"role": "patient", "content": message})

        # Handle tool calls in consult mode (no real DB, tools are disabled)
        max_tool_rounds = 5
        while resp.type == "function_call" and resp.tool_calls and max_tool_rounds > 0:
            max_tool_rounds -= 1
            for tc in resp.tool_calls:
                chief.message_history.append({
                    "role": "tool", "tool_call_id": tc["id"],
                    "content": "[咨询模式] 此工具在在线咨询中不可用。请基于患者的症状描述直接给出专业建议和就医指导。",
                })
            resp = chief.chat(user_input=None)

        session["history"].append({"role": "doctor", "content": resp.messages})
        session["last_active"] = time.time()
        _save_session(session_id)
        return jsonify({
            "response": resp.messages,
            "role": "doctor",
        })

    return jsonify({"error": "未知模式"}), 400

@app.route("/api/photos/<case_id>")
def list_photos(case_id):
    """List available photos for a case."""
    dirs = PHOTO_MAP.get(case_id, [])
    if not dirs:
        return jsonify({"photos": [], "note": "该病例暂无临床照片"})

    import glob, re
    photos = []
    for d in dirs:
        dpath = os.path.join(PHOTO_DIR, d)
        if not os.path.isdir(dpath):
            continue
        for ext in ["*.jpg", "*.JPG", "*.png", "*.PNG", "*.jpeg", "*.JPEG"]:
            for f in sorted(glob.glob(os.path.join(dpath, "**", ext), recursive=True)):
                rel = os.path.relpath(f, PHOTO_DIR)
                photos.append(f"/api/photo/{rel.replace(os.sep, '/')}")

    return jsonify({"photos": photos[:20], "count": len(photos)})

@app.route("/api/photo/<path:subpath>")
def serve_photo(subpath):
    """Serve a photo file from the case directory."""
    filepath = os.path.join(PHOTO_DIR, subpath)
    if not os.path.exists(filepath):
        return "Not found", 404
    return send_from_directory(PHOTO_DIR, subpath)

@app.route("/api/chat/history", methods=["GET"])
def get_history():
    """返回会话元信息+完整记录。内存缺失时回退到磁盘（只读）。"""
    session_id = request.args.get("session_id", "")
    s = sessions.get(session_id)
    if s is None:
        try:
            fp = _session_file(session_id)
            if os.path.exists(fp):
                with open(fp, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return jsonify({
                    "session_id": session_id,
                    "mode": d.get("mode"),
                    "title": d.get("title", "医学生"),
                    "case_id": d.get("case_id"),
                    "patient_info": d.get("patient_info"),
                    "started_at": d.get("started_at", ""),
                    "history": d.get("history", []),
                    "resumable": False,
                })
        except Exception:
            pass
        return jsonify({"error": "会话不存在"}), 400
    return jsonify({
        "session_id": session_id,
        "mode": s["mode"],
        "title": s.get("title", "医学生"),
        "case_id": s.get("case_id"),
        "patient_info": s.get("patient_info"),
        "started_at": s.get("started_at", ""),
        "history": s["history"],
        "resumable": True,
    })

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    """历史会话列表（按最近活跃倒序）。"""
    out = []
    for sid, s in sessions.items():
        hid = s.get("case_id")
        mode = s.get("mode", "?")
        out.append({
            "session_id": sid,
            "mode": mode,
            "mode_label": {"training": "训练", "test": "测试", "consult": "咨询"}.get(mode, mode),
            "title": s.get("title", "医学生"),
            "case_id": hid,
            "case_display": _get_display_code(hid) if hid else "",
            "started_at": s.get("started_at", ""),
            "last_active": s.get("last_active", 0.0),
            "msg_count": len(s.get("history", [])),
            "resumable": True,
        })
    out.sort(key=lambda x: x["last_active"], reverse=True)
    return jsonify(out)

@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    """删除一个历史会话（内存+磁盘）。"""
    sessions.pop(session_id, None)
    try:
        os.remove(_session_file(session_id))
    except OSError:
        pass
    return jsonify({"ok": True})

@app.route("/api/chat/examination", methods=["POST"])
def request_examination():
    """学生申请检查——查询数据库返回结果。"""
    data = request.json
    session_id = data.get("session_id", "")
    tool_name = data.get("tool", "")
    params = data.get("params", {})

    if session_id not in sessions or sessions[session_id]["mode"] not in ("training", "test"):
        return jsonify({"error": "会话已过期，请重新选择病例开始问诊"}), 400

    hid = sessions[session_id]["case_id"]

    # Map tool names to DB tables and formatters
    from tool_executors import (
        execute_oral_examination, execute_lab_tests,
        execute_microbiology, execute_pathology, execute_tcm_four_diagnosis
    )

    tool_map = {
        "oral_exam": lambda: execute_oral_examination(hid),
        "lab_tests": lambda: execute_lab_tests(hid, params.get("tests")),
        "microbiology": lambda: execute_microbiology(hid),
        "pathology": lambda: execute_pathology(hid),
        "tcm_diagnosis": lambda: execute_tcm_four_diagnosis(hid),
    }

    labels = {
        "oral_exam": "口腔专科检查",
        "lab_tests": "化验检查",
        "microbiology": "微生物检查",
        "pathology": "病理检查",
        "tcm_diagnosis": "中医四诊",
    }

    executor = tool_map.get(tool_name)
    if not executor:
        return jsonify({"error": f"未知检查类型: {tool_name}"}), 400

    result_text = executor()
    sessions[session_id]["history"].append({"role": "system", "content": f"[{labels.get(tool_name, tool_name)}]\n{result_text}"})
    sessions[session_id]["last_active"] = time.time()
    _save_session(session_id)

    # Include photo URLs for oral exam (direct lookup, no HTTP call)
    photos = []
    if tool_name == "oral_exam" and hid in PHOTO_MAP:
        for d in PHOTO_MAP[hid]:
            dpath = os.path.join(PHOTO_DIR, d)
            if os.path.isdir(dpath):
                for ext in ["*.jpg", "*.JPG", "*.png", "*.PNG", "*.jpeg", "*.JPEG"]:
                    for f in sorted(_glob.glob(os.path.join(dpath, "**", ext), recursive=True)):
                        rel = os.path.relpath(f, PHOTO_DIR)
                        photos.append(f"/api/photo/{rel.replace(os.sep, '/')}")

    return jsonify({"result": result_text, "tool": tool_name,
                    "label": labels.get(tool_name, tool_name), "photos": photos})

@app.route("/api/chat/evaluate", methods=["POST"])
def evaluate():
    """Score student diagnosis against ground truth."""
    data = request.json
    session_id = data.get("session_id", "")
    if session_id not in sessions or sessions[session_id]["mode"] not in ("training", "test"):
        return jsonify({"error": "仅训练/测试模式支持评估"}), 400

    session = sessions[session_id]
    hid = session["case_id"]

    student_diag = data.get("diagnosis", "").strip()
    student_tcm = data.get("tcm_syndrome", "").strip()
    student_treatment = data.get("treatment", "").strip()

    # Ground truth
    true_diag = query_table("diagnoses", hid)
    true_tcm = query_table("tcm_diagnoses", hid)
    true_treatment = query_table("treatments", hid)

    true_diag_text = true_diag.get("primary_diagnosis", "") if true_diag else ""
    true_tcm_text = true_tcm.get("syndrome_differentiation", "") if true_tcm else ""
    true_treatment_text = ""
    if true_treatment:
        parts = []
        if true_treatment.get("topical_treatment"): parts.append(true_treatment["topical_treatment"])
        if true_treatment.get("systemic_treatment"): parts.append(true_treatment["systemic_treatment"])
        true_treatment_text = "; ".join(parts)

    # ══════════════════════════════════════════
    # 新评分逻辑：关键词模糊匹配
    # ══════════════════════════════════════════
    import re

    def extract_keywords(text):
        """从文本中提取有意义的2-5字关键词"""
        s = re.sub(r'[（）()\s,，、\-/a-zA-Z\d]+', '', text)
        keywords = set()
        for n in [2, 3, 4, 5]:
            for i in range(len(s) - n + 1):
                seg = s[i:i+n]
                # Filter noisy segments
                if not re.match(r'^[的了在是和就不也还都只很到得着过被把]', seg):
                    keywords.add(seg)
        return keywords

    def score_diagnosis(student, truth):
        """关键词模糊匹配评分。标准答案拆分为关键词，学生答案覆盖足够多即满分。"""
        if not truth: return 0, "无标准答案"
        if not student: return 0, "未填写"
        # 手动定义每种疾病的核心关键词（确保关键概念被覆盖）
        core_keywords = {
            "扁平苔藓": ["扁平苔藓", "OLP"],
            "天疱疮": ["天疱疮"],
            "念珠菌": ["念珠菌", "真菌", "假膜"],
            "阿弗他": ["阿弗他", "溃疡", "阿弗它"],
            "疱疹": ["疱疹", "病毒"],
            "红斑狼疮": ["红斑狼疮", "红斑"],
            "白斑": ["白斑"],
            "多形红斑": ["多形红斑", "多形"],
            "坏死性溃疡性龈炎": ["坏死", "龈炎", "ANUG"],
            "苔藓样": ["苔藓样", "苔藓"],
            "类天疱疮": ["类天疱疮", "天疱"],
            "放射性": ["放射性", "放疗", "放射"],
            "带状疱疹": ["带状疱疹", "带状"],
            "过敏性": ["过敏", "过敏性"],
            "白色海绵状": ["海绵状", "海绵"],
            "慢性唇炎": ["唇炎", "慢性"],
            "种植体": ["种植体", "种植"],
            "梅罗": ["梅罗", "MRS"],
        }
        s = student.lower()
        t = truth.lower()

        # 找出该标准答案可能对应的疾病
        best_match_count = 0
        best_keywords = set()
        for disease, kws in core_keywords.items():
            if any(kw.lower() in t for kw in kws):
                matched = sum(1 for kw in kws if kw.lower() in s)
                if matched > best_match_count:
                    best_match_count = matched
                    best_keywords = kws

        # 如果没有匹配到预定义疾病，使用通用关键词匹配
        if not best_keywords:
            t_clean = re.sub(r'[（）()，,\s\-/a-zA-Z\d]+', '', truth)
            best_keywords = set()
            for i in range(len(t_clean) - 1):
                seg = t_clean[i:i+2]
                if seg not in ("口腔", "黏膜", "型", "性", "病"):
                    best_keywords.add(seg)

        # 评分
        if not best_keywords: return 50, "良好"
        matched = sum(1 for kw in best_keywords if kw.lower() in s)
        ratio = matched / len(best_keywords)

        if ratio >= 0.8: return 95 + int(ratio * 5), "优秀"
        if ratio >= 0.5: return 70 + int(ratio * 30), "良好"
        if ratio >= 0.2: return 30 + int(ratio * 50), "部分正确"
        return max(10, int(ratio * 100)), "需改进"

    def score_treatment(student, truth):
        """治疗方向匹配——只判断大方向，不要求具体药名。"""
        if not truth: return 0, "无标准答案"
        if not student: return 0, "未填写"

        directions = {
            "局部治疗": [r'局部', r'外用', r'涂', r'抹', r'含漱', r'漱口', r'软膏', r'凝胶', r'膜', r'贴'],
            "全身治疗": [r'全身', r'口服', r'内服', r'系统', r'全身用药'],
            "抗炎": [r'抗炎', r'消炎', r'激素', r'皮质', r'曲安奈德', r'地塞米松', r'泼尼松', r'甲泼尼龙', r'氯倍他索', r'他克莫司'],
            "免疫调节": [r'免疫', r'羟氯喹', r'沙利度胺', r'秋水仙碱', r'雷公藤', r'环孢素', r'甲氨蝶呤', r'氨苯砜', r'霉酚酸酯', r'调节免疫'],
            "抗感染": [r'抗感染', r'抗菌', r'抗真菌', r'抗病毒', r'制霉素', r'氟康唑', r'阿昔洛韦', r'甲硝唑', r'多西环素', r'氯己定'],
            "止痛对症": [r'止痛', r'镇痛', r'对症', r'利多卡因', r'苄达明'],
            "口腔卫生": [r'卫生', r'洁牙', r'戒烟', r'戒酒', r'饮食', r'防晒', r'口腔护理'],
            "随访复查": [r'随访', r'复查', r'定期', r'监测', r'复诊', r'观察'],
        }

        s_lower = student.lower()
        found = 0
        details = []
        for label, patterns in directions.items():
            if any(re.search(p, s_lower) for p in patterns):
                found += 1
                details.append(label)

        # 方向数评分（答对5个方向即可满分）
        target = min(8, len(directions))
        ratio = found / target
        if ratio >= 0.75: score = 90 + int(ratio * 10)
        elif ratio >= 0.4: score = 55 + int(ratio * 40)
        elif ratio >= 0.15: score = 20 + int(ratio * 60)
        else: score = max(5, int(ratio * 100))

        level = "优秀" if score >= 85 else ("良好" if score >= 60 else ("部分正确" if score >= 25 else "需改进"))
        return score, level

    def score_tcm(student, truth):
        """中医辨证加分项（0-10分）。关键词匹配即可。"""
        if not truth or not student: return 0
        # 从标准答案中提取中医关键词元素
        elements = re.findall(r'[脏腑气血阴阳虚实寒热燥湿痰瘀风火毒]|阴虚|阳虚|气虚|血虚|气滞|血瘀|湿热|寒湿|痰湿|火热|风热', truth)
        if not elements:
            elements = list(set(re.findall(r'.{2}', re.sub(r'[证型方药]', '', truth))))

        s = student.lower()
        matched = sum(1 for e in elements if e in s)
        total = max(1, len(set(elements)))
        bonus = min(10, int(matched / total * 15))
        return bonus

    def format_treatment_display(text):
        """格式化治疗标准答案显示。现在DB已是中文，只需清理残留英文。"""
        if not text: return "无"
        # 清理残留英文给药方式
        cmds = {
            r'\btid topical\b': '每日3次外用', r'\bbid topical\b': '每日2次外用',
            r'\bqid topical\b': '每日4次外用', r'\bqd topical\b': '每日1次外用',
            r'\btid\b': '每日3次', r'\bbid\b': '每日2次', r'\bqd\b': '每日1次',
            r'\bqid\b': '每日4次', r'\bprn\b': '必要时',
            r'\bpo\b': '口服', r'\btopical\b': '外用',
            r'\bswish_and_swallow\b': '含漱后吞咽',
            r'\bapply to.*?(;|$)': '',
            r'_{1,}': '',
            r'\bfor\s+\d+\w?\b': '', r'\bday\b': '', r'\bweek\b': '周',
            r'\bif\b.*?(;|$)': '',
            r'\bq\d+h\b': '', r'\bmg\b': 'mg', r'\bkg\b': 'kg',
            r'\b(eye_exam|baseline|short_course|resistant|refractory|recurrence|frequent)\b': '',
            r',\s*,': '，',
        }
        result = text
        for pat, repl in cmds.items():
            result = re.sub(pat, repl, result, flags=re.IGNORECASE)
        # 清理换行和多余符号
        result = re.sub(r'[{}"\'\[\]]', '', result)
        result = re.sub(r'[,;，；]+', '；', result)
        result = re.sub(r'^\s*[;；]\s*', '', result)
        return result.strip()[:300] or text[:300]

    # ── 执行评分 ──
    diag_score, diag_level = score_diagnosis(student_diag, true_diag_text)
    treat_score, treat_level = score_treatment(student_treatment, true_treatment_text)

    # TCM 加分（0-10分额外加）
    has_tcm = bool(true_tcm_text)
    tcm_bonus = score_tcm(student_tcm, true_tcm_text) if has_tcm else 0

    # 问诊轮次
    student_msgs = [h for h in session["history"] if h["role"] == "student"]
    rounds = len(student_msgs)

    # 总分 = 西医诊断70% + 治疗方案30% + 中医加分(0-10)
    total = diag_score * 0.70 + treat_score * 0.30 + tcm_bonus
    total = min(100, round(total, 1))

    grade = "A" if total >= 85 else ("B" if total >= 70 else ("C" if total >= 55 else "D"))

    # Test mode: save results + title-based behavior
    is_test = session.get("mode") == "test"
    title = session.get("title", "医学生")
    hide_tutor = title in ("主治医师", "副主任医师", "主任医师")
    show_ref_only = title in ("副主任医师", "主任医师")  # Only show reference, no scores

    if is_test:
        test_record = {
            "session_id": session_id,
            "case_id": hid,
            "title": title,
            "started_at": session.get("started_at", ""),
            "rounds": rounds,
            "diagnosis": student_diag,
            "tcm": student_tcm,
            "treatment": student_treatment,
            "scores": {"diag": diag_score, "treatment": treat_score, "tcm_bonus": tcm_bonus, "total": total, "grade": grade},
            "history": session["history"],
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
        os.makedirs("outputs/tests", exist_ok=True)
        test_file = f"outputs/tests/{session_id}_{hid}_{title}_{__import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(test_file, "w", encoding="utf-8") as f:
            __import__("json").dump(test_record, f, ensure_ascii=False, indent=2)

    return jsonify({
        "scores": {
            "western_diagnosis": {"score": diag_score, "level": diag_level, "weight": "70%"},
            "treatment_plan": {"score": treat_score, "level": treat_level, "weight": "30%"},
            "tcm_bonus": {"score": tcm_bonus, "max": 10} if has_tcm else None,
            "total": total,
            "grade": grade,
        },
        "truth": {
            "diagnosis": true_diag_text,
            "icd11": query_table("diagnoses", hid).get("icd11_code", "") if query_table("diagnoses", hid) else "",
            "tcm": true_tcm_text,
            "treatment": format_treatment_display(true_treatment_text),
        },
        "test_mode": {
            "is_test": is_test,
            "title": title,
            "hide_tutor": hide_tutor,
            "show_ref_only": show_ref_only,
        } if is_test else None,
        "stats": {
            "rounds": rounds,
            "patient_msgs": len([h for h in session["history"] if h["role"] == "patient"]),
        }
    })


@app.route("/api/chat/tutor_review", methods=["POST"])
def tutor_review():
    """Clinical tutor agent reviews student's performance."""
    data = request.json
    session_id = data.get("session_id", "")
    if session_id not in sessions or sessions[session_id]["mode"] != "training":
        return jsonify({"error": "仅训练模式支持导师点评"}), 400

    session = sessions[session_id]
    hid = session["case_id"]
    history = session["history"]

    diag = data.get("diagnosis", "")
    tcm = data.get("tcm_syndrome", "")
    treatment = data.get("treatment", "")

    # Build conversation summary for the tutor
    conv_text = ""
    for h in history:
        role = h["role"]
        content = h["content"][:300]
        if role == "student":
            conv_text += f"学生问: {content}\n"
        elif role == "patient":
            conv_text += f"患者答: {content}\n"
        elif role == "system":
            conv_text += f"[检查结果] {content[:200]}\n"

    true_diag = query_table("diagnoses", hid)
    true_diag_text = true_diag.get("primary_diagnosis", "未知") if true_diag else "未知"
    true_tcm = query_table("tcm_diagnoses", hid)
    true_tcm_text = true_tcm.get("syndrome_differentiation", "无") if true_tcm else "无"

    prompt = f"""你是一位经验丰富的口腔黏膜病临床教学导师。一位医学生刚完成了一次模拟问诊训练，请你对学生的表现进行教学点评。

【病例真实诊断】{true_diag_text}
【病例中医辨证】{true_tcm_text}
【学生给出的西医诊断】{diag}
【学生给出的中医辨证】{tcm}
【学生给出的治疗方案】{treatment}

【问诊对话记录】
{conv_text[-3000:]}

请你从以下几个角度进行点评（用中文，200-400字，语气亲切但专业）：
1. 问诊质量：是否抓住了关键问题？遗漏了什么重要信息？
2. 诊断准确性：学生的诊断和真实诊断的吻合度如何？
3. 治疗方案：是否合理？有什么可以改进的地方？
4. 教学建议：学生下一步应该重点学习什么？

直接给出点评文本，不要标题或格式标记。"""

    try:
        from openai import OpenAI
        from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        resp = client.chat.completions.create(
            model="deepseek-chat", temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        review = resp.choices[0].message.content
    except Exception as e:
        review = f"导师点评暂时不可用（API错误: {str(e)[:80]}）。请根据标准答案自行对照学习。"

    return jsonify({"review": review})

if __name__ == "__main__":
    # Ensure web directory exists
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    os.makedirs(web_dir, exist_ok=True)

    print("\n" + "=" * 60)
    print("  口腔黏膜病AI诊断Agent — Web服务")
    print("  访问: http://localhost:5000")
    print("  模式1: 医学生训练 (真实患者模拟)")
    print("  模式2: 患者咨询 (主任医师服务)")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
