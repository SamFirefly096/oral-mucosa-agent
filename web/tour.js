/* 颐鉴 · 新手教程（引导式步骤）
 * 6 步：选择患者 → 开始问诊 → 问诊对话 → 申请检查 → 结束问诊 → 填写诊断并提交
 * · 目标元素不可见时（如尚未开始问诊）自动改为居中卡片说明，不报错
 * · 文案走 i18n（window.t），中英文界面均可用
 * · 首次访问自动展示一次（localStorage.om_tour_done），顶部「教程」按钮可随时重看
 */
(function () {
  const STEPS = [
    { sel: "#caseBar", title: "① 选择患者", body: "在病例下拉框中选择一位患者，或点「随机」由系统抽取一例。训练模式下不会显示诊断，需要你自己问出来。" },
    { sel: "#startBtn", title: "② 开始问诊", body: "选定病例后点「开始问诊」，患者 Agent 会先给出主诉，随后由你主导问诊。" },
    { sel: "#chatArea", title: "③ 问诊对话", body: "在底部输入框提问并点「发送」。患者会用日常口语回答，可能跑题、记不清或带情绪——这正是真实门诊的样子。" },
    { sel: "#examBar", fallback: "#chatArea", note: "工具箱会在「开始问诊」后出现在对话区上方。", title: "④ 申请检查", body: "需要客观依据时，用工具箱申请口腔检查、化验、微生物、病理或中医四诊。没做过的检查会明确回复「未行该检验或检查」。" },
    { sel: "#endBtn", note: "「结束问诊」按钮只在问诊进行中出现——开始问诊后，它会出现在顶部状态栏右侧。", title: "⑤ 结束问诊", body: "问诊充分后点「结束问诊」，系统结束对话并开放诊断评估面板。" },
    { sel: "#scorePanel", note: "诊断填写面板在点「结束问诊」后弹出，包含西医诊断 / 中医辨证 / 治疗方案三项。", title: "⑥ 填写诊断并提交", body: "填写西医诊断、中医辨证与治疗方案，点「提交评分」即可获得评分、标准答案；训练模式下还可请「导师点评」。" },
  ];

  let idx = 0, els = null, target = null;

  function ensureDom() {
    if (els) return;
    const wrap = document.createElement("div");
    wrap.id = "omTour";
    wrap.innerHTML = [
      '<div class="omt-hole"></div>',
      '<div class="omt-card" role="dialog" aria-modal="true">',
      '  <div class="omt-head"><span class="omt-step"></span><span class="omt-title"></span></div>',
      '  <div class="omt-body"></div>',
      '  <div class="omt-note" style="display:none"></div>',
      '  <div class="omt-foot">',
      '    <label class="omt-skip-again"><input type="checkbox" id="omtNoMore"> <span data-omt="nomore"></span></label>',
      '    <span class="omt-spacer"></span>',
      '    <button class="omt-btn ghost" data-omt-act="skip"></button>',
      '    <button class="omt-btn ghost" data-omt-act="prev"></button>',
      '    <button class="omt-btn primary" data-omt-act="next"></button>',
      '  </div>',
      "</div>",
    ].join("");
    const style = document.createElement("style");
    style.textContent = `
      #omTour{position:fixed;inset:0;z-index:9998;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
      #omTour .omt-hole{position:absolute;border-radius:14px;box-shadow:0 0 0 9999px rgba(15,23,42,.55);transition:all .18s ease;pointer-events:none}
      #omTour .omt-card{position:absolute;max-width:min(92vw,380px);background:#fff;border-radius:16px;padding:16px 16px 12px;
        box-shadow:0 18px 50px rgba(2,6,23,.38);border:1px solid #e2e8f0;transition:all .18s ease;
        max-height:calc(100dvh - 20px);display:flex;flex-direction:column}
      #omTour .omt-body{overflow-y:auto;-webkit-overflow-scrolling:touch}
      #omTour .omt-note{margin-top:8px;padding:7px 10px;border-radius:9px;background:#fff7e6;border:1px solid #f0c36d;
        color:#8a5a00;font-size:11.5px;line-height:1.6}
      #omTour .omt-head{display:flex;align-items:center;gap:8px;margin-bottom:6px}
      #omTour .omt-step{background:#fee2e2;color:#A21A00;font-size:11px;font-weight:700;border-radius:999px;padding:2px 9px}
      #omTour .omt-title{font-size:15px;font-weight:700;color:#0f172a}
      #omTour .omt-body{font-size:13px;line-height:1.75;color:#475569}
      #omTour .omt-foot{display:flex;align-items:center;gap:8px;margin-top:14px;flex-wrap:wrap;flex-shrink:0}
      #omTour .omt-skip-again{display:flex;align-items:center;gap:5px;font-size:11px;color:#94a3b8}
      #omTour .omt-spacer{flex:1}
      #omTour .omt-btn{border:0;border-radius:10px;padding:7px 14px;font-size:13px;cursor:pointer}
      #omTour .omt-btn.ghost{background:#f1f5f9;color:#475569}
      #omTour .omt-btn.primary{background:linear-gradient(135deg,#A21A00,#c2410c);color:#fff;font-weight:600}
      #omTour .omt-btn[disabled]{opacity:.45;cursor:default}
      @media (max-width:420px){ #omTour .omt-card{left:8px!important;right:8px;max-width:none} }
    `;
    document.head.appendChild(style);
    document.body.appendChild(wrap);
    els = {
      wrap: wrap,
      hole: wrap.querySelector(".omt-hole"),
      card: wrap.querySelector(".omt-card"),
      step: wrap.querySelector(".omt-step"),
      title: wrap.querySelector(".omt-title"),
      body: wrap.querySelector(".omt-body"),
      note: wrap.querySelector(".omt-note"),
      noMore: wrap.querySelector("#omtNoMore"),
      nomoreLabel: wrap.querySelector('[data-omt="nomore"]'),
      skip: wrap.querySelector('[data-omt-act="skip"]'),
      prev: wrap.querySelector('[data-omt-act="prev"]'),
      next: wrap.querySelector('[data-omt-act="next"]'),
    };
    els.skip.addEventListener("click", function () { close(); });
    els.prev.addEventListener("click", function () { idx = Math.max(0, idx - 1); render(); });
    els.next.addEventListener("click", function () {
      if (idx >= STEPS.length - 1) { close(); return; }
      idx++; render();
    });
    els.wrap.addEventListener("click", function (e) { if (e.target === els.wrap) close(); });
    window.addEventListener("resize", function () { if (target) place(); });
    window.addEventListener("scroll", function () { if (target) place(); }, true);
  }

  function visible(el) {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return false;
    const st = getComputedStyle(el);
    return st.display !== "none" && st.visibility !== "hidden" && st.opacity !== "0";
  }

  function place() {
    if (!target) return;
    const r = target.getBoundingClientRect();
    const pad = 6;
    Object.assign(els.hole.style, {
      left: r.left - pad + "px", top: r.top - pad + "px",
      width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px",
      boxShadow: "0 0 0 9999px rgba(15,23,42,.55), 0 0 0 3px rgba(162,26,0,.85)",
    });
    const card = els.card, cw = card.offsetWidth, ch = card.offsetHeight;
    let top = r.bottom + 12, left = Math.min(Math.max(10, r.left), window.innerWidth - cw - 10);
    if (top + ch > window.innerHeight - 10) top = Math.max(10, r.top - ch - 12);
    top = Math.min(Math.max(10, top), Math.max(10, window.innerHeight - ch - 10));
    card.style.left = left + "px";
    card.style.top = top + "px";
    card.style.right = "auto";
  }

  function render() {
    ensureDom();
    const s = STEPS[idx];
    els.step.textContent = (idx + 1) + " / " + STEPS.length;
    els.title.textContent = window.t ? t(s.title) : s.title;
    els.body.textContent = window.t ? t(s.body) : s.body;
    els.nomoreLabel.textContent = window.t ? t("不再提示") : "不再提示";
    els.skip.textContent = window.t ? t("跳过教程") : "跳过教程";
    els.prev.textContent = window.t ? t("上一步") : "上一步";
    els.next.textContent = idx === STEPS.length - 1
      ? (window.t ? t("开始使用") : "开始使用")
      : (window.t ? t("下一步") : "下一步");
    els.prev.disabled = idx === 0;
    // 主目标不可见时用 fallback（例如尚未开始问诊时工具箱/结束按钮还不存在）
    let el = document.querySelector(s.sel);
    let usedFallback = false;
    if (!visible(el) && s.fallback) {
      const fb = document.querySelector(s.fallback);
      if (visible(fb)) { el = fb; usedFallback = true; }
    }
    els.note.style.display = "none";
    if (!visible(document.querySelector(s.sel)) && s.note) {
      els.note.textContent = window.t ? t(s.note) : s.note;
      els.note.style.display = "block";
    }
    if (visible(el)) {
      target = el;
      els.hole.style.display = "block";
      els.card.style.transform = "none";
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      setTimeout(place, 260);
      place();
    } else {
      target = null;                       // 目标尚未出现（如未开始问诊）→ 居中展示
      els.hole.style.display = "none";
      Object.assign(els.card.style, { left: "50%", top: "50%", transform: "translate(-50%,-50%)" });
    }
  }

  function start(force) {
    idx = 0; ensureDom(); els.wrap.style.display = "block";
    render();
    if (force) els.noMore.checked = false;
  }

  function close() {
    if (!els) return;
    els.wrap.style.display = "none";
    if (els.noMore.checked) localStorage.setItem("om_tour_done", "1");
    else if (localStorage.getItem("om_tour_done") === "1") localStorage.setItem("om_tour_done", "1");
  }

  window.OM_TOUR = { start: function () { start(true); }, close: close };

  function maybeAuto() {
    if (localStorage.getItem("om_tour_done") === "1") return;
    if (!document.querySelector(".tabs")) return;      // 仅主界面
    setTimeout(function () { start(false); localStorage.setItem("om_tour_done", "1"); }, 900);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", maybeAuto);
  else maybeAuto();

  document.addEventListener("om-lang-change", function () { if (els && els.wrap.style.display === "block") render(); });
})();
