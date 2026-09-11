/**
 * 口腔黏膜病AI诊断Agent — 前端应用逻辑 (v0.2.0)
 * 多用户系统（令牌认证/会话隔离/admin管理） + 移动端优先UI + 语音输入/播报
 */
const API_BASE = window.APP_CONFIG?.apiBase || "";
let TOKEN = localStorage.getItem("om_token") || "";
let USER = null;

/* ── 语音能力检测 ── */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const HAS_TTS = typeof speechSynthesis !== "undefined";

/* ── 演示实例上的管理员提示 ──────────────────────────────────────
 * 演示环境为保护真实病例，服务端已关闭全部管理员功能（_require_admin 返回 None）。
 * 若管理员误入演示站，菜单里那两个入口点了只会 403，这里改为明确说明。 */
const OM_DEMO_SURFACE = location.pathname.indexOf("/demo") === 0;

const SR_SECURE = !!(SR && window.isSecureContext);

/* ── 全局状态 ── */
let sessionId = null, currentMode = "training", cases = [];
let testTitle = "医学生", testHideTutor = false, testShowRefOnly = false;
let userListCache = null;
const SETTINGS = { autoTTS: localStorage.getItem("om_autoTTS") === "1" };

/* ── 工具函数 ── */
function api(path, opts = {}) {
  opts.headers = opts.headers || {};
  opts.headers["X-Auth-Token"] = TOKEN;
  return fetch(API_BASE + path, opts);
}

async function apiJSON(path, opts = {}) {
  const r = await api(path, opts);
  let d = null;
  try { d = await r.json(); } catch (e) { d = {}; }
  if (r.status === 401) {
    logoutLocal();
    location.replace("/login.html");
    throw new Error("登录已过期");
  }
  if (!r.ok) throw new Error(d.error || "请求失败");
  return d;
}

