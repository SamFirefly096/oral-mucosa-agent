"""
口腔黏膜病AI诊断Agent — Web前端服务
模式1: 医学生训练 (RealisticPatientAgent)
模式2: 患者咨询 (ChiefMedAgent)
"""
import sys, os, json, random
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
PHOTO_MAP = {}
_ALL_HIDS = [row[0] for row in list_cases()]
for _f in _glob.glob(PHOTO_DIR + "/*"):
    _name = os.path.basename(_f)
    for _hid in _ALL_HIDS:
        if _name == _hid or _name.startswith(_hid):
            PHOTO_MAP[_hid] = [_name]
            break

# ── Session store ──
sessions = {}  # session_id -> {mode, agent, patient_agent, ctx, history}

@app.route("/")
def index():
    return send_from_directory("web", "index.html")

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
        cases.append({
            "id": row[0],
            "display": _get_display_code(row[0]),
            "age": row[1],
            "gender": "女" if row[2] == "F" else "男",
            "category": row[4],
        })
    return jsonify(cases)

@app.route("/api/chat/start", methods=["POST"])
def start_chat():
    """Initialize a new chat session."""
    data = request.json
    mode = data.get("mode", "training")  # "training" or "consult"
    case_id = data.get("case_id", "")
    session_id = str(random.randint(10000, 99999))

    if mode == "training":
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

        # Realistic patient for training
        pat = RealisticPatientAgent(model="deepseek-chat")
        pat.init_with_patient(ctx)

        sessions[session_id] = {
            "mode": mode,
            "case_id": case_id,
            "patient_agent": pat,
            "doctor_agent": None,
            "ctx": ctx,
            "history": [],
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

        return jsonify({
            "session_id": session_id,
            "mode": mode,
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
        }
        greeting = "您好，我是口腔黏膜病主任医师。请问您有什么口腔问题需要咨询？请详细描述您的症状，包括部位、持续时间、有无疼痛等。"
        sessions[session_id]["history"].append({"role": "doctor", "content": greeting})
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

    if session["mode"] == "training":
        # Student sends message -> Realistic patient responds
        pat = session["patient_agent"]
        resp = pat.chat(message)
        session["history"].append({"role": "student", "content": message})
        session["history"].append({"role": "patient", "content": resp.messages})
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
    session_id = request.args.get("session_id", "")
    if session_id not in sessions:
        return jsonify({"error": "会话不存在"}), 400
    return jsonify(sessions[session_id]["history"])

@app.route("/api/chat/examination", methods=["POST"])
def request_examination():
    """学生申请检查——查询数据库返回结果。"""
    data = request.json
    session_id = data.get("session_id", "")
    tool_name = data.get("tool", "")
    params = data.get("params", {})

    if session_id not in sessions or sessions[session_id]["mode"] != "training":
        return jsonify({"error": "仅训练模式支持检查申请"}), 400

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

    # Include photo URLs for oral exam
    photos = []
    if tool_name == "oral_exam":
        import requests as _r
        try:
            pr = _r.get(f"http://127.0.0.1:5000/api/photos/{hid}", timeout=1)
            photos = pr.json().get("photos", [])
        except:
            pass

    return jsonify({"result": result_text, "tool": tool_name,
                    "label": labels.get(tool_name, tool_name), "photos": photos})

@app.route("/api/chat/evaluate", methods=["POST"])
def evaluate():
    """Score student diagnosis against ground truth."""
    data = request.json
    session_id = data.get("session_id", "")
    if session_id not in sessions or sessions[session_id]["mode"] != "training":
        return jsonify({"error": "仅训练模式支持评估"}), 400

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

    # Scoring
    import re
    def score_diagnosis(student, truth):
        if not truth: return 0, "无标准答案"
        def ng(s): return set(re.sub(r'[（）(),，\-\s/a-zA-Z]+','',s.lower())[i:i+2] for i in range(len(s)-1))
        sg, tg = ng(student), ng(truth)
        if not tg: return 0, "标准答案为空"
        cov = len(sg & tg) / len(tg)
        if cov >= 0.9: return 90 + int(cov * 10), "优秀"
        if cov >= 0.5: return 60 + int(cov * 30), "良好"
        if cov >= 0.2: return 30 + int(cov * 50), "部分正确"
        return max(5, int(cov * 100)), "需改进"

    def score_treatment(student, truth):
        """Match treatment directions, not specific drug names."""
        if not truth: return 0, "无标准答案"
        categories = {
            "局部激素": [r'激素.{0,4}(漱口|含漱|软膏|外用|涂抹|涂布)', r'(曲安奈德|地塞米松|曲安缩松).{0,4}(软膏|漱口|外用)', r'triamcinolone', r'dexamethasone'],
            "局部止痛": [r'利多卡因', r'lidocaine', r'止痛', r'苯佐卡因', r'benzocaine'],
            "局部抗感染": [r'氯己定', r'chlorhexidine', r'西吡氯铵', r'抗菌.{0,3}(漱口|含漱)', r'碘伏'],
            "全身激素": [r'(口服|全身).{0,4}激素', r'泼尼松', r'prednisolone', r'甲泼尼龙', r'methylprednisolone'],
            "免疫抑制剂": [r'羟氯喹', r'hydroxychloroquine', r'沙利度胺', r'thalidomide', r'秋水仙碱', r'colchicine', r'氨苯砜', r'dapsone', r'霉酚酸酯', r'mycophenolate', r'环孢素', r'cyclosporine', r'甲氨蝶呤', r'methotrexate', r'雷公藤'],
            "抗真菌": [r'制霉素', r'nystatin', r'氟康唑', r'fluconazole', r'咪康唑', r'miconazole', r'抗真菌'],
            "抗病毒": [r'阿昔洛韦', r'acyclovir', r'伐昔洛韦', r'valacyclovir', r'抗病毒'],
            "抗细菌": [r'甲硝唑', r'metronidazole', r'多西环素', r'doxycycline', r'抗生素', r'阿莫西林'],
            "抗组胺": [r'氯雷他定', r'loratadine', r'抗组胺', r'抗过敏'],
            "支持治疗": [r'维生素', r'vitamin', r'补钙', r'护胃', r'奥美拉唑', r'omeprazole'],
            "中医外治": [r'康复新液', r'养阴生肌', r'冰硼散', r'青黛散', r'含漱', r'湿敷', r'中药.{0,3}(漱口|含漱|外敷)'],
            "生活指导": [r'戒烟', r'戒酒', r'防晒', r'sunscreen', r'饮食', r'口腔卫生', r'规律作息'],
            "物理治疗": [r'激光', r'laser', r'光动力', r'PDT', r'冷冻'],
        }
        found = 0; total = len(categories)
        s_lower = student.lower()
        for cat, patterns in categories.items():
            if any(re.search(p, s_lower) for p in patterns):
                found += 1
        rate = found / total
        if rate >= 0.5: return 85 + int(rate * 15), "优秀"
        if rate >= 0.3: return 55 + int(rate * 30), "良好"
        if rate >= 0.1: return 20 + int(rate * 50), "部分正确"
        return max(5, int(rate * 100)), "需改进"

    def translate_treatment(text):
        """Translate treatment JSON to readable Chinese."""
        if not text: return "无"
        # Try to parse JSON-like structure and extract Chinese meaning
        import json as _json
        parts = []
        # Match patterns like {"drug":"frequency route"}
        for segment in text.split(";"):
            segment = segment.strip()
            if not segment: continue
            # Extract drug name and route from patterns like: "triamcinolone 0.1% ointment bid topical"
            # Map common English terms to Chinese
            mapping = {
                "triamcinolone": "曲安奈德", "prednisolone": "泼尼松", "dexamethasone": "地塞米松",
                "chlorhexidine": "氯己定", "lidocaine": "利多卡因", "nystatin": "制霉素",
                "fluconazole": "氟康唑", "miconazole": "咪康唑", "acyclovir": "阿昔洛韦",
                "valacyclovir": "伐昔洛韦", "hydroxychloroquine": "羟氯喹", "colchicine": "秋水仙碱",
                "metronidazole": "甲硝唑", "doxycycline": "多西环素", "mycophenolate": "霉酚酸酯",
                "thalidomide": "沙利度胺", "loratadine": "氯雷他定", "omeprazole": "奥美拉唑",
                "ointment": "软膏", "mouthwash": "含漱液", "gel": "凝胶",
                "topical": "外用", "oral": "口服", "bid": "每日2次", "tid": "每日3次",
                "qd": "每日1次", "qid": "每日4次", "prn": "必要时",
            }
            translated = segment
            for en, zh in mapping.items():
                translated = re.sub(en, zh, translated, flags=re.IGNORECASE)
            translated = re.sub(r'[{}"\'\[\]]', '', translated)
            translated = re.sub(r'\d+%', '', translated)
            parts.append(translated.strip().strip(","))
        return "；".join(parts[:5]) if parts else text[:200]

    diag_score, diag_level = score_diagnosis(student_diag, true_diag_text)
    treat_score, treat_level = score_treatment(student_treatment, true_treatment_text) if true_treatment_text else (0, "无标准答案")

    # TCM: only score if true TCM data exists
    has_tcm = bool(true_tcm_text)
    tcm_score, tcm_level = (0, "无中医数据")
    if has_tcm:
        tcm_score, tcm_level = score_diagnosis(student_tcm, true_tcm_text)

    # Interaction efficiency bonus
    student_msgs = [h for h in session["history"] if h["role"] == "student"]
    rounds = len(student_msgs)
    if rounds <= 3: efficiency_bonus = 10
    elif rounds <= 6: efficiency_bonus = 6
    elif rounds <= 10: efficiency_bonus = 3
    else: efficiency_bonus = 0

    # Weighted total — TCM only counts when ground truth has TCM data
    if has_tcm:
        weights = {"diag": 0.45, "tcm": 0.25, "treatment": 0.20, "efficiency": 0.10}
    else:
        weights = {"diag": 0.60, "tcm": 0.0, "treatment": 0.28, "efficiency": 0.12}

    total = diag_score * weights["diag"]
    total += tcm_score * weights["tcm"]
    total += treat_score * weights["treatment"]
    total += efficiency_bonus * weights["efficiency"] * 10

    grade = "A" if total >= 85 else ("B" if total >= 70 else ("C" if total >= 55 else "D"))

    return jsonify({
        "scores": {
            "western_diagnosis": {"score": diag_score, "level": diag_level},
            "tcm_syndrome": {"score": tcm_score, "level": tcm_level} if has_tcm else None,
            "treatment_plan": {"score": treat_score, "level": treat_level},
            "efficiency_bonus": efficiency_bonus,
            "total": round(total, 1),
            "grade": grade,
        },
        "truth": {
            "diagnosis": true_diag_text,
            "tcm": true_tcm_text,
            "treatment": translate_treatment(true_treatment_text),
        },
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
