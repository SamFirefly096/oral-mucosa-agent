/**
 * 口腔黏膜病AI诊断Agent — 前端应用逻辑
 * 部署时修改 API_BASE 指向实际服务地址（如 "/api" 或 "https://domain.com/api"）
 */
const API_BASE = window.APP_CONFIG?.apiBase || "";
const PW = (() => {
  const p = new URLSearchParams(window.location.search).get("pw");
  if (p) { localStorage.setItem("agent_pw", p); window.history.replaceState({}, "", "/"); }
  return localStorage.getItem("agent_pw") || "";
})();

/* ── 工具函数 ── */
function api(path, opts = {}) {
  opts.headers = opts.headers || {};
  opts.headers["X-Access-Password"] = PW;
  return fetch(API_BASE + path, opts);
}

function escapeHTML(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function simpleMarkdown(text) {
  if (!text) return "";
  let html = escapeHTML(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/^#{1,3}\s+(.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^-\s+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

function toast(msg, type = "info") {
  const colors = { info: "#2563eb", error: "#dc2626", success: "#16a34a", warn: "#d97706" };
  const t = document.createElement("div");
  t.textContent = msg;
  Object.assign(t.style, {
    position: "fixed", top: "16px", left: "50%", transform: "translateX(-50%)",
    background: colors[type] || colors.info, color: "#fff", padding: "10px 24px",
    borderRadius: "20px", fontSize: "13px", fontWeight: "600", zIndex: "9999",
    boxShadow: "0 4px 16px rgba(0,0,0,.2)", animation: "fadeIn .2s", maxWidth: "90vw",
  });
  document.body.appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .3s"; }, 2000);
  setTimeout(() => t.remove(), 2500);
}

/* ── 全局状态 ── */
let sessionId = null, currentMode = "training", cases = [];

/* ── 初始化 ── */
function init() {
  loadCases();
  setupScrollButton();
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".dropdown")) {
      document.querySelectorAll(".dropdown-menu.show").forEach(m => m.classList.remove("show"));
    }
  });
}

async function loadCases() {
  try {
    const r = await api("/api/cases");
    const data = await r.json();
    cases = data;
    const sel = document.getElementById("caseSelect");
    data.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = `${c.display} | ${c.age}岁 ${c.gender}`;
      sel.appendChild(opt);
    });
  } catch (e) {
    toast("加载病例列表失败", "error");
  }
}

/* ── 滚动按钮 ── */
function setupScrollButton() {
  const chat = document.getElementById("chatArea");
  const btn = document.createElement("button");
  btn.id = "scrollBtn";
  btn.innerHTML = "&#x2B07;";
  btn.title = "滚动到底部";
  Object.assign(btn.style, {
    display: "none", position: "absolute", bottom: "70px", right: "24px",
    width: "36px", height: "36px", borderRadius: "50%", border: "1px solid #d0d5dd",
    background: "#fff", cursor: "pointer", fontSize: "16px", boxShadow: "0 2px 8px rgba(0,0,0,.12)",
    zIndex: "10", color: "#666",
  });
  btn.onclick = () => { chat.scrollTop = chat.scrollHeight; btn.style.display = "none"; };
  chat.parentNode.style.position = "relative";
  chat.parentNode.appendChild(btn);
  chat.addEventListener("scroll", () => {
    const atBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 60;
    btn.style.display = atBottom ? "none" : "block";
  });
}

function scrollToBottom() {
  const chat = document.getElementById("chatArea");
  chat.scrollTop = chat.scrollHeight;
}

/* ── 模式切换 ── */
function switchMode(mode) {
  currentMode = mode;
  document.querySelectorAll(".tab").forEach((t, i) => t.classList.toggle("active", i === (mode === "training" ? 0 : 1)));
  document.getElementById("caseSelector").style.display = mode === "training" ? "flex" : "none";
  document.getElementById("chatArea").className = "chat-area " + (mode === "training" ? "training" : "consult");
  document.getElementById("endBtn").style.display = mode === "training" ? "inline-block" : "none";
  document.getElementById("scorePanel").classList.remove("show");
  resetSession();
}

/* ── 训练模式 ── */
function onCaseChange() {
  const sel = document.getElementById("caseSelect");
  if (sel.value && cases.length) {
    const c = cases.find(x => x.id === sel.value);
    if (c) document.getElementById("caseLabel").textContent = `${c.display} | ${c.age}岁${c.gender}`;
  }
}