function escapeHTML(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function simpleMarkdown(text) {
  if (!text) return "";
  let html = escapeHTML(text);
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/^(?!<h4>)(#{1,3})\s+(.+)$/gm, "<h4>$2</h4>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/^[-*]\s+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/^>\s?(.+)$/gm, "<blockquote>$1</blockquote>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

function toast(msg, type = "info") {
  const colors = { info: "#2563eb", error: "#dc2626", success: "#16a34a", warn: "#d97706" };
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  t.style.background = colors[type] || colors.info;
  document.body.appendChild(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; }, 2100);
  setTimeout(() => t.remove(), 2600);
}

/* ═══════════════ 键盘/视口修复 ═══════════════ */
function applyViewport() {
  const vv = window.visualViewport;
  const h = vv ? Math.round(vv.height) : window.innerHeight;
  const top = vv ? Math.round(vv.offsetTop) : 0;
  document.documentElement.style.setProperty("--vh", h + "px");
  document.documentElement.style.setProperty("--vv-top", top + "px");
}
function watchViewport() {
  applyViewport();
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", applyViewport);
    window.visualViewport.addEventListener("scroll", applyViewport);
  }
  window.addEventListener("resize", applyViewport);
  window.addEventListener("orientationchange", () => setTimeout(applyViewport, 150));
}

/* ═══════════════ 语音播报 (TTS) ═══════════════ */
let speakingBtn = null;
function pickZhVoice() {
  const vs = speechSynthesis.getVoices();
  return vs.find(v => /zh|中文|Chinese/i.test(v.lang + " " + v.name)) || null;
}
function cleanSpeakText(t) {
  return String(t || "").replace(/[*#`>_~]+/g, " ").replace(/http\S+/g, "")
    .replace(/\s+/g, " ").replace(/<[^>]+>/g, "").slice(0, 600);
}
function speakText(text, btn) {
  if (!HAS_TTS) { toast("当前浏览器不支持语音播报", "warn"); return; }
  const content = cleanSpeakText(text);
  if (!content) return;
  // 再点一次停止当前朗读
  if (speakingBtn === btn && speechSynthesis.speaking) {
    speechSynthesis.cancel();
    stopSpeak(btn);
    return;
  }
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(content);
  u.lang = "zh-CN";
  const v = pickZhVoice();
  if (v) u.voice = v;
  u.rate = 1.0;
  u.onstart = () => { if (btn) { btn.classList.add("speaking"); btn.textContent = "\u{1F507} 停止"; speakingBtn = btn; } };
  u.onend = () => stopSpeak(btn);
  u.onerror = () => stopSpeak(btn);
  speechSynthesis.speak(u);
}
function stopSpeak(btn) {
  if (btn) { btn.classList.remove("speaking"); btn.textContent = "\u{1F50A} 朗读"; }
  if (speakingBtn === btn) speakingBtn = null;
}

function toggleTTS() {
  SETTINGS.autoTTS = !SETTINGS.autoTTS;
  localStorage.setItem("om_autoTTS", SETTINGS.autoTTS ? "1" : "0");
  document.getElementById("ttsSwitch").classList.toggle("on", SETTINGS.autoTTS);
  toast(SETTINGS.autoTTS ? "已开启自动语音播报" : "已关闭自动语音播报", "success");
}

/* ═══════════════ 语音输入 (STT) ═══════════════ */
let recog = null, listening = false;
function initVoice() {
  const mic = document.getElementById("micBtn");
  if (!SR) {
    mic.classList.add("off");
    mic.title = "当前浏览器不支持语音输入（建议使用Chrome/Safari）";
    return;
  }
  if (!window.isSecureContext) {
    mic.classList.add("off");
    mic.title = "语音输入需要 HTTPS 环境，当前为 HTTP，语音播报不受影响";
    return;
  }
  try {
    recog = new SR();
    recog.lang = "zh-CN";
    recog.continuous = false;
    recog.interimResults = true;
    recog.onresult = (e) => {
      let final = "", interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) final += r[0].transcript;
        else interim += r[0].transcript;
      }
      const input = document.getElementById("msgInput");
      input.value = final || interim;
      scrollToBottom();
    };
    recog.onend = () => setListening(false);
    recog.onerror = (e) => {
      setListening(false);
      const errs = {
        "not-allowed": "麦克风权限被拒绝，请在浏览器设置中允许麦克风",
        "no-speech": "未检测到语音，请重试",
        "network": "语音识别服务网络异常，请重试",
        "aborted": "",
      };
      if (errs[e.error]) toast(errs[e.error], "warn");
    };
  } catch (e) {
    mic.classList.add("off");
  }
}
function toggleMic() {
  if (!recog) {
    toast(SR ? "语音输入需要 HTTPS 环境（建议为站点配置SSL证书）" : "当前浏览器不支持语音输入", "warn");
    return;
  }
  if (listening) { recog.stop(); setListening(false); return; }
  try {
    recog.start();
    setListening(true);
  } catch (e) {
    toast("语音启动失败，请重试", "error");
  }
}
function setListening(on) {
  listening = on;
  const mic = document.getElementById("micBtn");
  mic.classList.toggle("listening", on);
  mic.title = on ? "点击停止" : "语音输入";
}

/* ═══════════════ 启动 ═══════════════ */
async function boot() {
  watchViewport();
  setupDropClick();
  // URL 携带令牌（后端 ?pw= 旧链接兼容重定向产物）
  const q = new URLSearchParams(location.search);
  const t = q.get("t");
  if (t) {
    TOKEN = t;
    localStorage.setItem("om_token", t);
    history.replaceState({}, "", "/");
  }
  if (!TOKEN) { location.replace("/login.html"); return; }

  try {
    const d = await apiJSON("/api/auth/me");
    USER = d.user;
    if (!USER) throw new Error("no user");
  } catch (e) {
    return; // apiJSON 已跳转登录页
  }
  renderUser();
  initVoice();
  document.getElementById("ttsSwitch").classList.toggle("on", SETTINGS.autoTTS);
  loadCases();
  tryRestoreLocalSession();
}

function renderUser() {
  const letter = (USER.display_name || USER.username).slice(0, 1).toUpperCase() || "U";
  document.getElementById("userBtn").textContent = letter;
  document.getElementById("menuAvatar").textContent = letter;
  document.getElementById("menuName").textContent = USER.display_name || USER.username;
  document.getElementById("menuRole").innerHTML =
    `账号: <b style="color:#0f2f6f">${escapeHTML(USER.username)}</b>` +
    `<span class="role-pill ${USER.role === "admin" ? "admin" : ""}">${USER.role === "admin" ? "管理员 · 最高权限" : "普通用户"}</span>`;
  // 管理员专属入口（演示实例上服务端已关闭管理员功能，入口隐藏并给出说明）
  const isAdmin = USER.role === "admin";
  const adminVisible = isAdmin && !OM_DEMO_SURFACE;
  document.getElementById("adminEntry").style.display = adminVisible ? "flex" : "none";
  document.getElementById("debugEntry").style.display = adminVisible ? "flex" : "none";
  let hint = document.getElementById("demoAdminHint");
  if (OM_DEMO_SURFACE && isAdmin) {
    if (!hint) {
      hint = document.createElement("div");
      hint.id = "demoAdminHint";
      hint.style.cssText = "margin:10px 0 2px;padding:10px 12px;border-radius:10px;background:#fff7e6;" +
        "border:1px solid #f0c36d;color:#8a5a00;font-size:12px;line-height:1.75;text-align:left";
      const anchor = document.querySelector("#menuOverlay .menu-user");
      if (anchor && anchor.parentNode) anchor.parentNode.insertBefore(hint, anchor.nextSibling);
    }
    hint.innerHTML = "演示环境为保护真实病例，已关闭管理员功能（病例全量数据、用户管理）。" +
      "<br>如需管理，请改用生产入口并输入管理员密码。";
  } else if (hint) {
    hint.remove();
  }
}

function setupDropClick() {
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".exam-dd")) {
      document.querySelectorAll(".exam-dd .menu.show").forEach(m => m.classList.remove("show"));
    }
  });
}

/* ═══════════════ 病例 ═══════════════ */
async function loadCases() {
  try {
    const d = await apiJSON("/api/cases");
    cases = d;
    filterCases();
  } catch (e) {
    toast("加载病例列表失败", "error");
  }
}

/* ═══════════════ 模式切换 ═══════════════ */
function setModeUI(mode) {
  currentMode = mode;
  document.querySelectorAll(".tab").forEach((el, i) => {
    el.classList.toggle("on", el.dataset.mode === mode);
  });
  document.querySelectorAll(".btab").forEach(el => {
    el.classList.toggle("on", el.dataset.mode === mode);
  });
  document.getElementById("caseBar").style.display = (mode === "training" || mode === "test") ? "flex" : "none";
  const cls = mode === "consult" ? "consult" : "training";
  document.getElementById("chatArea").className = "chat-area " + cls;
  document.getElementById("endBtn").style.display = (mode === "training" || mode === "test") ? "inline-block" : "none";
  document.getElementById("scorePanel").classList.remove("show");
  testTitle = "医学生"; testHideTutor = false; testShowRefOnly = false;
}

function switchMode(mode) {
  setModeUI(mode);
  resetSession();
  if (mode === "test") document.getElementById("titleOverlay").classList.add("show");
}

/* ═══════════════ 开始/训练/测试 ═══════════════ */
function handleStart() { startTraining(false); }

function onCaseChange() {
  const sel = document.getElementById("caseSelect");
  if (sel.value && cases.length) {
    const c = cases.find(x => x.id === sel.value);
    if (c) document.getElementById("caseLabel").textContent = `${c.display} | ${c.age}${t("岁")} ${t(c.gender)}`;
  }
}

