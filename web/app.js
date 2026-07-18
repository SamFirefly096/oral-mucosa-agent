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
let testTitle = "医学生", testHideTutor = false, testShowRefOnly = false;

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
    filterCases();  // Populate dropdown (also adds photo indicators)
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
  const tabs = document.querySelectorAll(".tab");
  const idx = mode === "training" ? 0 : (mode === "test" ? 1 : 2);
  tabs.forEach((t, i) => t.classList.toggle("active", i === idx));
  document.getElementById("caseSelector").style.display = (mode === "training" || mode === "test") ? "flex" : "none";
  const cls = mode === "consult" ? "consult" : "training";
  document.getElementById("chatArea").className = "chat-area " + cls;
  document.getElementById("endBtn").style.display = (mode === "training" || mode === "test") ? "inline-block" : "none";
  document.getElementById("scorePanel").classList.remove("show");
  testTitle = "医学生"; testHideTutor = false; testShowRefOnly = false;
  resetSession();
  // Test mode: show title selector immediately
  if (mode === "test") {
    document.getElementById("titleModal").classList.add("show");
  }
}

/* ── 通用开始按钮 ── */
function handleStart() {
  startTraining();
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

/* ── 测试模式 ── */
function selectTitle(title) {
  testTitle = title;
  testHideTutor = ["主治医师", "副主任医师", "主任医师"].includes(title);
  testShowRefOnly = ["副主任医师", "主任医师"].includes(title);
  document.getElementById("titleModal").classList.remove("show");
  startTest();
}

function startTest() {
  const cid = document.getElementById("caseSelect").value;
  if (!cid) { toast("请先选择训练病例", "warn"); return; }
  setLoading(true);
  setChatHTML('<div class="empty-state"><div class="spinner"></div><p style="margin-top:12px">正在准备测试患者...</p></div>');

  api("/api/chat/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "test", case_id: cid, title: testTitle }),
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
      document.getElementById("statusText").textContent = `测试中 (${testTitle})`;
      const cc = cases.find(x => x.id === cid);
      document.getElementById("caseLabel").textContent = `${cc ? cc.display : cid} | ${d.patient_info.age}岁${d.patient_info.gender}`;
      document.getElementById("scorePanel").classList.remove("show");
      clearDiagForm();
    })
    .catch(e => { toast(e.message, "error"); resetSession(); });
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

  const role = (currentMode === "training" || currentMode === "test") ? "student" : "patient";
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

  document.getElementById("scoreDiag").innerHTML = `<div class="score-val">${sc.western_diagnosis.score}</div><div class="score-lbl">西医诊断 (70%) · ${sc.western_diagnosis.level}</div>`;
  document.getElementById("scoreDiag").className = "score-item " + levelCls(sc.western_diagnosis.score);

  document.getElementById("scoreTreat").innerHTML = `<div class="score-val">${sc.treatment_plan.score}</div><div class="score-lbl">治疗方案 (30%) · ${sc.treatment_plan.level}</div>`;
  document.getElementById("scoreTreat").className = "score-item " + levelCls(sc.treatment_plan.score);

  // TCM bonus (0-10 extra)
  if (sc.tcm_bonus) {
    document.getElementById("scoreTCM").innerHTML = `<div class="score-val">+${sc.tcm_bonus.score}</div><div class="score-lbl">中医加分 (最多+10)</div>`;
    document.getElementById("scoreTCM").className = "score-item great";
  } else {
    document.getElementById("scoreTCM").innerHTML = '<div class="score-val">+0</div><div class="score-lbl">中医加分</div>';
    document.getElementById("scoreTCM").className = "score-item ok";
  }

  document.getElementById("scoreEff").innerHTML = `<div class="score-val">${d.stats.rounds}轮</div><div class="score-lbl">问诊轮次</div>`;
  document.getElementById("scoreEff").className = "score-item great";

  const gb = document.getElementById("gradeBadge");
  gb.textContent = sc.grade;
  gb.className = "grade-badge grade-" + sc.grade;
  document.getElementById("totalScore").textContent = `总分: ${sc.total}`;

  const icd11Code = d.truth.icd11 ? ` (ICD-11: ${escapeHTML(d.truth.icd11)})` : "";
  document.getElementById("truthContent").innerHTML =
    `<b>西医诊断:</b> ${escapeHTML(d.truth.diagnosis)}${icd11Code}<br>` +
    `<b>中医辨证:</b> ${escapeHTML(d.truth.tcm || "无")}<br>` +
    `<b>治疗方案:</b> ${escapeHTML(d.truth.treatment || "无")}`;

  document.getElementById("scorePanel").classList.add("show");
  document.getElementById("endBtn").style.display = "none";
  const statusLabel = currentMode === "test" ? `评估完成 (${testTitle})` : "评估完成";
  document.getElementById("statusText").textContent = statusLabel;

  // Test mode: hide tutor for 主治+, show reference only for 副主任+
  const tutorBtn = document.getElementById("tutorBtn");
  if (d.test_mode) {
    testHideTutor = d.test_mode.hide_tutor;
    testShowRefOnly = d.test_mode.show_ref_only;
  }
  if (testHideTutor) {
    tutorBtn.style.display = "none";
    document.getElementById("tutorReview").style.display = "none";
  } else {
    tutorBtn.style.display = "block";
  }
  // For 副主任+, hide the score details and just show reference
  if (testShowRefOnly) {
    document.getElementById("scoreDiag").style.display = "none";
    document.getElementById("scoreTreat").style.display = "none";
    document.getElementById("scoreTCM").style.display = "none";
    document.getElementById("scoreEff").style.display = "none";
    document.getElementById("gradeBadge").style.display = "none";
    document.getElementById("totalScore").style.display = "none";
  }
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
  const testMode = currentMode === "test";
  const showSelector = training || testMode;
  let title = showSelector ? (testMode ? "测试模式" : "医学生训练模式") : "患者咨询服务";
  let desc = testMode
    ? "选择病例开始测试。问诊参数将被记录保存，供后续分析。可选择职称级别。"
    : (training ? "选择病例开始模拟接诊。患者的诊断不会显示，请通过问诊自行判断。" : "描述您的口腔问题，获得主任医师级专业建议。");
  area.innerHTML = `<div class="empty-state"><div class="icon">\u{1F4AC}</div>
    <p><b>${title}</b></p>
    <p style="font-size:12px;color:#888;margin-top:4px">${desc}</p></div>`;
  area.className = "chat-area " + (training || testMode ? "training" : "consult");
  document.getElementById("msgInput").value = "";
  document.getElementById("sendBtn").disabled = showSelector;
  document.getElementById("msgInput").disabled = showSelector;
  document.getElementById("endBtn").style.display = "none";
  document.getElementById("examToolbar").style.display = "none";
  document.getElementById("scorePanel").classList.remove("show");
  document.getElementById("statusBar").style.display = "none";
  document.getElementById("tutorReview").style.display = "none";
  // Reset score visibility
  ["scoreDiag","scoreTreat","scoreTCM","scoreEff","gradeBadge","totalScore"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = "";
  });
  testTitle = "医学生"; testHideTutor = false; testShowRefOnly = false;
}