function startTraining() {
  const cid = document.getElementById("caseSelect").value;
  if (!cid) { toast("请先选择训练病例", "warn"); return; }
  setLoading(true);
  setChatHTML('<div class="empty-state"><div class="spinner"></div><p style="margin-top:12px">正在准备患者...</p></div>');

  api("/api/chat/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "training", case_id: cid }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "启动失败");
      sessionId = d.session_id;
      document.getElementById("chatArea").innerHTML = "";
      addMessage("patient", d.first_message);
      enableChat(true);
      document.getElementById("endBtn").style.display = "inline-block";
      document.getElementById("examToolbar").style.display = "flex";
      document.getElementById("statusBar").style.display = "flex";
      document.getElementById("statusText").textContent = "问诊中";
      const cc = cases.find(x => x.id === cid);
      document.getElementById("caseLabel").textContent = `${cc ? cc.display : cid} | ${d.patient_info.age}岁${d.patient_info.gender}`;
      document.getElementById("scorePanel").classList.remove("show");
      clearDiagForm();
    })
    .catch(e => {
      toast(e.message, "error");
      resetSession();
    });
}

/* ── 咨询模式 ── */
function startConsult() {
  setLoading(true);
  setChatHTML('<div class="empty-state"><div class="spinner"></div><p style="margin-top:12px">正在连接主任医师...</p></div>');

  api("/api/chat/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "consult" }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "启动失败");
      sessionId = d.session_id;
      document.getElementById("chatArea").innerHTML = "";
      addMessage("doctor", d.first_message);
      enableChat(true);
    })
    .catch(e => {
      toast(e.message, "error");
      resetSession();
    });
}

/* ── 发送消息 ── */
function sendMessage() {
  const input = document.getElementById("msgInput"), msg = input.value.trim();
  if (!msg) return;

  if (!sessionId) {
    if (currentMode === "consult") { startConsult(); return; }
    else { toast("请先选择病例并开始问诊", "warn"); return; }
  }

  const role = currentMode === "training" ? "student" : "patient";
  addMessage(role, msg);
  input.value = "";
  setLoading(true);

  api("/api/chat/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message: msg }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "发送失败");
      addMessage(d.role, d.response);
    })
    .catch(e => toast(e.message, "error"))
    .finally(() => setLoading(false));
}

/* ── 检查工具箱 ── */
function toggleDD(id) {
  const menu = document.getElementById(id).querySelector(".dropdown-menu");
  menu.classList.toggle("show");
}

function requestExam(tool) {
  if (!sessionId) { toast("请先开始训练", "warn"); return; }
  let params = {};
  if (tool === "lab_tests") {
    const cbs = document.querySelectorAll("#dd-lab input:checked");
    if (cbs.length === 0) { toast("请至少选择一项化验项目", "warn"); return; }
    params.tests = Array.from(cbs).map(c => c.value);
  } else if (tool === "microbiology") {
    const cbs = document.querySelectorAll("#dd-micro input:checked");
    if (cbs.length === 0) { toast("请至少选择一项微生物检查项目", "warn"); return; }
    params.tests = Array.from(cbs).map(c => c.value);
  }

  addSystemMsg("正在获取检查结果...", true);
  api("/api/chat/examination", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, tool, params }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "检查申请失败");
      // 移除"正在获取"的临时消息
      const chat = document.getElementById("chatArea");
      const pending = chat.querySelector(".msg-pending");
      if (pending) pending.remove();
      addSystemMsg(d.result);
      if (d.photos && d.photos.length > 0) addPhotos(d.photos);
    })
    .catch(e => toast(e.message, "error"));
}

function addPhotos(urls) {
  const area = document.getElementById("chatArea");
  const div = document.createElement("div");
  div.className = "message system";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.style.maxWidth = "90%";
  bubble.innerHTML = '<div class="role-label">\u{1F4F7} 临床照片</div>';

  const grid = document.createElement("div");
  grid.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin-top:6px";
  urls.forEach(url => {
    const img = document.createElement("img");
    img.src = url;
    img.style.cssText = "max-width:200px;max-height:160px;border-radius:6px;border:1px solid #ddd;cursor:pointer;object-fit:cover";
    img.onclick = () => openLightbox(url);
    img.loading = "lazy";
    grid.appendChild(img);
  });
  bubble.appendChild(grid);
  div.appendChild(bubble);
  area.appendChild(div);
  scrollToBottom();
}