function startTraining(isTest) {
  const cid = document.getElementById("caseSelect").value;
  if (!cid) { toast("请先选择训练病例", "warn"); return; }
  const mode = isTest ? "test" : "training";
  setLoading(true);
  setChatHTML(`<div class="empty-state"><div class="spinner"></div><p style="margin-top:14px;font-size:12px;color:#94a3b8">正在准备${mode === "test" ? "测试" : ""}患者...</p></div>`);

  api("/api/chat/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, case_id: cid, title: testTitle }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "启动失败");
      sessionId = d.session_id;
      saveLocalSession();
      document.getElementById("chatArea").innerHTML = "";
      addMessage("patient", d.first_message, { speak: true });
      enableChat(true);
      document.getElementById("endBtn").style.display = "inline-block";
      document.getElementById("examBar").style.display = "flex";
      document.getElementById("statusBar").style.display = "flex";
      document.getElementById("statusText").textContent = mode === "test" ? `测试中 (${testTitle})` : "问诊中";
      const cc = cases.find(x => x.id === cid);
      document.getElementById("caseLabel").textContent = `${cc ? cc.display : cid} | ${d.patient_info.age}${t("岁")} ${t(d.patient_info.gender)}`;
      document.getElementById("scorePanel").classList.remove("show");
      clearDiagForm();
    })
    .catch(e => { toast(e.message, "error"); resetSession(); });
}

function selectTitle(title) {
  testTitle = title;
  testHideTutor = ["主治医师", "副主任医师", "主任医师"].includes(title);
  testShowRefOnly = ["副主任医师", "主任医师"].includes(title);
  document.getElementById("titleOverlay").classList.remove("show");
  startTraining(true);
}

function startConsult(firstMsg) {
  setLoading(true);
  setChatHTML('<div class="empty-state"><div class="spinner"></div><p style="margin-top:14px;font-size:12px;color:#94a3b8">正在连接主任医师...</p></div>');

  api("/api/chat/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: "consult" }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "启动失败");
      sessionId = d.session_id;
      saveLocalSession();
      document.getElementById("chatArea").innerHTML = "";
      addMessage("doctor", d.first_message, { speak: true });
      enableChat(true);
      // 用户此前输入的内容：接入会话后立即发出（doSend 负责渲染用户气泡）
      if (firstMsg) {
        doSend(firstMsg);
      }
    })
    .catch(e => { toast(e.message, "error"); resetSession(); });
}

/* ── 发送消息 ── */
function sendMessage() {
  const input = document.getElementById("msgInput"), msg = input.value.trim();
  if (!msg) return;
  if (!sessionId) {
    if (currentMode === "consult") {
      input.value = "";
      startConsult(msg);   // 首次发送：自动建立咨询会话并携带本条消息
      return;
    }
    toast("请先选择病例并开始问诊", "warn");
    return;
  }
  input.value = "";
  doSend(msg);
}

function doSend(msg) {
  const role = (currentMode === "training" || currentMode === "test") ? "student" : "patient";
  addMessage(role, msg);
  setLoading(true);

  api("/api/chat/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message: msg }),
  })
    .then(r => r.json().then(d => ({ ok: r.ok, data: d })))
    .then(({ ok, data: d }) => {
      if (!ok) throw new Error(d.error || "发送失败");
      addMessage(d.role, d.response, { speak: true });
    })
    .catch(e => toast(e.message, "error"))
    .finally(() => setLoading(false));
}

/* ═══════════════ 检查工具箱 ═══════════════ */
function toggleDD(btn) {
  const menu = btn.parentElement.querySelector(".menu");
  const menus = document.querySelectorAll(".exam-dd .menu.show");
  menus.forEach(m => { if (m !== menu) m.classList.remove("show"); });
  const willOpen = !menu.classList.contains("show");
  menu.classList.toggle("show");
  if (willOpen) {
    // 工具条是横向滚动容器，absolute 菜单会被裁剪 → 用 fixed 定位到按钮上方
    const r = btn.getBoundingClientRect();
    const w = Math.min(230, window.innerWidth - 16);
    menu.style.position = "fixed";
    menu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + "px";
    menu.style.bottom = (window.innerHeight - r.top + 6) + "px";
    menu.style.width = w + "px";
  }
}

function requestExam(tool, okBtn) {
  if (okBtn) okBtn.closest(".menu").classList.remove("show");
  if (!sessionId) { toast("请先开始训练", "warn"); return; }
  let params = {};
  if (tool === "lab_tests") {
    const cbs = document.querySelectorAll("#dd-lab .menu input:checked");
    if (cbs.length === 0) { toast("请至少选择一项化验项目", "warn"); return; }
    params.tests = Array.from(cbs).map(c => c.value);
  } else if (tool === "microbiology") {
    const cbs = document.querySelectorAll("#dd-micro .menu input:checked");
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
      const pending = document.getElementById("chatArea").querySelector(".msg-pending");
      if (pending) pending.remove();
      addSystemMsg(d.result);
      if (d.photos && d.photos.length > 0) addPhotos(d.photos);
    })
    .catch(e => toast(e.message, "error"));
}

function addPhotos(urls) {
  const area = document.getElementById("chatArea");
  const div = document.createElement("div");
  div.className = "msg system";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = '<div class="role">\u{1F4F7} 临床照片</div>';
  const grid = document.createElement("div");
  grid.style.cssText = "display:flex;flex-wrap:wrap;gap:6px;margin-top:6px";
  urls.forEach(url => {
    const img = document.createElement("img");
    img.src = url;
    img.style.cssText = "max-width:46vw;max-height:150px;border-radius:8px;border:1px solid #e2e8f0;cursor:pointer;object-fit:cover";
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
    background: "rgba(0,0,0,.88)", zIndex: "300", display: "flex",
    alignItems: "center", justifyContent: "center", cursor: "pointer",
    WebkitBackdropFilter: "blur(2px)",
  });
  const img = document.createElement("img");
  img.src = url;
  img.style.cssText = "max-width:94vw;max-height:94vh;border-radius:10px;object-fit:contain";
  lb.appendChild(img);
  lb.onclick = () => lb.remove();
  document.body.appendChild(lb);
}