/* ── 随机病例 ── */
function randomCase() {
  const visible = getVisibleCases();
  if (!visible.length) { toast("没有可选的病例", "warn"); return; }
  const pick = visible[Math.floor(Math.random() * visible.length)];
  document.getElementById("caseSelect").value = pick.id;
  onCaseChange();
  toast(`随机选中: ${pick.display}`, "success");
}

/* ── 照片筛选 ── */
function getVisibleCases() {
  const filter = document.getElementById("photoFilter");
  if (filter && filter.checked) {
    return cases.filter(c => c.has_photos);
  }
  return cases;
}

function filterCases() {
  const filter = document.getElementById("photoFilter");
  const sel = document.getElementById("caseSelect");
  const currentVal = sel.value;
  sel.innerHTML = '<option value="">-- 请选择病例 --</option>';
  const visible = getVisibleCases();
  visible.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.display} | ${c.age}岁 ${c.gender}${c.has_photos ? " 📷" : ""}`;
    sel.appendChild(opt);
  });
  if (visible.find(c => c.id === currentVal)) {
    sel.value = currentVal;
  }
  if (filter && filter.checked) {
    toast(`已筛选: ${visible.length}例有临床照片`, "info");
  }
}

/* ── 调试面板 ── */
let debugData = null;
let debugVisible = false;

function toggleDebug() {
  debugVisible = !debugVisible;
  document.getElementById("debugPanel").style.display = debugVisible ? "block" : "none";
  if (debugVisible && !debugData) loadDebugData();
}

async function loadDebugData() {
  document.getElementById("debugContent").innerHTML =
    '<div class="spinner"></div><p style="text-align:center;margin-top:10px">加载中...</p>';
  try {
    const r = await api("/api/cases/debug");
    debugData = await r.json();
    renderDebugTable();
    toast(`已加载 ${debugData.length} 例病例`, "success");
  } catch (e) {
    document.getElementById("debugContent").innerHTML =
      `<p style="color:#f87171">加载失败: ${e.message}</p>`;
  }
}

function toggleDebugDetail(cid) {
  openCaseDetail(cid);
}

function renderDebugTable() {
  if (!debugData) return;
  const search = (document.getElementById("debugSearch")?.value || "").toLowerCase();
  let filtered = debugData;
  if (search) {
    filtered = debugData.filter(c =>
      c.id.toLowerCase().includes(search) ||
      c.diagnosis.toLowerCase().includes(search) ||
      c.tcm_syndrome.toLowerCase().includes(search)
    );
  }

  const photoCount = debugData.filter(c => c.has_photos).length;
  let html = `<div style="margin-bottom:8px;color:#888">
    共 ${debugData.length} 例 | 有照片: ${photoCount} 例 | 筛选: ${filtered.length} 例
  </div>`;
  html += '<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:10px">';
  html += '<thead><tr style="background:#2a2a3e;color:#fff">';
  html += '<th style="padding:6px 8px;text-align:left">编号</th>';
  html += '<th style="padding:6px 8px;text-align:left">ID</th>';
  html += '<th style="padding:6px 8px;text-align:left">西医诊断</th>';
  html += '<th style="padding:6px 8px;text-align:left">ICD-11</th>';
  html += '<th style="padding:6px 8px;text-align:left">中医辨证</th>';
  html += '<th style="padding:6px 8px;text-align:left">年龄/性别</th>';
  html += '<th style="padding:6px 8px;text-align:left">主诉</th>';
  html += '<th style="padding:6px 8px;text-align:center">照片</th>';
  html += '</tr></thead><tbody>';

  filtered.forEach((c, i) => {
    const bg = i % 2 === 0 ? "#1a1a2e" : "#222240";
    const photoTag = c.has_photos
      ? `<span style="color:#4ade80">&#x1F4F7; ${c.photo_count || "有"}</span>`
      : `<span style="color:#666">-</span>`;
    html += `<tr style="background:${bg};cursor:pointer" onclick="openCaseDetail('${c.id}')" title="点击查看完整信息">`;
    html += `<td style="padding:4px 8px">${c.display}</td>`;
    html += `<td style="padding:4px 8px;color:#60a5fa;text-decoration:underline">${c.id}</td>`;
    html += `<td style="padding:4px 8px">${escapeHTML(c.diagnosis) || "-"}</td>`;
    html += `<td style="padding:4px 8px;color:#888">${escapeHTML(c.icd11) || "-"}</td>`;
    html += `<td style="padding:4px 8px;color:#fbbf24">${escapeHTML(c.tcm_syndrome) || "-"}</td>`;
    html += `<td style="padding:4px 8px">${c.age}岁/${c.gender}</td>`;
    html += `<td style="padding:4px 8px;color:#888;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHTML(c.chief_complaint)}">${escapeHTML(c.chief_complaint) || "-"}</td>`;
    html += `<td style="padding:4px 8px;text-align:center">${photoTag}</td>`;
    html += `</tr>`;
  });
  html += '</tbody></table></div>';
  document.getElementById("debugContent").innerHTML = html;
}