function openLightbox(url) {
  const lb = document.createElement("div");
  Object.assign(lb.style, {
    position: "fixed", top: "0", left: "0", width: "100%", height: "100%",
    background: "rgba(0,0,0,.85)", zIndex: "200", display: "flex",
    alignItems: "center", justifyContent: "center", cursor: "pointer",
  });
  const img = document.createElement("img");
  img.src = url;
  img.style.cssText = "max-width:92vw;max-height:92vh;border-radius:8px;object-fit:contain";
  lb.appendChild(img);
  lb.onclick = () => lb.remove();
  document.body.appendChild(lb);
}

function addSystemMsg(text, isPending = false) {
  const area = document.getElementById("chatArea");
  const es = area.querySelector(".empty-state");
  if (es) es.remove();

  const div = document.createElement("div");
  div.className = "message system" + (isPending ? " msg-pending" : "");
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<div class="role-label">\u{1F52C} 检查结果</div>';

  if (isPending) {
    bubble.innerHTML += '<div class="spinner-sm"></div><span style="font-size:11px;color:#888;margin-left:6px">获取中...</span>';
  } else {
    const pre = document.createElement("pre");
    pre.style.cssText = "white-space:pre-wrap;font-family:inherit;margin:0;font-size:11px";
    pre.textContent = text;
    bubble.appendChild(pre);
  }
  div.appendChild(bubble);
  area.appendChild(div);
  scrollToBottom();
}

/* ── 结束问诊 → 弹出诊断表单 ── */
function endConsultation() {
  setLoading(true);
  document.getElementById("statusText").textContent = "问诊结束，请填写诊断";
  document.getElementById("diagModal").classList.add("show");
  setLoading(false);
}

function closeModal() {
  document.getElementById("diagModal").classList.remove("show");
}

function clearDiagForm() {
  document.getElementById("diagInput").value = "";
  document.getElementById("tcmInput").value = "";
  document.getElementById("treatInput").value = "";
}

function submitDiagnosis() {
  const diag = document.getElementById("diagInput").value.trim();
  const tcm = document.getElementById("tcmInput").value.trim();
  const treat = document.getElementById("treatInput").value.trim();
  if (!diag) { toast("请至少填写西医诊断", "warn"); return; }

  document.getElementById("diagModal").classList.remove("show");
  setLoading(true);

  api("/api/chat/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, diagnosis: diag, tcm_syndrome: tcm, treatment: treat }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "评分失败");
      renderScores(d);
    })
    .catch(e => toast(e.message, "error"))
    .finally(() => setLoading(false));
}

function renderScores(d) {
  const sc = d.scores;
  const levelCls = s => s >= 80 ? "great" : s >= 50 ? "good" : s >= 20 ? "ok" : "poor";

  document.getElementById("scoreDiag").innerHTML = `<div class="score-val">${sc.western_diagnosis.score}</div><div class="score-lbl">西医诊断 · ${sc.western_diagnosis.level}</div>`;
  document.getElementById("scoreDiag").className = "score-item " + levelCls(sc.western_diagnosis.score);

  if (sc.tcm_syndrome) {
    document.getElementById("scoreTCM").innerHTML = `<div class="score-val">${sc.tcm_syndrome.score}</div><div class="score-lbl">中医辨证 · ${sc.tcm_syndrome.level}</div>`;
    document.getElementById("scoreTCM").className = "score-item " + levelCls(sc.tcm_syndrome.score);
  } else {
    document.getElementById("scoreTCM").innerHTML = '<div class="score-val">N/A</div><div class="score-lbl">中医辨证 · 无数据</div>';
    document.getElementById("scoreTCM").className = "score-item ok";
  }

  document.getElementById("scoreTreat").innerHTML = `<div class="score-val">${sc.treatment_plan.score}</div><div class="score-lbl">治疗方案 · ${sc.treatment_plan.level}</div>`;
  document.getElementById("scoreTreat").className = "score-item " + levelCls(sc.treatment_plan.score);

  document.getElementById("scoreEff").innerHTML = `<div class="score-val">+${sc.efficiency_bonus}</div><div class="score-lbl">效率加分 (${d.stats.rounds}轮)</div>`;
  document.getElementById("scoreEff").className = "score-item great";

  const gb = document.getElementById("gradeBadge");
  gb.textContent = sc.grade;
  gb.className = "grade-badge grade-" + sc.grade;
  document.getElementById("totalScore").textContent = `总分: ${sc.total}`;

  document.getElementById("truthContent").innerHTML =
    `<b>西医诊断:</b> ${escapeHTML(d.truth.diagnosis)}<br>` +
    `<b>中医辨证:</b> ${escapeHTML(d.truth.tcm || "无")}<br>` +
    `<b>治疗方案:</b> ${escapeHTML(d.truth.treatment || "无")}`;

  document.getElementById("scorePanel").classList.add("show");
  document.getElementById("endBtn").style.display = "none";
  document.getElementById("statusText").textContent = "评估完成";
}