function addSystemMsg(text, isPending = false) {
  const area = document.getElementById("chatArea");
  const es = area.querySelector(".empty-state");
  if (es) es.remove();

  const div = document.createElement("div");
  div.className = "msg system" + (isPending ? " msg-pending" : "");
  const mcol = document.createElement("div");
  mcol.className = "mcol";
  mcol.innerHTML = '<div class="role">\u{1F52C} 检查结果</div>';
  const bubble = document.createElement("div");
  bubble.className = "bubble";

  if (isPending) {
    bubble.innerHTML = '<div class="spinner-sm"></div><span style="font-size:11px;color:#888;margin-left:6px">获取中...</span>';
  } else {
    const pre = document.createElement("pre");
    pre.textContent = text;
    bubble.appendChild(pre);
  }
  mcol.appendChild(bubble);
  div.appendChild(mcol);
  area.appendChild(div);
  scrollToBottom();
}

/* ═══════════════ 结束 → 评分 ═══════════════ */
function endConsultation() {
  document.getElementById("statusText").textContent = "问诊结束，请填写诊断";
  document.getElementById("diagOverlay").classList.add("show");
}

function closeOverlay(id) {
  document.getElementById(id).classList.remove("show");
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

  closeOverlay("diagOverlay");
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

  document.getElementById("scoreDiag").innerHTML = `<div class="v">${sc.western_diagnosis.score}</div><div class="l">西医诊断 (70%) · ${sc.western_diagnosis.level}</div>`;
  document.getElementById("scoreDiag").className = "score-item " + levelCls(sc.western_diagnosis.score);

  document.getElementById("scoreTreat").innerHTML = `<div class="v">${sc.treatment_plan.score}</div><div class="l">治疗方案 (30%) · ${sc.treatment_plan.level}</div>`;
  document.getElementById("scoreTreat").className = "score-item " + levelCls(sc.treatment_plan.score);

  if (sc.tcm_bonus) {
    document.getElementById("scoreTCM").innerHTML = `<div class="v">+${sc.tcm_bonus.score}</div><div class="l">中医加分 (最多+10)</div>`;
    document.getElementById("scoreTCM").className = "score-item great";
  } else {
    document.getElementById("scoreTCM").innerHTML = '<div class="v">+0</div><div class="l">中医加分</div>';
    document.getElementById("scoreTCM").className = "score-item ok";
  }
  document.getElementById("scoreEff").innerHTML = `<div class="v">${d.stats.rounds}轮</div><div class="l">问诊轮次</div>`;
  document.getElementById("scoreEff").className = "score-item great";

  const gb = document.getElementById("gradeBadge");
  gb.textContent = sc.grade;
  gb.className = "grade-badge grade-" + sc.grade;
  document.getElementById("totalScore").textContent = `总分: ${sc.total}`;

  const icd11 = d.truth.icd11 ? ` (ICD-11: ${escapeHTML(d.truth.icd11)})` : "";
  document.getElementById("truthContent").innerHTML =
    `<b>西医诊断:</b> ${escapeHTML(d.truth.diagnosis)}${icd11}<br>` +
    `<b>中医辨证:</b> ${escapeHTML(d.truth.tcm || "无")}<br>` +
    `<b>治疗方案:</b> ${escapeHTML(d.truth.treatment || "无")}`;

  document.getElementById("scorePanel").classList.add("show");
  document.getElementById("endBtn").style.display = "none";
  document.getElementById("statusText").textContent = currentMode === "test" ? `评估完成 (${testTitle})` : "评估完成";

  if (d.test_mode) {
    testHideTutor = d.test_mode.hide_tutor;
    testShowRefOnly = d.test_mode.show_ref_only;
  }
  const tutorBtn = document.getElementById("tutorBtn");
  tutorBtn.style.display = testHideTutor ? "none" : "block";
  if (testHideTutor) document.getElementById("tutorReview").style.display = "none";
  ["scoreDiag", "scoreTreat", "scoreTCM", "scoreEff", "gradeBadge", "totalScore"].forEach(id => {
    document.getElementById(id).style.display = testShowRefOnly ? "none" : "";
  });
}

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

/* ═══════════════ 消息渲染 ═══════════════ */
function addMessage(role, text, opts = {}) {
  const area = document.getElementById("chatArea");
  const es = area.querySelector(".empty-state");
  if (es) es.remove();

  const labels = { student: "\u{1F9D1}\u200D\u2695\uFE0F 医学生", patient: "\u{1F9D1} 患者", doctor: "\u{1F468}\u200D\u2695\uFE0F 主任医师" };

  const div = document.createElement("div");
  div.className = "msg " + (role === "student" ? "right" : "left");
  const mcol = document.createElement("div");
  mcol.className = "mcol";

  const label = document.createElement("div");
  label.className = "role";
  label.textContent = labels[role] || role;
  mcol.appendChild(label);

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "doctor") {
    const content = document.createElement("div");
    content.innerHTML = simpleMarkdown(text);
    bubble.appendChild(content);
    content.querySelectorAll("li").forEach(li => {
      if (!li.parentNode.matches("ul")) {
        const ul = document.createElement("ul");
        li.parentNode.insertBefore(ul, li);
        ul.appendChild(li);
      }
    });
  } else {
    bubble.textContent = text;
  }
  mcol.appendChild(bubble);

  // 语音播报按钮（患者/医生回复均可朗读）
  if ((role === "patient" || role === "doctor") && HAS_TTS) {
    const vb = document.createElement("button");
    vb.className = "voice-btn";
    vb.textContent = "\u{1F50A} 朗读";
    vb.title = "朗读本条消息";
    vb.onclick = (e) => { e.stopPropagation(); speakText(text, vb); };
    mcol.appendChild(vb);
  }

  div.appendChild(mcol);
  area.appendChild(div);
  scrollToBottom();
  if (opts.speak && SETTINGS.autoTTS) {
    setTimeout(() => speakText(text), 300);
  }
}