/* ── 病例详情弹窗 + 评论 ── */
let currentDetailCid = null;

async function openCaseDetail(cid) {
  currentDetailCid = cid;
  const overlay = document.getElementById("detailOverlay");
  overlay.classList.add("show");
  document.getElementById("detailBody").innerHTML = '<div class="spinner"></div><p style="text-align:center;margin-top:10px">加载中...</p>';
  document.getElementById("detailComments").innerHTML = "";
  document.getElementById("commentInput").value = "";
  document.getElementById("commentAuthor").value = localStorage.getItem("comment_author") || "";

  try {
    const r = await api("/api/cases/" + cid + "/full");
    const d = await r.json();
    renderDetail(d);
    loadComments(cid);
  } catch (e) {
    document.getElementById("detailBody").innerHTML = `<p style="color:#f87171">加载失败: ${e.message}</p>`;
  }
}

function closeDetail() {
  document.getElementById("detailOverlay").classList.remove("show");
  currentDetailCid = null;
}

function renderDetail(d) {
  const labels = {
    chief_complaints: "主诉", diagnoses: "西医诊断", tcm_diagnoses: "中医辨证",
    treatments: "治疗方案", oral_examinations: "口腔检查", lab_results: "化验结果",
    microbiology_results: "微生物检查", pathology_results: "病理检查",
    tcm_four_diagnosis: "中医四诊", patients: "基本信息",
  };
  const fieldNames = {
    chief_complaint: "主诉", symptom_onset: "发病时间", symptom_duration_days: "病程(天)",
    symptom_evolution: "症状演变",
    primary_diagnosis: "主要诊断", differential_diagnoses: "鉴别诊断", icd11_code: "ICD-11",
    syndrome_differentiation: "辨证分型",
    topical_treatment: "局部治疗", systemic_treatment: "全身治疗", adjunctive_treatment: "辅助治疗",
    follow_up_plan: "随访计划", prognosis: "预后",
    lesion_location: "病损部位", lesion_morphology: "病损形态", lesion_color: "病损颜色",
    lesion_texture: "病损质地", nikolsky_sign: "Nikolsky征", extraoral_findings: "口腔外体征",
    oral_hygiene: "口腔卫生", additional_notes: "补充说明",
    age: "年龄", gender: "性别", systemic_diseases: "系统性疾病",
    medications: "当前用药", allergies: "过敏史",
    he_findings: "HE染色", dif_findings: "DIF", iif_findings: "IIF",
    pathological_diagnosis: "病理诊断", biopsy_site: "活检部位",
    wang_diagnosis: "望诊", tongue_body: "舌质", tongue_coating: "舌苔",
    pulse_description: "脉象", wen_diagnosis: "闻诊", wen_inquiry: "问诊",
  };

  let html = `<h3 style="margin-bottom:8px">&#x1F4CB; ${d.case_id}</h3>`;
  if (d.has_photos && d.photos) {
    html += `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px">`;
    d.photos.slice(0, 12).forEach(url => {
      html += `<img src="${url}" style="max-width:120px;max-height:100px;border-radius:4px;cursor:pointer" onclick="window.open('${url}','_blank')" loading="lazy">`;
    });
    html += `</div>`;
  }

  for (const [table, label] of Object.entries(labels)) {
    const row = d[table];
    if (!row) continue;
    html += `<div style="margin-bottom:10px"><h4 style="color:#60a5fa;margin:0 0 4px">${label}</h4><div style="font-size:12px;line-height:1.7">`;
    for (const [k, v] of Object.entries(row)) {
      if (k === "id" || k === "hadm_id" || v === null || v === "") continue;
      const name = fieldNames[k] || k;
      html += `<b>${name}:</b> ${escapeHTML(String(v))}<br>`;
    }
    html += `</div></div>`;
  }
  document.getElementById("detailBody").innerHTML = html;
}

