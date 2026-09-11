/* 颐鉴 · 中英文界面切换（i18n）
 * 设计要点：
 *  1) 只翻译「界面文字」——通过整节点精确匹配（允许保留前缀 emoji/符号），
 *     因此患者主诉、病历、检查结果等对话内容不会被误翻。
 *  2) 语言选择存 localStorage（om_lang），默认中文；英文模式下用 MutationObserver
 *     持续翻译动态插入的节点（面板、弹窗、列表）。
 *  3) 暴露 window.t(key) 供 app.js 的动态字符串使用。
 */
(function () {
  const LANG_KEY = "om_lang";
  let lang = localStorage.getItem(LANG_KEY) === "en" ? "en" : "zh";

  // ── 界面词典：中文 → English（键为中文原文，可带前缀 emoji） ──────────────
  const DICT = {
    // 品牌与登录页
    "口腔黏膜病AI诊断Agent": "Oral Mucosal Disease AI Agent",
    "口腔黏膜病 AI 诊断": "Oral Mucosal Disease AI Diagnosis",
    "中西医结合 · DeepSeek 智能诊疗": "Integrative Dentistry · DeepSeek",
    "颐鉴": "YIJIAN",
    "登 录": "Sign in",
    "注册账号": "Sign up",
    "注册并登录": "Sign up & sign in",
    "用户名": "Username",
    "密码": "Password",
    "用户名（2-24位，中英文/数字/下划线）": "Username (2–24 chars: letters, digits, _ or -)",
    "显示名称（可选，如：李医生）": "Display name (optional, e.g. Dr. Li)",
    "密码（至少6位）": "Password (min. 6 characters)",
    "确认密码": "Confirm password",
    "新用户请先注册，各用户会话记录相互独立。": "New users please sign up first. Each user's sessions are private.",
    "两次输入的密码不一致": "The two passwords do not match",
    "用户名或密码错误": "Incorrect username or password",
    "网络错误，请稍后重试": "Network error, please try again later",
    // 顶部与模式
    "历史": "History",
    "教程": "Tutorial",
    "语言": "Language",
    "医学生训练": "Student Training",
    "测试模式": "Test Mode",
    "患者咨询": "Consultation",
    "训练": "Training",
    "测试": "Test",
    "咨询": "Consult",
    "病例:": "Case:",
    "-- 请选择病例 --": "-- Select a case --",
    "随机": "Random",
    "有照片": "With photos",
    "开始问诊": "Start consultation",
    "问诊中": "In consultation",
    "已结束": "Ended",
    "结束问诊": "End consultation",
    "医学生训练模式": "Student Training Mode",
    "选择病例开始模拟接诊。患者的诊断不会显示，请通过问诊自行判断。":
      "Select a case to begin a simulated encounter. The diagnosis is hidden — reach it by interviewing the patient.",
    "测试模式说明": "Test Mode",
    "主治医师及以上不显示导师评语，仅展示参考答案。":
      "For attending physicians and above, tutor comments are hidden and only the reference answer is shown.",
    // 工具箱
    "工具箱:": "Toolbox:",
    "口腔检查": "Oral exam",
    "化验": "Lab tests",
    "微生物": "Microbiology",
    "病理": "Pathology",
    "中医四诊": "TCM diagnostics",
    "血常规(WBC)": "CBC (WBC)",
    "血沉(ESR)": "ESR",
    "C反应蛋白(CRP)": "CRP",
    "抗核抗体(ANA)": "ANA",
    "真菌涂片": "Fungal smear",
    "真菌培养": "Fungal culture",
    "细菌培养": "Bacterial culture",
    "HP检测": "H. pylori test",
    "确认申请": "Request",
    // 评估与评分
    "诊断评估结果": "Assessment",
    "总分: -": "Total: -",
    "总分": "Total",
    "西医诊断 (70%)": "Diagnosis (70%)",
    "治疗方案 (30%)": "Treatment (30%)",
    "中医加分 (+0~10)": "TCM bonus (+0~10)",
    "问诊轮次": "Turns",
    "标准答案（仅训练可见）": "Reference answer (training only)",
    "导师点评": "Tutor review",
    "发送": "Send",
    // 历史与用户菜单
    "历史会话": "Session history",
    "会话保存在服务器，刷新页面、服务重启后仍可继续。各用户仅能查看自己的会话。":
      "Sessions are stored on the server and survive refresh or restart. You can only see your own sessions.",
    "加载中...": "Loading...",
    "语音播报（回复自动朗读）": "Read replies aloud (TTS)",
    "修改密码": "Change password",
    "病例调试面板": "Case debug panel",
    "用户管理": "User management",
    "退出登录": "Sign out",
    "原密码": "Current password",
    "新密码（至少6位）": "New password (min. 6 characters)",
    "确认新密码": "Confirm new password",
    "取消": "Cancel",
    "确认修改": "Confirm",
    "新增用户": "New user",
    "普通用户": "User",
    "管理员": "Administrator",
    "创建账号": "Create account",
    "选择您的职称": "Select your title",
    "医学生": "Medical student",
    "住院医师": "Resident",
    "主治医师": "Attending",
    "副主任医师": "Associate chief physician",
    "主任医师": "Chief physician",
    // 诊断填写
    "请给出您的诊断和治疗方案": "Your diagnosis and treatment plan",
    "基于刚才的问诊对话，填写以下内容。系统将自动评分。":
      "Based on the consultation above, fill in the following. It will be scored automatically.",
    "1. 西医诊断（主要诊断名称）": "1. Western diagnosis (primary)",
    "2. 中医辨证分型": "2. TCM syndrome pattern",
    "3. 治疗方案（局部+全身用药要点）": "3. Treatment plan (topical + systemic)",
    "提交评分": "Submit",
    // 其他面板
    "病例详情": "Case details",
    "讨论区": "Discussion",
    "暂无评论": "No comments yet",
    "调试面板 — 全部病例": "Debug panel — all cases",
    "关闭": "Close",
    "刷新": "Refresh",
    // 占位符 / 提示
    "用户中心": "Account",
    "语音输入": "Voice input",
    "输入问诊内容...": "Type your question...",
    "请输入原密码": "Enter current password",
    "请输入新密码": "Enter new password",
    "再次输入新密码": "Re-enter new password",
    "显示名称(可选)": "Display name (optional)",
    "密码(≥6位)": "Password (min. 6 chars)",
    "例如：糜烂型口腔扁平苔藓": "e.g. Erosive oral lichen planus",
    "例如：肝郁气滞，兼有血瘀证（无中医数据可留空）": "e.g. Liver-qi stagnation with blood stasis (leave blank if no TCM data)",
    "例如：曲安奈德软膏bid外用；泼尼松20mg qd口服": "e.g. Triamcinolone ointment b.i.d. topically; prednisone 20 mg q.d. orally",
    "输入您的建议或讨论内容...": "Write your comment...",
    "搜索病例ID/诊断/辨证...": "Search case ID / diagnosis / pattern...",
    // 运行时状态（app.js）
    "请先选择病例": "Please select a case first",
    "会话已过期，请重新选择病例开始问诊": "Session expired — please start a new consultation",
    "请先结束问诊再提交诊断": "Please end the consultation before submitting",
    "请填写西医诊断": "Please enter the western diagnosis",
    "正在提交...": "Submitting...",
    "已提交": "Submitted",
    "患者": "Patient",
    "医生": "Doctor",
    "医学生提问": "Student",
    "主任医师": "Chief physician",
    "系统": "System",
    "提示": "Notice",
    "确定": "OK",
    "删除": "Delete",
    "继续": "Resume",
    "查看": "View",
    "评分中...": "Scoring...",
    "生成中...": "Generating...",
    "本轮问诊已结束": "This consultation has ended",
    "请等待患者回复": "Waiting for the patient",
    // 品牌补充与教程
    "颐鉴 · 口腔黏膜病 AI 诊断": "YIJIAN · Oral Mucosal Disease AI Diagnosis",
    "中西医结合口腔黏膜病 AI 诊断智能体": "Integrative Oral Mucosal Disease AI Diagnostic Agent",
    "中国中医科学院西苑医院 · 口腔科": "Xiyuan Hospital, CACMS · Dept. of Oral Medicine",
    "① 选择患者": "1. Choose a patient",
    "② 开始问诊": "2. Start the consultation",
    "③ 问诊对话": "3. Interview the patient",
    "④ 申请检查": "4. Order examinations",
    "⑤ 结束问诊": "5. End the consultation",
    "⑥ 填写诊断并提交": "6. Fill in the diagnosis",
    "在病例下拉框中选择一位患者，或点「随机」由系统抽取一例。训练模式下不会显示诊断，需要你自己问出来。": "Pick a patient from the case list, or tap Random. The diagnosis is hidden in training mode — you have to elicit it.",
    "选定病例后点「开始问诊」，患者 Agent 会先给出主诉，随后由你主导问诊。": "Tap Start consultation. The patient agent gives the chief complaint first; you lead the interview from there.",
    "在底部输入框提问并点「发送」。患者会用日常口语回答，可能跑题、记不清或带情绪——这正是真实门诊的样子。": "Type your question at the bottom and tap Send. The patient answers in everyday language and may ramble, forget or get emotional — just like a real clinic.",
    "需要客观依据时，用工具箱申请口腔检查、化验、微生物、病理或中医四诊。没做过的检查会明确回复「未行该检验或检查」。": "Use the toolbox to order an oral exam, lab tests, microbiology, pathology or TCM diagnostics. Tests that were not performed are reported explicitly.",
    "问诊充分后点「结束问诊」，系统结束对话并开放诊断评估面板。": "When you have enough information, tap End consultation to close the dialogue and unlock the assessment panel.",
    "填写西医诊断、中医辨证与治疗方案，点「提交评分」即可获得评分、标准答案；训练模式下还可请「导师点评」。": "Fill in the western diagnosis, TCM pattern and treatment plan, then tap Submit to see your score and the reference answer. In training mode you can also request a tutor review.",
    "不再提示": "Don't show again",
    "跳过教程": "Skip",
    "上一步": "Back",
    "下一步": "Next",
    "开始使用": "Start",
    "工具箱会在「开始问诊」后出现在对话区上方。": "The toolbox appears above the chat area once the consultation starts.",
    "「结束问诊」按钮只在问诊进行中出现——开始问诊后，它会出现在顶部状态栏右侧。": "The End consultation button only exists during a consultation — it appears on the right of the status bar once you start.",
    "诊断填写面板在点「结束问诊」后弹出，包含西医诊断 / 中医辨证 / 治疗方案三项。": "The diagnosis form opens after you end the consultation, covering western diagnosis, TCM pattern and treatment plan.",
    "演示环境为保护真实病例，已关闭管理员功能（病例全量数据、用户管理）。": "Administrator features are disabled in the demo environment to protect real patient cases (full case data and user management).",
    "如需管理，请改用生产入口并输入管理员密码。": "For administration, please use the production entry point and enter the administrator password.",
    "输入用户名": "Enter username",
    "输入密码": "Enter password",
    "设置用户名": "Choose a username",
    "昵称/姓名": "Display name",
    "设置密码": "Choose a password",
    "再次输入密码": "Re-enter password",
    "抗Dsg1": "anti-Dsg1",
    "抗Dsg3": "anti-Dsg3",
    "抗BP180": "anti-BP180",
    "抗BP230": "anti-BP230",
    "抗dsDNA": "anti-dsDNA",
    "抗核抗体": "ANA",
    "糖化血红蛋白": "HbA1c",
    "血清铁": "Serum iron",
    "叶酸": "Folate",
    "维生素B12": "Vitamin B12",
    "T-SPOT": "T-SPOT",
    "HIV检测": "HIV test",
    "血常规(WBC)": "CBC (WBC)",
    "测试模式会记录全部问诊参数并保存。主治医师及以上不显示导师评语，仅展示参考答案。": "Test mode records and saves all consultation parameters. For attending physicians and above, tutor comments are hidden and only the reference answer is shown.",
    "HSV PCR": "HSV PCR",
    "VZV PCR": "VZV PCR",
    "CMV PCR": "CMV PCR",
    "HE染色": "H&E stain",
    "Nikolsky征": "Nikolsky sign",
    "两次输入的新密码不一致": "The new passwords do not match",
    "中医四诊": "TCM diagnostics",
    "中医辨证": "TCM pattern",
    "主任医师": "Chief physician",
    "主治医师": "Attending physician",
    "主要诊断": "Primary diagnosis",
    "主诉": "Chief complaint",
    "全身治疗": "Systemic treatment",
    "副主任医师": "Associate chief physician",
    "加载病例列表失败": "Failed to load the case list",
    "化验结果": "Lab results",
    "医学生": "Medical student",
    "医学生训练模式": "Student training mode",
    "发病时间": "Onset",
    "发送失败": "Failed to send",
    "口腔卫生": "Oral hygiene",
    "口腔外体征": "Extraoral findings",
    "口腔检查": "Oral examination",
    "启动失败": "Failed to start",
    "启用": "Enable",
    "咨询中": "In consultation",
    "基本信息": "Basic information",
    "密码已修改，请重新登录": "Password changed — please sign in again",
    "密码已重置": "Password reset",
    "密码至少6位": "Password must be at least 6 characters",
    "局部治疗": "Topical treatment",
    "已关闭自动语音播报": "Auto TTS off",
    "已删除": "Deleted",
    "已启用": "Enabled",
    "已开启自动语音播报": "Auto TTS on",
    "已恢复历史会话，可继续对话": "Previous session restored — you can continue",
    "已禁用": "Disabled",
    "年龄": "Age",
    "建议已保存": "Comment saved",
    "当前浏览器不支持语音播报": "TTS is not supported in this browser",
    "当前浏览器不支持语音输入": "Speech input is not supported in this browser",
    "当前浏览器不支持语音输入（建议使用Chrome/Safari）": "Speech input is not supported in this browser (Chrome/Safari recommended)",
    "当前用药": "Current medications",
    "微生物检查": "Microbiology",
    "性别": "Sex",
    "患者咨询": "Patient consultation",
    "患者咨询服务": "Patient consultation service",
    "投票失败": "Vote failed",
    "描述您的口腔问题，获取参考建议（仅供参考，不作为诊疗依据）。": "Describe your oral problem to receive general reference information (for reference only; not a diagnosis or treatment).",
    "提交失败:": "Submission failed:",
    "新密码至少6位": "New password must be at least 6 characters",
    "普通用户": "User",
    "有": "Yes",
    "朗读本条消息": "Read this message aloud",
    "望诊": "Inspection",
    "未检测到语音，请重试": "No speech detected, please try again",
    "检查申请失败": "Failed to request the examination",
    "正在生成点评...": "Generating review...",
    "正在获取检查结果...": "Retrieving results...",
    "治疗方案": "Treatment plan",
    "活检部位": "Biopsy site",
    "测试": "Test",
    "测试模式": "Test mode",
    "滚动到底部": "Scroll to bottom",
    "点击停止": "Tap to stop",
    "点击查看完整信息": "Tap for details",
    "点评失败": "Review failed",
    "用户": "User",
    "用户已创建": "User created",
    "病损形态": "Lesion morphology",
    "病损质地": "Lesion texture",
    "病损部位": "Lesion location",
    "病损颜色": "Lesion colour",
    "病理检查": "Pathology",
    "病理诊断": "Pathological diagnosis",
    "症状演变": "Symptom evolution",
    "登录已过期": "Sign-in expired",
    "确定删除该历史会话？删除后无法恢复。": "Delete this session? This cannot be undone.",
    "禁用": "Disable",
    "管理员": "Administrator",
    "管理员 · 最高权限": "Administrator · full privileges",
    "系统性疾病": "Systemic diseases",
    "脉象": "Pulse",
    "舌苔": "Tongue coating",
    "舌质": "Tongue body",
    "补充说明": "Additional notes",
    "西医诊断": "Western diagnosis",
    "评估完成": "Assessment complete",
    "评分失败": "Scoring failed",
    "该会话仅可查看（服务端状态已失效）": "Read-only session (server state expired)",
    "该会话仅可查看，无法继续对话": "Read-only session — cannot continue",
    "语音启动失败，请重试": "Failed to start speech input, please try again",
    "语音识别服务网络异常，请重试": "Speech service network error, please try again",
    "语音输入": "Voice input",
    "语音输入需要 HTTPS 环境（建议为站点配置SSL证书）": "Speech input requires HTTPS (please configure an SSL certificate)",
    "语音输入需要 HTTPS 环境，当前为 HTTP，语音播报不受影响": "Speech input requires HTTPS; TTS still works over HTTP",
    "请先开始训练": "Please start a consultation first",
    "请先选择训练病例": "Please select a case first",
    "请填写用户名和密码": "Please enter your username and password",
    "请求失败": "Request failed",
    "请至少填写西医诊断": "Please enter at least the western diagnosis",
    "请至少选择一项化验项目": "Select at least one lab test",
    "请至少选择一项微生物检查项目": "Select at least one microbiology test",
    "请输入原密码": "Enter your current password",
    "请输入建议内容": "Please enter your comment",
    "辅助治疗": "Adjunctive treatment",
    "辨证分型": "TCM pattern",
    "过敏史": "Allergies",
    "选择病例开始测试。问诊参数将被记录保存，供后续分析。可选择职称级别。": "Select a case to begin the test. Consultation parameters are recorded for later analysis; you may choose your title level.",
    "鉴别诊断": "Differential diagnosis",
    "问诊": "Consultation",
    "问诊结束，请填写诊断": "Consultation ended — please fill in your diagnosis",
    "闻诊": "Auscultation & olfaction",
    "随访计划": "Follow-up plan",
    "预后": "Prognosis",
    "麦克风权限被拒绝，请在浏览器设置中允许麦克风": "Microphone permission denied — please allow it in your browser settings",
    "岁": "y",
    "女": "F",
    "男": "M",
    "账号:": "Account:",
    "测试中": "Testing",
    "正在准备训练患者...": "Preparing the simulated patient...",
    "正在准备测试患者...": "Preparing the test patient...",
    "正在连接主任医师...": "Connecting to the chief physician...",
    "中医辨证一致率": "TCM pattern agreement",
    "医学": "Medical",
    "删除": "Delete",
    "继续": "Resume",
  };

  // 供 app.js 动态字符串使用
  function t(zh) {
    if (lang !== "en") return zh;
    return Object.prototype.hasOwnProperty.call(DICT, zh) ? DICT[zh] : zh;
  }

  const ORIG = new WeakMap(); // 文本节点 → 原始中文
  const ORIG_ATTR = new WeakMap(); // 元素 → {attr: 原文}

  // 前缀（emoji/空白/符号）保留，正文查表
  // 渐进匹配：① 整串 → ② 仅剥前缀（emoji）→ ③ 再剥尾缀（▾ 等装饰符）
  // 注意：全角「:」「）」属于正文，不能被当作装饰符剥掉，故顺序不能颠倒。
  function matchKey(trimmed) {
    if (Object.prototype.hasOwnProperty.call(DICT, trimmed)) return ["", trimmed, ""];
    const p = trimmed.match(/^([^0-9A-Za-z\u4e00-\u9fff]*)([\s\S]*)$/);
    const pre = p ? p[1] : "", rest = p ? p[2] : trimmed;
    if (Object.prototype.hasOwnProperty.call(DICT, rest)) return [pre, rest, ""];
    const m = rest.match(/^([\s\S]*?)([^0-9A-Za-z\u4e00-\u9fff]*)$/);
    const mid = m ? m[1] : rest, suf = m ? m[2] : "";
    if (Object.prototype.hasOwnProperty.call(DICT, mid)) return [pre, mid, suf];
    return null;
  }

  function translateTextNode(node) {
    const raw = node.nodeValue;
    if (!raw) return;
    const trimmed = raw.trim();
    if (!trimmed) return;
    // 已含英文的句子（患者/医生内容）不处理
    const hit = matchKey(trimmed);
    if (!hit) return;
    const prefix = hit[0], core = hit[1], suffix = hit[2];
    if (!ORIG.has(node)) ORIG.set(node, raw);
    const lead = raw.slice(0, raw.indexOf(trimmed));
    const tail = raw.slice(raw.indexOf(trimmed) + trimmed.length);
    node.nodeValue = lead + prefix + DICT[core] + suffix + tail;
  }

  const ATTRS = ["placeholder", "title", "aria-label"];
  function translateAttrs(el) {
    if (!el.getAttribute) return;
    ATTRS.forEach(function (a) {
      const v = el.getAttribute(a);
      if (!v) return;
      const hit = matchKey(v.trim());
      if (!hit) return;
      const prefix = hit[0], core = hit[1], suffix = hit[2];
      let store = ORIG_ATTR.get(el);
      if (!store) { store = {}; ORIG_ATTR.set(el, store); }
      if (!(a in store)) store[a] = v;
      el.setAttribute(a, prefix + DICT[core] + suffix);
    });
  }

  function walk(root, fn) {
    if (!root) return;
    if (root.nodeType === 3) { fn(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9) return;
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let n; while ((n = tw.nextNode())) fn(n);
    if (root.querySelectorAll) root.querySelectorAll("[placeholder],[title],[aria-label]").forEach(translateAttrs);
  }

  function restore(root) {
    walk(root, function (n) { if (ORIG.has(n)) n.nodeValue = ORIG.get(n); });
    if (root.querySelectorAll) root.querySelectorAll("*").forEach(function (el) {
      const store = ORIG_ATTR.get(el);
      if (store) Object.keys(store).forEach(function (a) { el.setAttribute(a, store[a]); });
    });
  }

  function apply(root) {
    if (lang === "en") walk(root || document.body, translateTextNode);
    else if (root && root !== document.body) restore(root);
  }

  let observer = null;
  function startObserver() {
    if (observer) return;
    observer = new MutationObserver(function (muts) {
      if (lang !== "en") return;
      muts.forEach(function (m) {
        m.addedNodes && m.addedNodes.forEach(function (n) { apply(n); });
        if (m.type === "characterData" && m.target) translateTextNode(m.target);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  function setLang(next, opts) {
    lang = next === "en" ? "en" : "zh";
    localStorage.setItem(LANG_KEY, lang);
    document.documentElement.setAttribute("lang", lang === "en" ? "en" : "zh-CN");
    if (lang === "en") { apply(document.body); startObserver(); }
    else { if (observer) { observer.disconnect(); observer = null; } restore(document.body); }
    document.querySelectorAll("[data-lang-btn]").forEach(function (b) {
      b.textContent = lang === "en" ? "中文" : "EN";
      b.title = lang === "en" ? "切换到中文" : "Switch to English";
    });
    // 启动时应用已保存的语言属于初始化，不派发事件——
    // 否则 app.js 的重渲染回调会先于 boot() 取到令牌而触发 401 误判
    if (!(opts && opts.silent)) {
      document.dispatchEvent(new CustomEvent("om-lang-change", { detail: { lang: lang } }));
    }
  }

  window.t = t;
  window.OM_I18N = { t: t, setLang: setLang, apply: apply, getLang: function () { return lang; }, DICT: DICT };

  function boot() {
    document.querySelectorAll("[data-lang-btn]").forEach(function (b) {
      b.addEventListener("click", function () { setLang(lang === "en" ? "zh" : "en"); });
    });
    if (lang === "en") setLang("en", { silent: true });
    else setLang("zh", { silent: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