/* ═══════════════ 加载状态 ═══════════════ */
function setLoading(loading) {
  document.getElementById("sendBtn").disabled = loading;
  document.getElementById("msgInput").disabled = loading;
  if (!loading) document.getElementById("msgInput").focus();
}
function enableChat(enabled) {
  document.getElementById("sendBtn").disabled = !enabled;
  document.getElementById("msgInput").disabled = !enabled;
  if (enabled) setTimeout(() => document.getElementById("msgInput").focus(), 60);
}
function setChatHTML(html) {
  document.getElementById("chatArea").innerHTML = html;
}

/* ═══════════════ 重置 ═══════════════ */
function resetSession() {
  sessionId = null;
  clearLocalSession();
  const area = document.getElementById("chatArea");
  const showSelector = currentMode === "training" || currentMode === "test";
  let title, desc;
  if (currentMode === "test") {
    title = "测试模式";
    desc = "选择病例开始测试。问诊参数将被记录保存，供后续分析。可选择职称级别。";
  } else if (currentMode === "training") {
    title = "医学生训练模式";
    desc = "选择病例开始模拟接诊。患者的诊断不会显示，请通过问诊自行判断。";
  } else {
    title = "患者咨询服务";
    desc = "描述您的口腔问题，获取参考建议（仅供参考，不作为诊疗依据）。";
  }
  area.innerHTML = `<div class="empty-state"><div class="eicon">\u{1F4AC}</div>
    <div class="etitle">${title}</div><p>${desc}</p></div>`;
  area.className = "chat-area " + (showSelector ? "training" : "consult");
  document.getElementById("msgInput").value = "";
  document.getElementById("sendBtn").disabled = showSelector;
  document.getElementById("msgInput").disabled = showSelector;
  document.getElementById("endBtn").style.display = "none";
  document.getElementById("examBar").style.display = "none";
  document.getElementById("scorePanel").classList.remove("show");
  document.getElementById("statusBar").style.display = "none";
  document.getElementById("tutorReview").style.display = "none";
  ["scoreDiag","scoreTreat","scoreTCM","scoreEff","gradeBadge","totalScore"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = "";
  });
  testTitle = "医学生"; testHideTutor = false; testShowRefOnly = false;
}

/* ═══════════════ 本地会话记忆 ═══════════════ */
function saveLocalSession() {
  try { localStorage.setItem("om_session", JSON.stringify({ session_id: sessionId, mode: currentMode })); } catch (e) {}
}
function clearLocalSession() {
  try { localStorage.removeItem("om_session"); } catch (e) {}
}

function applyRestoredSession(d, silent) {
  const mode = d.mode || "training";
  setModeUI(mode);
  sessionId = d.session_id;
  testTitle = d.title || "医学生";

  document.getElementById("chatArea").innerHTML = "";
  (d.history || []).forEach(h => {
    if (h.role === "system") addSystemMsg(h.content);
    else addMessage(h.role, h.content);
  });

  if (mode === "training" || mode === "test") {
    document.getElementById("endBtn").style.display = "inline-block";
    document.getElementById("examBar").style.display = "flex";
    document.getElementById("statusBar").style.display = "flex";
    document.getElementById("statusText").textContent = mode === "test" ? `测试中 (${testTitle})` : "问诊中";
    const cc = cases.find(x => x.id === d.case_id);
    const pi = d.patient_info || {};
    document.getElementById("caseLabel").textContent = `${cc ? cc.display : d.case_id} | ${pi.age || "?"}${t("岁")} ${t(pi.gender || "")}`;
    const sel = document.getElementById("caseSelect");
    if (Array.from(sel.options).some(o => o.value === d.case_id)) sel.value = d.case_id;
  } else {
    document.getElementById("statusBar").style.display = "flex";
    document.getElementById("statusText").textContent = "咨询中";
  }

  if (d.resumable === false) {
    enableChat(false);
    document.getElementById("msgInput").placeholder = "该会话仅可查看（服务端状态已失效）";
    clearLocalSession();
    if (!silent) toast("该会话仅可查看，无法继续对话", "warn");
  } else {
    enableChat(true);
    saveLocalSession();
    if (!silent) toast("已恢复历史会话，可继续对话", "success");
  }
}

async function fetchSessionHistory(sid) {
  return apiJSON("/api/chat/history?session_id=" + encodeURIComponent(sid));
}

function tryRestoreLocalSession() {
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem("om_session") || "null"); } catch (e) { saved = null; }
  if (!saved || !saved.session_id) return;
  fetchSessionHistory(saved.session_id)
    .then(d => applyRestoredSession(d, false))
    .catch(() => {});
}