async function loadComments(cid) {
  try {
    const r = await api("/api/cases/" + cid + "/comments");
    const comments = await r.json();
    renderComments(comments);
  } catch (e) {
    document.getElementById("detailComments").innerHTML = '<p style="color:#888">评论加载失败</p>';
  }
}

function renderComments(comments) {
  const container = document.getElementById("detailComments");
  if (!comments.length) {
    container.innerHTML = '<p style="color:#888">暂无建议，欢迎留言讨论</p>';
    return;
  }
  let html = "";
  comments.forEach(c => {
    html += `<div style="padding:8px 0;border-bottom:1px solid #e5e7eb">`;
    html += `<div style="display:flex;justify-content:space-between;align-items:center">`;
    html += `<span style="font-weight:600;font-size:12px">${escapeHTML(c.author)}</span>`;
    html += `<span style="font-size:10px;color:#888">${c.created_at}</span>`;
    html += `</div>`;
    html += `<div style="font-size:12px;line-height:1.6;margin:4px 0;white-space:pre-wrap">${escapeHTML(c.content)}</div>`;
    html += `<div style="display:flex;gap:12px;font-size:11px">`;
    html += `<span onclick="voteComment('${c.id}','up')" style="cursor:pointer;color:#16a34a">&#x1F44D; ${c.up||0}</span>`;
    html += `<span onclick="voteComment('${c.id}','down')" style="cursor:pointer;color:#dc2626">&#x1F44E; ${c.down||0}</span>`;
    html += `</div></div>`;
  });
  container.innerHTML = html;
}

async function submitComment() {
  const content = document.getElementById("commentInput").value.trim();
  if (!content) { toast("请输入建议内容", "warn"); return; }
  const author = document.getElementById("commentAuthor").value.trim() || "匿名用户";
  localStorage.setItem("comment_author", author);
  try {
    const r = await api("/api/cases/" + currentDetailCid + "/comments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author, content }),
    });
    const d = await r.json();
    if (d.error) { toast(d.error, "error"); return; }
    document.getElementById("commentInput").value = "";
    loadComments(currentDetailCid);
    toast("建议已保存", "success");
  } catch (e) {
    toast("提交失败: " + e.message, "error");
  }
}

async function voteComment(commentId, vote) {
  if (!currentDetailCid) return;
  try {
    await api("/api/comments/" + commentId + "/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: currentDetailCid, vote }),
    });
    loadComments(currentDetailCid);
  } catch (e) {
    toast("投票失败", "error");
  }
}

/* ── 键盘快捷键 ── */
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    closeModal();
    closeDetail();
    document.getElementById("diagModal")?.classList.remove("show");
  }
  if (e.ctrlKey && e.key === "Enter" && currentMode === "training" && sessionId) {
    endConsultation();
  }
});

// 页面加载完成后初始化
document.addEventListener("DOMContentLoaded", init);