/* ── 导师点评 ── */
function getTutorReview() {
  const btn = document.getElementById("tutorBtn");
  btn.disabled = true;
  btn.textContent = "正在生成点评...";
  const diag = document.getElementById("diagInput").value;
  const tcm = document.getElementById("tcmInput").value;
  const treat = document.getElementById("treatInput").value;

  api("/api/chat/tutor_review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, diagnosis: diag, tcm_syndrome: tcm, treatment: treat }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "点评失败");
      const div = document.getElementById("tutorReview");
      div.innerHTML = simpleMarkdown(d.review);
      div.style.display = "block";
    })
    .catch(e => toast(e.message, "error"))
    .finally(() => {
      btn.disabled = false;
      btn.textContent = "\u{1F468}\u200D\u{1F3EB} 导师点评";
    });
}

/* ── 消息渲染 ── */
function addMessage(role, text) {
  const area = document.getElementById("chatArea");
  const es = area.querySelector(".empty-state");
  if (es) es.remove();

  const div = document.createElement("div");
  div.className = "message " + role;
  const bubble = document.createElement("div");
  bubble.className = "bubble";

  const labels = {
    student: "\u{1F468}\u200D\u2695\uFE0F 医学生",
    patient: "\u{1F9D1} 患者",
    doctor: "\u{1F468}\u200D\u2695\uFE0F 主任医师",
  };

  const label = document.createElement("div");
  label.className = "role-label";
  label.innerHTML = labels[role] || role;
  bubble.appendChild(label);

  // Markdown rendering for doctor messages
  if (role === "doctor") {
    const content = document.createElement("div");
    content.innerHTML = simpleMarkdown(text);
    bubble.appendChild(content);
    if (content.querySelector("li")) {
      const uls = content.querySelectorAll("li");
      uls.forEach(li => { if (!li.parentNode.matches("ul")) { const ul = document.createElement("ul"); li.parentNode.insertBefore(ul, li); ul.appendChild(li); } });
    }
  } else {
    bubble.appendChild(document.createTextNode(text));
  }

  div.appendChild(bubble);
  area.appendChild(div);
  scrollToBottom();
}

/* ── 加载状态 ── */
function setLoading(loading) {
  const sendBtn = document.getElementById("sendBtn");
  const msgInput = document.getElementById("msgInput");
  sendBtn.disabled = loading;
  msgInput.disabled = loading;
  if (!loading) msgInput.focus();
}

function enableChat(enabled) {
  document.getElementById("sendBtn").disabled = !enabled;
  document.getElementById("msgInput").disabled = !enabled;
  if (enabled) document.getElementById("msgInput").focus();
}

function setChatHTML(html) {
  document.getElementById("chatArea").innerHTML = html;
}

/* ── 重置 ── */
function resetSession() {
  sessionId = null;
  const area = document.getElementById("chatArea");
  const training = currentMode === "training";
  area.innerHTML = `<div class="empty-state"><div class="icon">\u{1F4AC}</div>
    <p><b>${training ? "医学生训练模式" : "患者咨询服务"}</b></p>
    <p style="font-size:12px;color:#888;margin-top:4px">${training ? "选择病例开始模拟接诊。患者的诊断不会显示，请通过问诊自行判断。" : "描述您的口腔问题，获得主任医师级专业建议。"}</p></div>`;
  area.className = "chat-area " + (training ? "training" : "consult");
  document.getElementById("msgInput").value = "";
  document.getElementById("sendBtn").disabled = training;
  document.getElementById("msgInput").disabled = training;
  document.getElementById("endBtn").style.display = "none";
  document.getElementById("examToolbar").style.display = "none";
  document.getElementById("scorePanel").classList.remove("show");
  document.getElementById("statusBar").style.display = "none";
  document.getElementById("tutorReview").style.display = "none";
}

/* ── 键盘快捷键 ── */
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    closeModal();
    document.getElementById("diagModal")?.classList.remove("show");
  }
  // Ctrl+Enter to end consultation in training mode
  if (e.ctrlKey && e.key === "Enter" && currentMode === "training" && sessionId) {
    endConsultation();
  }
});

// 页面加载完成后初始化
document.addEventListener("DOMContentLoaded", init);