/* ═══════════════ 历史会话 ═══════════════ */
function openHistory() {
  document.getElementById("histOverlay").classList.add("show");
  loadHistoryList();
}
async function loadHistoryList() {
  const box = document.getElementById("historyList");
  box.innerHTML = '<div style="text-align:center;padding:30px"><div class="spinner"></div><p style="margin-top:10px;font-size:12px;color:#94a3b8">加载中...</p></div>';
  try {
    const list = await apiJSON("/api/sessions");
    if (!list.length) {
      box.innerHTML = '<div class="empty-state"><div class="eicon">&#x1F4ED;</div><p>暂无历史会话</p></div>';
      return;
    }
    box.innerHTML = "";
    list.forEach(s => {
      const ts = new Date(s.last_active * 1000);
      const time = isNaN(ts.getTime()) ? "" :
        ts.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
      const isConsult = s.mode === "consult";
      const name = isConsult ? "患者咨询" : `${s.case_display || s.case_id}${s.mode === "test" ? ` · ${escapeHTML(s.title)}` : ""}`;
      const row = document.createElement("div");
      row.className = "hist-row";
      row.innerHTML = `
        <span class="hist-badge ${isConsult ? "consult" : "other"}">${s.mode_label}</span>
        <div class="hist-main">
          <div class="hist-name">${name}</div>
          <div class="hist-meta"><span>${time}</span><span>${s.msg_count} 条消息</span>
            ${s.username ? `<span class="hist-user">${escapeHTML(s.username)}</span>` : ""}</div>
        </div>
        <div class="hist-act">
          <button class="go" onclick="restoreSession('${s.session_id}')">继续</button>
          <button class="del" onclick="deleteSession('${s.session_id}')">删除</button>
        </div>`;
      box.appendChild(row);
    });
  } catch (e) {
    box.innerHTML = `<p style="color:#f87171;text-align:center;padding:20px">加载失败: ${escapeHTML(e.message)}</p>`;
  }
}
async function restoreSession(sid) {
  try {
    const d = await fetchSessionHistory(sid);
    closeOverlay("histOverlay");
    applyRestoredSession(d, false);
  } catch (e) { toast(e.message, "error"); }
}
async function deleteSession(sid) {
  if (!confirm("确定删除该历史会话？删除后无法恢复。")) return;
  try {
    await apiJSON("/api/sessions/" + encodeURIComponent(sid), { method: "DELETE" });
    if (sessionId === sid) resetSession();
    loadHistoryList();
    toast("已删除", "success");
  } catch (e) { toast(e.message, "error"); }
}

/* ═══════════════ 随机/筛选 ═══════════════ */
function randomCase() {
  const visible = getVisibleCases();
  if (!visible.length) { toast("没有可选的病例", "warn"); return; }
  const pick = visible[Math.floor(Math.random() * visible.length)];
  document.getElementById("caseSelect").value = pick.id;
  onCaseChange();
  toast(`随机选中: ${pick.display}`, "success");
}
function getVisibleCases() {
  const filter = document.getElementById("photoFilter");
  return (filter && filter.checked) ? cases.filter(c => c.has_photos) : cases;
}
function filterCases() {
  const filter = document.getElementById("photoFilter");
  const sel = document.getElementById("caseSelect");
  const currentVal = sel.value;
  sel.innerHTML = '<option value="">-- 请选择病例 --</option>';
  getVisibleCases().forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.textContent = `${c.display} | ${c.age}${t("岁")} ${t(c.gender)}${c.has_photos ? " \u{1F4F7}" : ""}`;
    sel.appendChild(opt);
  });
  if (getVisibleCases().find(c => c.id === currentVal)) sel.value = currentVal;
}

/* ═══════════════ 用户菜单/账户 ═══════════════ */
function toggleUserMenu() {
  const ov = document.getElementById("menuOverlay");
  ov.classList.toggle("show");
}
function doLogout() {
  api("/api/auth/logout", { method: "POST" }).finally(() => { logoutLocal(); });
  logoutLocal();
}
function logoutLocal() {
  localStorage.removeItem("om_token");
  localStorage.removeItem("om_user");
  localStorage.removeItem("om_session");
  location.replace("/login.html");
}

function openPwSheet() {
  closeOverlay("menuOverlay");
  document.getElementById("oldPw").value = "";
  document.getElementById("newPw").value = "";
  document.getElementById("newPw2").value = "";
  document.getElementById("pwOverlay").classList.add("show");
}
async function submitPwChange() {
  const oldPw = document.getElementById("oldPw").value;
  const newPw = document.getElementById("newPw").value;
  const newPw2 = document.getElementById("newPw2").value;
  if (!oldPw) { toast("请输入原密码", "warn"); return; }
  if (newPw.length < 6) { toast("新密码至少6位", "warn"); return; }
  if (newPw !== newPw2) { toast("两次输入的新密码不一致", "warn"); return; }
  try {
    await apiJSON("/api/auth/change_password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: oldPw, new_password: newPw }),
    });
    toast("密码已修改，请重新登录", "success");
    setTimeout(() => logoutLocal(), 800);
  } catch (e) { toast(e.message, "error"); }
}

/* ═══════════════ 用户管理（admin） ═══════════════ */
function openAdmin() {
  closeOverlay("menuOverlay");
  document.getElementById("adminOverlay").classList.add("show");
  loadAdminList();
}
async function loadAdminList() {
  const box = document.getElementById("adminList");
  box.innerHTML = '<div style="text-align:center;padding:24px"><div class="spinner"></div></div>';
  try {
    const d = await apiJSON("/api/admin/users");
    box.innerHTML = "";
    d.users.forEach(u => {
      const isSelf = USER && u.id === USER.id;
      const row = document.createElement("div");
      row.className = "um-row";
      row.innerHTML = `
        <div class="um-av">${escapeHTML((u.display_name || u.username).slice(0, 1).toUpperCase())}</div>
        <div class="um-main">
          <div class="um-name">${escapeHTML(u.display_name || u.username)}
            <span class="role-pill ${u.role === "admin" ? "admin" : ""}">${u.role === "admin" ? "管理员" : "用户"}</span>
            ${u.disabled ? '<span class="role-pill" style="background:#fee2e2;color:#b91c1c">已禁用</span>' : ""}
          </div>
          <div class="um-sub">@${escapeHTML(u.username)} · ${escapeHTML(u.created_at || "")}</div>
        </div>
        <div class="um-act">
          ${isSelf ? "" : `<button class="r" onclick="adminResetPw(${u.id},'${escapeHTML(u.username)}')">重置密码</button>
          <button class="t ${u.disabled ? "off" : ""}" onclick="adminToggleUser(${u.id},${!u.disabled})">${u.disabled ? "启用" : "禁用"}</button>
          <button class="d" onclick="adminDeleteUser(${u.id},'${escapeHTML(u.username)}')">删除</button>`}
        </div>`;
      box.appendChild(row);
    });
  } catch (e) {
    box.innerHTML = `<p style="color:#f87171">加载失败: ${escapeHTML(e.message)}</p>`;
  }
}
async function adminCreateUser() {
  const username = document.getElementById("nuUser").value.trim();
  const display_name = document.getElementById("nuName").value.trim();
  const password = document.getElementById("nuPw").value;
  const role = document.getElementById("nuRole").value;
  if (!username || !password) { toast("请填写用户名和密码", "warn"); return; }
  try {
    await apiJSON("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, role, display_name }),
    });
    toast("用户已创建", "success");
    document.getElementById("nuUser").value = "";
    document.getElementById("nuName").value = "";
    document.getElementById("nuPw").value = "";
    loadAdminList();
  } catch (e) { toast(e.message, "error"); }
}
async function adminResetPw(id, name) {
  const pw = prompt(`为 ${name} 设置新密码（至少6位）：`);
  if (pw === null) return;
  if (pw.length < 6) { toast("密码至少6位", "warn"); return; }
  try {
    await apiJSON(`/api/admin/users/${id}/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pw }),
    });
    toast("密码已重置", "success");
    loadAdminList();
  } catch (e) { toast(e.message, "error"); }
}
async function adminToggleUser(id, disabled) {
  try {
    await apiJSON(`/api/admin/users/${id}/disabled`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disabled }),
    });
    toast(disabled ? "已禁用" : "已启用", "success");
    loadAdminList();
  } catch (e) { toast(e.message, "error"); }
}
async function adminDeleteUser(id, name) {
  if (!confirm(`确定删除用户 ${name}？其会话将保留（仅管理员可见）。`)) return;
  try {
    await apiJSON(`/api/admin/users/${id}`, { method: "DELETE" });
    toast("已删除", "success");
    loadAdminList();
  } catch (e) { toast(e.message, "error"); }
}

/* ═══════════════ 调试面板（admin） ═══════════════ */
let debugData = null, debugVisible = false;
function toggleDebug() {
  debugVisible = !debugVisible;
  document.getElementById("debugPanel").classList.toggle("show", debugVisible);
  if (debugVisible && !debugData) loadDebugData();
}
async function loadDebugData() {
  document.getElementById("debugContent").innerHTML =
    '<div style="text-align:center;padding:40px"><div class="spinner"></div><p style="margin-top:10px">加载中...</p></div>';
  try {
    debugData = await apiJSON("/api/cases/debug");
    renderDebugTable();
    toast(`已加载 ${debugData.length} 例病例`, "success");
  } catch (e) {
    document.getElementById("debugContent").innerHTML = `<p style="color:#f87171">加载失败: ${escapeHTML(e.message)}</p>`;
  }
}
function renderDebugTable() {
  if (!debugData) return;
  const search = (document.getElementById("debugSearch")?.value || "").toLowerCase();
  const filtered = search ? debugData.filter(c =>
    c.id.toLowerCase().includes(search) ||
    c.diagnosis.toLowerCase().includes(search) ||
    c.tcm_syndrome.toLowerCase().includes(search)) : debugData;
  const photoCount = debugData.filter(c => c.has_photos).length;
  let html = `<div style="margin-bottom:8px;color:#94a3b8">共 ${debugData.length} 例 | 有照片: ${photoCount} 例 | 筛选: ${filtered.length} 例</div>`;
  if (window.innerWidth < 900) {
    // 移动端卡片式
    filtered.forEach(c => {
      html += `<div style="background:#0f172a;border-radius:10px;padding:10px 12px;margin-bottom:8px" onclick="openCaseDetail('${c.id}')">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <b>${escapeHTML(c.display)}</b>
          <span style="color:#60a5fa;font-size:11px">${escapeHTML(c.id)} ${c.has_photos ? "\u{1F4F7}" + (c.photo_count || "") : ""}</span>
        </div>
        <div style="color:#7dd3fc;margin-top:5px;font-size:12.5px">${escapeHTML(c.diagnosis) || "-"}</div>
        <div style="color:#fbbf24;font-size:11.5px;margin-top:3px">${escapeHTML(c.tcm_syndrome) || ""}</div>
      </div>`;
    });
  } else {
    html += '<div style="overflow-x:auto"><table class="dp-tbl"><thead><tr><th>编号</th><th>ID</th><th>西医诊断</th><th>ICD-11</th><th>中医辨证</th><th>年龄/性别</th><th>主诉</th><th>照片</th></tr></thead><tbody>';
    filtered.forEach((c, i) => {
      const bg = i % 2 === 0 ? "#0f172a" : "#16213e";
      html += `<tr style="background:${bg}" onclick="openCaseDetail('${c.id}')" title="点击查看完整信息">
        <td>${escapeHTML(c.display)}</td><td style="color:#60a5fa;text-decoration:underline">${escapeHTML(c.id)}</td>
        <td>${escapeHTML(c.diagnosis) || "-"}</td><td style="color:#94a3b8">${escapeHTML(c.icd11) || "-"}</td>
        <td style="color:#fbbf24">${escapeHTML(c.tcm_syndrome) || "-"}</td>
        <td>${c.age}${t("岁")}/${t(c.gender)}</td>
        <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHTML(c.chief_complaint)}">${escapeHTML(c.chief_complaint) || "-"}</td>
        <td style="text-align:center">${c.has_photos ? `\u{1F4F7} ${c.photo_count || "有"}` : "-"}</td></tr>`;
    });
    html += "</tbody></table></div>";
  }
  document.getElementById("debugContent").innerHTML = html;
}

/* ═══════════════ 病例详情 + 讨论区 ═══════════════ */
let currentDetailCid = null;
async function openCaseDetail(cid) {
  currentDetailCid = cid;
  const ov = document.getElementById("detailOverlay");
  ov.classList.add("show");
  document.getElementById("detailBody").innerHTML = '<div class="spinner"></div><p style="text-align:center;margin-top:10px;font-size:12px">加载中...</p>';
  document.getElementById("detailComments").innerHTML = "";
  document.getElementById("commentInput").value = "";
  try {
    const d = await apiJSON("/api/cases/" + cid + "/full");
    renderDetail(d);
    loadComments(cid);
  } catch (e) {
    document.getElementById("detailBody").innerHTML = `<p style="color:#f87171">加载失败: ${escapeHTML(e.message)}</p>`;
  }
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
  let html = `<h3 style="margin:0 0 8px;font-size:15px">&#x1F4CB; ${escapeHTML(d.case_id)}</h3>`;
  if (d.has_photos && d.photos) {
    html += `<div class="detail-photo">`;
    d.photos.slice(0, 12).forEach(url => {
      html += `<img src="${url}" onclick="openLightbox('${url}')" loading="lazy">`;
    });
    html += `</div>`;
  }
  for (const [table, label] of Object.entries(labels)) {
    const row = d[table];
    if (!row) continue;
    html += `<div class="detail-sec"><h4>${label}</h4><div class="dv">`;
    for (const [k, v] of Object.entries(row)) {
      if (k === "id" || k === "hadm_id" || v === null || v === "") continue;
      html += `<b>${fieldNames[k] || k}:</b> ${escapeHTML(String(v))}<br>`;
    }
    html += `</div></div>`;
  }
  document.getElementById("detailBody").innerHTML = html;
}
async function loadComments(cid) {
  try {
    const comments = await apiJSON("/api/cases/" + cid + "/comments");
    renderComments(comments);
  } catch (e) {
    document.getElementById("detailComments").innerHTML = '<p style="color:#94a3b8">评论加载失败</p>';
  }
}
function renderComments(comments) {
  const container = document.getElementById("detailComments");
  if (!comments.length) { container.innerHTML = '<p style="color:#94a3b8">暂无建议，欢迎留言讨论</p>'; return; }
  let html = "";
  comments.forEach(c => {
    html += `<div class="comment-item">
      <div class="ch"><span class="ca">${escapeHTML(c.author)}</span><span class="ct">${escapeHTML(c.created_at)}</span></div>
      <div class="cb">${escapeHTML(c.content)}</div>
      <div class="cv"><span onclick="voteComment('${c.id}','up')">&#x1F44D; ${c.up || 0}</span><span onclick="voteComment('${c.id}','down')">&#x1F44E; ${c.down || 0}</span></div>
    </div>`;
  });
  container.innerHTML = html;
}
async function submitComment() {
  const content = document.getElementById("commentInput").value.trim();
  if (!content) { toast("请输入建议内容", "warn"); return; }
  try {
    await apiJSON("/api/cases/" + currentDetailCid + "/comments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: USER.display_name || USER.username, content }),
    });
    document.getElementById("commentInput").value = "";
    loadComments(currentDetailCid);
    toast("建议已保存", "success");
  } catch (e) { toast("提交失败: " + e.message, "error"); }
}
async function voteComment(commentId, vote) {
  if (!currentDetailCid) return;
  try {
    await apiJSON("/api/comments/" + commentId + "/vote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id: currentDetailCid, vote }),
    });
    loadComments(currentDetailCid);
  } catch (e) { toast("投票失败", "error"); }
}

/* ═══════════════ 滚动 ═══════════════ */
function setupScrollButton() {
  if (document.getElementById("scrollBtn")) return;
  const chat = document.getElementById("chatArea");
  const btn = document.createElement("button");
  btn.id = "scrollBtn";
  btn.innerHTML = "&#x2B07;";
  btn.title = "滚动到底部";
  btn.onclick = () => { chat.scrollTop = chat.scrollHeight; btn.style.display = "none"; };
  chat.appendChild(btn);
  chat.addEventListener("scroll", () => {
    const atBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 60;
    btn.style.display = atBottom ? "none" : "block";
  });
}
function scrollToBottom() {
  const chat = document.getElementById("chatArea");
  chat.scrollTop = chat.scrollHeight;
}

/* ═══════════════ 键盘/全局事件 ═══════════════ */
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    ["histOverlay", "menuOverlay", "pwOverlay", "adminOverlay", "titleOverlay", "diagOverlay", "detailOverlay"].forEach(closeOverlay);
  }
  if (e.ctrlKey && e.key === "Enter" && (currentMode === "training" || currentMode === "test") && sessionId) {
    endConsultation();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  setupScrollButton();
  boot();
});

/* ── 界面语言切换后：重渲染动态列表（病例下拉/用户菜单等拼接串） ── */
document.addEventListener("om-lang-change", function () {
  if (!TOKEN || !USER) return;   // 尚未登录/尚未取到令牌时不请求，避免误判 401
  try { if (typeof loadCases === "function") loadCases(); } catch (e) {}
  try { if (typeof renderUser === "function") renderUser(); } catch (e) {}
});

/* ── 弹层交互：点击空白处 / 按 Esc 关闭 ──────────────────────────
 * 诊断填写面板（diagOverlay）除外：误触会让已填写的诊断内容丢失，
 * 该面板只能用「取消 / 提交」按钮关闭。 */
const NO_OUTSIDE_CLOSE = ["diagOverlay"];
document.addEventListener("click", function (e) {
  const ov = e.target.closest && e.target.closest(".sheet-overlay.show");
  if (!ov || NO_OUTSIDE_CLOSE.indexOf(ov.id) >= 0) return;
  if (e.target.closest(".sheet")) return;      // 点在弹层内容上不关闭
  closeOverlay(ov.id);
}, true);
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  document.querySelectorAll(".sheet-overlay.show").forEach(function (ov) {
    if (NO_OUTSIDE_CLOSE.indexOf(ov.id) < 0) closeOverlay(ov.id);
  });
});
