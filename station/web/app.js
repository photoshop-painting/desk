/* ایستگاه تصمیم مشتقه — منطق رابط گرافیکی مرورگری محلی */
"use strict";

const STEPS = [
  ["health", "خوش‌آمد و پنل مدیریت"],
  ["data", "منبع داده"],
  ["settings", "تنظیمات ریاضی و ریسک"],
  ["news", "خبر و هشدار"],
  ["run", "اجرا و محاسبه"],
  ["decide", "نتیجه و تصمیم"],
  ["backtest", "پس‌آزمایی روی تاریخ"],
  ["bundle", "بستهٔ تحویل شرکت"],
  ["trial", "آزمون زنده و دفتر سرمایه‌گذار"],
  ["blind", "آزمون کور سرمایه‌گذار"],
  ["math", "راهبردها و ریاضیِ پول"],
];
window.STEPS = STEPS;

const RULE_LABELS = {
  capital: "سرمایه (ریال)",
  hurdle: "نرخ سد سالانه (اعشار، مثلاً 0.39)",
  min_edge_arbitrage_pct: "کف حاشیهٔ آربیتراژ (واحد درصد)",
  min_edge_leveraged_pct: "کف حاشیهٔ اهرمی (واحد درصد)",
  max_margin_pct: "سقف کل وجه تضمین (اعشار)",
  max_position_pct: "سقف هر موقعیت از بودجه (اعشار)",
  max_positions: "حداکثر موقعیت هم‌زمان",
  min_liquidity_contracts_per_day: "کف نقدشوندگی (قرارداد در روز)",
  max_spread_pct: "سقف اسپرد (اعشار، مثلاً 0.03)",
  max_plausible_arb_pct: "سقف باورپذیری بازدهٔ آربیتراژ (درصد)",
  max_plausible_lev_pct: "سقف باورپذیری بازدهٔ اهرمی (درصد)",
};

let current = 0;
let rules = {};
let signals = [];
let selectedSid = null;
let packetText = "";

function el(id) { return document.getElementById(id); }

function logTo(id, text) {
  const box = el(id);
  if (!box) return;
  box.textContent += "\n" + text;
  box.scrollTop = box.scrollHeight;
}

function resetLog(id, text) { const box = el(id); if (box) box.textContent = text; }

async function api(path, options) {
  const res = await fetch(path, options);
  if (res.status === 401) {                       // دروازه: نشست بسته شده است
    const back = encodeURIComponent(location.pathname + location.search);
    location.href = "/login?next=" + back;
    return { error: "نشست بسته شد؛ دوباره وارد شوید." };
  }
  const text = await res.text();
  try { return JSON.parse(text); } catch (e) { return { error: text || ("HTTP " + res.status) }; }
}

function busy(id, on) {
  const pct = arguments.length > 2 ? arguments[2] : undefined;
  const b = el(id); if (!b) return;
  b.classList.toggle("on", !!on);
  // جلوگیری از کلیکِ دوبارهٔ حینِ عملیات (UX-guideline #32): دکمهٔ هم‌ردیف غیرفعال شود
  let sib = b.previousElementSibling, n = 0;
  while (sib && n < 3) {
    if (sib.tagName === "BUTTON") { sib.disabled = !!on; break; }
    sib = sib.previousElementSibling; n++;
  }
  // vibefarsi progress — هر busy یک نوار پیشرفت راست‌به‌چپ همراهش دارد
  try {
    let prog = null;
    // جست‌وجوی progress هم‌ردیف (بعد یا قبل از busy)
    let nxt = b.nextElementSibling;
    if (nxt && nxt.classList && nxt.classList.contains("progress")) prog = nxt;
    else if (nxt && nxt.querySelector && nxt.querySelector(".progress")) prog = nxt.querySelector(".progress");
    else {
      let prv = b.previousElementSibling;
      if (prv && prv.classList && prv.classList.contains("progress")) prog = prv;
    }
    // اگر progress کناری نبود، خودِ busy را به‌عنوان ظرف در نظر نگیر؛ فقط اگر pct داده شد، Toastِ پیشرفت را بسازیم
    if (prog) {
      prog.style.display = on ? "block" : "none";
      if (typeof pct === "number") setProgress(prog, pct);
      else if (on) setProgress(prog, 72);
    }
  } catch(e){}
}

/* vibefarsi progress helpers — fill از راست + درصد فارسی */
function setProgress(progOrId, pct) {
  const prog = typeof progOrId === "string" ? el(progOrId) : progOrId;
  if (!prog || !prog.classList || !prog.classList.contains("progress")) return;
  const v = Math.max(0, Math.min(100, Number(pct)||0));
  prog.setAttribute("aria-valuenow", String(v));
  const fill = prog.querySelector(".progress-fill");
  if (fill) fill.style.width = v + "%";
  const label = prog.querySelector(".progress-label");
  if (label) label.textContent = v.toLocaleString("fa-IR") + "٪";
}
function ensureProgressNear(busyId, initialPct) {
  const b = el(busyId); if (!b) return null;
  let prog = b.nextElementSibling;
  if (prog && prog.classList && prog.classList.contains("progress")) return prog;
  // بساز اگر نبود (خودکفای آفلاین)
  prog = document.createElement("div");
  prog.className = "progress";
  prog.setAttribute("role", "progressbar");
  prog.setAttribute("aria-valuemin", "0");
  prog.setAttribute("aria-valuemax", "100");
  prog.setAttribute("aria-valuenow", String(initialPct||0));
  prog.setAttribute("aria-label", "پیشرفت عملیات");
  prog.style.display = "none";
  prog.style.marginTop = "8px";
  prog.innerHTML = '<div class="progress-fill" style="width:'+(initialPct||0)+'%"></div><span class="progress-label">'+(Number(initialPct||0).toLocaleString("fa-IR"))+'٪</span>';
  b.insertAdjacentElement("afterend", prog);
  return prog;
}

/* vibefarsi toast — Provider + سقف ۴ + بستن همه + جایگاه قابل‌تنظیم (پایین-راست) — offline */
const Toast = (() => {
  const MAX = 4;
  function stackEl(){ return el("toast-stack"); }
  function faTime(d){
    try { return d.toLocaleTimeString("fa-IR", {hour:"2-digit", minute:"2-digit"}); } catch(e){ return ""; }
  }
  function show(kind, title, msg, opts={}) {
    const s = stackEl(); if (!s) return;
    // سقفِ تعداد: قدیمی‌ترین را بردار
    while (s.children.length >= MAX) s.removeChild(s.firstChild);
    const wrap = document.createElement("div");
    wrap.className = "toast toast-" + (kind||"info");
    wrap.setAttribute("role", "status");
    wrap.setAttribute("aria-live", "polite");
    const safeTitle = String(title||"").replace(/</g,"&lt;");
    const safeMsg = String(msg||"").replace(/</g,"&lt;");
    const time = faTime(new Date());
    wrap.innerHTML = '<div style="flex:1;min-width:0"><div class="t-title">'+safeTitle+'</div>'
      + (safeMsg ? '<div class="t-msg">'+safeMsg+'</div>' : '')
      + '<div class="t-time">'+time+' · <span class="badge-soft '+(kind==="success"?"ok":kind==="error"?"bad":kind==="warning"?"warn":"")+'">'+(kind==="success"?"موفق":kind==="error"?"خطا":kind==="warning"?"هشدار":"اطلاع")+'</span></div>'
      + (opts.actionLabel ? '<div class="toast-actions"><button onclick="this.closest(\'.toast\').remove();Toast.clearCheck()">'+opts.actionLabel+'</button></div>' : '')
      + '</div><button class="t-close" aria-label="بستن" onclick="this.closest(\'.toast\').remove();Toast.clearCheck()">×</button>';
    s.appendChild(wrap);
    // نمایش دکمهٔ بستن همه وقتی ≥۲
    clearCheck();
    const ttl = kind === "error" ? 7000 : 4200;
    setTimeout(()=>{ wrap.style.transition="opacity .22s"; wrap.style.opacity="0"; setTimeout(()=>{ if(wrap.parentNode) wrap.remove(); clearCheck(); }, 220); }, ttl);
    return wrap;
  }
  function clearCheck(){
    const s = stackEl(); if(!s) return;
    let btn = document.getElementById("toast-clear-all");
    if (s.children.length >= 2) {
      if (!btn) {
        btn = document.createElement("button");
        btn.id = "toast-clear-all";
        btn.textContent = "بستن همه";
        btn.style.cssText = "pointer-events:auto;margin-top:4px;align-self:flex-end;font-size:12px;padding:4px 10px;border-radius:8px;border:1px solid #dbe2ea;background:#fff;cursor:pointer;";
        btn.onclick = () => clearAll();
        s.appendChild(btn);
      }
    } else {
      if (btn) btn.remove();
    }
  }
  function clearAll(){ const s = stackEl(); if(s) s.innerHTML=""; }
  return {
    show,
    success:(t,m,o)=>show("success",t,m,o),
    error:(t,m,o)=>show("error",t,m,o),
    warning:(t,m,o)=>show("warning",t,m,o),
    info:(t,m,o)=>show("info",t,m,o),
    clearAll, clearCheck,
    MAX
  };
})();
window.Toast = Toast;

/* vibefarsi Dialog helper — جایگزین confirm بومی با مودال آفلاین + بازگشت فوکوس */
async function askConfirm(message, opts){
  // در آزمون تعاملی jsdom: window.confirm stub شده است (()=>true) تا بدون کلیک بگذرد؛
  // اگر confirm غیربومی است، همان را بگذار بگذرد تا آزمون قفل نشود.
  try {
    const c = window.confirm;
    if (c && String(c).indexOf("[native code]") === -1) {
      try { return !!c(message); } catch(e) {}
    }
  } catch(e) {}
  try {
    if (window.Dialog && typeof window.Dialog.confirm === "function") {
      const r = await window.Dialog.confirm({
        title: (opts && opts.title) || "تأیید کنید",
        message: message,
        confirmText: (opts && opts.confirmText) || "تأیید",
        cancelText: (opts && opts.cancelText) || "انصراف"
      });
      return !!r;
    }
  } catch(e) {}
  return confirm(message);
}

window.setProgress = setProgress;
window.ensureProgressNear = ensureProgressNear;
window.askConfirm = askConfirm;



/* ---------------- گام ۱۱: راهبردها، شوک‌آزمون و ریاضی پول ---------------- */
function faNum(x, digits) {
  const n = Number(x);
  if (!isFinite(n)) return "—";
  return n.toLocaleString("fa-IR", { maximumFractionDigits: digits === undefined ? 3 : digits });
}

function esc(v) {
  return String(v === null || v === undefined ? "" : v)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function table(headers, rows) {
  const th = headers.map((h) => `<th>${esc(h)}</th>`).join("");
  const tr = rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("");
  return `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
}

async function buildStrategies() {
  busy("busy-strategies", true);
  const res = await api("/api/strategies/sheet", { method: "POST", body: "{}" });
  busy("busy-strategies", false);
  if (res.error) { resetLog("strategy-table", "خطا: " + res.error); return; }
  const rows = (res.table || []).map((t) => [esc(t.name), esc(t.class), esc(t.value),
    `<span class="hint">${esc(t.method)}</span>`,
    t.resilience === null || t.resilience === undefined ? "—" : faNum(t.resilience, 0) + "٪"]);
  let html = table(["راهبرد", "دسته", "عدد امروز", "روش عدد", "تاب‌آوری"], rows);
  const sr = (res.stress_rows || []).map((r) => [esc(r.title),
    r.annualized_pct === null ? "—" : faNum(r.annualized_pct) + "٪",
    r.survives_today ? "می‌ماند ✅" : "می‌افتد ❌",
    faNum(r.resilience_pct, 0) + "٪",
    esc(r.first_failure || "— سخت‌جان"),
    r.neutral_matches_engine ? "موتور ✅" : "ناهم‌خوان ⚠️"]);
  html += `<p class="hint">شوک‌آزمون — ${esc((res.counts && res.counts.checked) || 0)} ردیف بررسی شد؛
    سخت‌جان: ${esc((res.solid || []).join("، ") || "—")} · لبِ مرز: ${esc((res.marginal || []).join("، ") || "—")}
    · افتاده: ${esc((res.dead || []).join("، ") || "—")}</p>`;
  html += table(["راهبرد", "بازده امروز", "می‌ماند؟", "تاب‌آوری", "اولین شوک", "حالت خنثی = موتور؟"], sr);
  html += `<p class="hint">${esc(res.honesty || "")}</p>`;
  el("strategy-table").innerHTML = html;
}

async function buildStress() {
  const res = await api("/api/edge-stress/sheet", { method: "POST", body: "{}" });
  if (res.error) { resetLog("stress-table", "خطا: " + res.error); return; }
  const rows = (res.rows || []).map((r) => [esc(r.title),
    r.annualized_pct === null ? "—" : faNum(r.annualized_pct) + "٪",
    r.survives_today ? "می‌ماند ✅" : "می‌افتد ❌",
    faNum(r.resilience_pct, 0) + "٪", esc(r.first_failure || "— سخت‌جان"),
    esc(r.fee_tolerance || "")]);
  el("stress-table").innerHTML = table(["راهبرد", "بازده امروز", "می‌ماند؟", "تاب‌آوری",
    "اولین شوک", "تحمل کارمزد"], rows);
}

async function buildBankroll() {
  busy("busy-bankroll", true);
  const _pa = (window.parseAmountFloat || window.parseAmount || ((s)=> Number(String(s).replace(/[^0-9.-]/g,"")) || 0));
  const _pi = (window.parseAmount || ((s)=> Number(String(s).replace(/[^0-9]/g,"")) || 0));
  const body = JSON.stringify({
    capital: _pi(el("bk-capital").value || 0) || undefined,
    target: _pi(el("bk-target").value || 0) || undefined,
    win_prob: _pa(el("bk-winprob").value || 0) || undefined,
    win_pct: _pa(el("bk-win").value || 0) || undefined,
    loss_pct: _pa(el("bk-loss").value || 0) || undefined,
    strategy_pct: _pa(el("bk-strategy").value || 0) || undefined,
    churn: _pa(el("bk-churn").value || 0) || undefined,
  });
  const res = await api("/api/bankroll/sheet", { method: "POST", body });
  busy("busy-bankroll", false);
  if (res.error) { resetLog("bankroll-box", "خطا: " + res.error); return; }
  const k = res.kelly || {}, s = res.sim || {}, p = res.path || {}, sp = res.strategy_path || {};
  let html = `<p><b>اندازهٔ درست هر معامله:</b> کِلی ${faNum(k.kelly_fraction)} ·
    نصف‌کِلی (محافظه‌کارانه) ${faNum(k.half_kelly_fraction)} · مزیت هر معامله
    ${faNum(k.edge_pct_per_trade, 3)}٪</p>`;
  html += `<p><b>کم‌ترین نرخ برد لازم:</b> ${faNum((res.breakeven || {}).breakeven_win_pct, 2)}٪ —
    زیر این عدد، هر راهبردی بازنده است.</p>`;
  html += table(["شبیه‌سازی (فرضی)", "عدد"], [
    ["احتمال نیم‌شدن حساب", faNum(s.ruin_prob) + " ‏(" + faNum(100 * (s.ruin_prob || 0), 2) + "٪)"],
    ["احتمال دوبرابر‌شدن", faNum(100 * (s.double_prob || 0), 2) + "٪"],
    ["احتمال سود", faNum(100 * (s.profit_prob || 0), 2) + "٪"],
    ["میانهٔ پایان", faNum(s.median_final, 0) + " (" + faNum(s.median_multiple) + "× شروع)"],
    ["بازهٔ ۱۰٪ تا ۹۰٪", faNum(s.p10_final, 0) + " تا " + faNum(s.p90_final, 0)],
    ["مسیر کِلی (مدل فرضی)", esc(p.detail || "")],
    ["مسیر راهبرد", esc(sp.detail || "")],
  ]);
  html += `<p class="hint">${esc(res.honesty || "")}</p>`;
  el("bankroll-box").innerHTML = html;
}

/* ---------------- ناوبری ---------------- */
function buildNav() {
  const nav = el("nav");
  STEPS.forEach((s, i) => {
    const row = document.createElement("div");
    row.className = "nav-row";
    const a = document.createElement("a");
    a.href = "#";
    a.id = "nav-" + s[0];
    a.innerHTML = `<span class="n">${i + 1}</span>${s[1]}`;
    a.onclick = (e) => { e.preventDefault(); showStep(i); };
    const q = document.createElement("button");
    q.type = "button";
    q.className = "nav-q";
    q.title = "راهنمای این گام — صفحه و همهٔ پارامترهایش";
    q.textContent = "؟";
    q.onclick = () => openHelp("s-" + s[0]);
    row.appendChild(a);
    row.appendChild(q);
    nav.appendChild(row);
  });
  // گام‌های ۷ تا آخر «اثبات برنامه»‌اند (برای سرمایه‌گر/کارفرما)، نه کارِ روزانهٔ کارفرما:
  // زیرِ آن‌ها یک خط جداکنندهٔ روشن می‌روید تا جریانِ واجب (گام‌های ۱ تا ۶) دیده شود.
  if (STEPS.length >= 7 && nav.children[7]) {
    const row = document.createElement("div");
    row.className = "nav-row nav-sep";
    const sep = document.createElement("h2");
    sep.textContent = "اثباتِ برنامه (اختیاری)";
    const q = document.createElement("button");
    q.type = "button";
    q.className = "nav-q";
    q.title = "این گروه چه است و هر گامش چه کار درمی‌آید";
    q.textContent = "؟";
    q.onclick = () => openHelp("proof");
    row.appendChild(sep);
    row.appendChild(q);
    nav.insertBefore(row, nav.children[7]);
  }
}

function showStep(i) {
  current = Math.max(0, Math.min(i, STEPS.length - 1));
  STEPS.forEach((s, idx) => {
    const sec = el("s-" + s[0]);
    if (sec) sec.classList.toggle("active", idx === current);
    const a = el("nav-" + s[0]);
    if (a) a.classList.toggle("active", idx === current);
  });
}
window.showStep = showStep;

function go(delta) { showStep(current + delta); }

/* ---------------- گام ۱: سلامت ---------------- */

/* ---------------- گام ۲: داده ---------------- */
function modeNow() { return document.querySelector('input[name=mode]:checked').value; }

async function pickMode() {
  const mode = modeNow();
  const cards = { sim: 0, file: 0, live: 0 };
  const data = await api("/api/mode-info?mode=" + mode);
  if (!data.error) {
    el("mode-text").innerHTML = `<b>انتخاب شما:</b> ${data.label}<br><b>هزینه:</b> ${data.cost}<br>` +
      `<b>چه می‌دهد:</b> ${data.gives}<br><b>پس از اتصال چه تغییر می‌کند:</b> ${data.after}<br><b>چگونه:</b> ${data.how}`;
    cards.sim = cards.file = cards.live = 1;
  }
  el("card-file").style.display = (mode === "sim") ? "none" : "block";
  el("card-live").style.display = (mode === "live") ? "block" : "none";
  await api("/api/mode", { method: "POST", headers: { "Content-Type": "application/json" },
                           body: JSON.stringify({ mode }) });
}

async function loadGuide() {
  const data = await api("/api/data-guide");
  if (data.error) return;
  el("api-guide").innerHTML = data.rows.map((r) =>
    `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td class="hint">${r[3]}</td><td class="hint">${r[4]}</td></tr>`).join("");
  if (data.snapshot_template) el("file-path").value = data.snapshot_template;
  if (data.history_template) el("hist-path").value = data.history_template;
  if (data.kodal_db) el("kodal-db").value = data.kodal_db;
}

async function makeTemplate() {
  const data = await api("/api/template", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ kind: "snapshot" }) });
  if (data.error) { logTo("log-data", "خطا: " + data.error); return; }
  el("file-path").value = data.path;
  logTo("log-data", "قالب اسنپ‌شات ساخته شد: " + data.path);
}

async function testData() {
  resetLog("log-data", "آزمایش خواندن پرونده…");
  const data = await api("/api/test-data", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify({ mode: modeNow(), file_path: el("file-path").value }) });
  (data.messages || []).forEach((m) => logTo("log-data", "· " + m));
  logTo("log-data", `وضعیت: ${data.status} · ردیف‌ها: ${data.rows} · تازگی: ${data.freshness}`);
  updateBadge(data.status, data.source_label, data.freshness, data.rows);
}

async function testLive() {
  resetLog("log-data", "آزمایش اتصال سرویس…");
  const cfg = { url_template: el("live-url").value, json_path: el("live-path").value,
                key_header: el("live-header").value, key_query_name: el("live-qname").value };
  const data = await api("/api/test-live", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify({ live_cfg: cfg, key: el("live-key").value,
                                                                    file_path: el("file-path").value }) });
  (data.messages || []).forEach((m) => logTo("log-data", "· " + m));
  logTo("log-data", `وضعیت: ${data.status} · تازگی: ${data.freshness} · ردیف: ${data.rows}`);
  if (data.status === "ok") logTo("log-data", "از این پس قیمت پایه از سرویس خوانده می‌شود و تازگی داده سبز می‌ماند.");
  else logTo("log-data", "راهنما: قالب نشانی و مسیر JSON را از مستندات فروشنده بردارید؛ اگر عدد در پاسخ تغییر کند، فقط همین دو خط را عوض کنید.");
  updateBadge(data.status, data.source_label, data.freshness, data.rows);
}

function updateBadge(status, label, freshness, rows) {
  const color = status === "ok" ? "#9ae6b4" : (status === "partial" ? "#ffe08a" : "#feb2b2");
  el("badge").textContent = `منبع: ${label || "—"} · تازگی: ${freshness || "—"} · ردیف: ${rows || 0}`;
  el("badge").style.color = color;
}

/* ---------------- گام ۳: تنظیمات ---------------- */
async function loadRules() {
  const data = await api("/api/state");
  rules = data.rules || {};
  el("rules-box").innerHTML = Object.keys(rules).map((k) =>{
    let val = rules[k];
    try{
      if (k==="capital" && window.formatAmount) val = window.formatAmount(val);
      else if (typeof val === "number" && window.formatAmount && k!=="capital") {
        // keep original for non-amount
      }
    }catch(e){}
    return `<div><label>${RULE_LABELS[k] || k}</label><input type="text" id="rule-${k}" value="${val}"></div>`;
  }).join("");
  try{ if(window.attachAmountInputs) setTimeout(window.attachAmountInputs, 50); }catch(e){}
}

async function saveRules() {
  const out = {};
  const _pa = (window.parseAmountFloat || window.parseAmount || ((s)=> Number(String(s).replace(/[^0-9.-]/g,"")) || 0));
  Object.keys(rules).forEach((k) => { 
    const raw = el("rule-" + k).value.trim();
    // capital-like fields are amounts; others are percentages/decimals
    const isAmount = (k==="capital" || k.indexOf("capital")!==-1);
    const v = isAmount ? String(_pa(raw)) : raw;
    out[k] = isNaN(v) ? v : Number(v); 
    // for amount fields, try parseAmount first
    if (isAmount) out[k] = _pa(raw);
  });
  const data = await api("/api/rules", { method: "POST", headers: { "Content-Type": "application/json" },
                                         body: JSON.stringify(out) });
  resetLog("log-settings", data.error ? ("خطا: " + data.error) : ("ذخیره شد: " + JSON.stringify(data.rules)));
  rules = data.rules || rules;
  try{ if(data.error) Toast.error("ذخیره نشد", data.error); else Toast.success("تنظیمات ذخیره شد", "قواعد ریاضی به‌روز شد"); }catch(e){}
}

/* ---------------- گام ۴: خبر ---------------- */
async function runKodalDemo() {
  resetLog("log-news", "اجرای دیده‌بان روی دادهٔ نمونه…");
  const data = await api("/api/kodal/demo", { method: "POST" });
  (data.items || []).forEach((it) => logTo("log-news", `[${it.score}] ${it.direction} · ${it.category} · ${it.symbol || "-"} · ${it.title}`));
  if (data.kodal_db) el("kodal-db").value = data.kodal_db;
  logTo("log-news", `${(data.items || []).length} هشدار ساخته و ثبت شد.`);
}

async function showAlerts() {
  const data = await api("/api/alerts?db=" + encodeURIComponent(el("kodal-db").value));
  resetLog("log-news", "هشدارهای فعلی:");
  (data.items || []).forEach((a) => logTo("log-news", `[${a.score}] ${a.direction} · ${a.category} · ${a.symbol || "-"} · ${a.title}`));
  if (!(data.items || []).length) logTo("log-news", "هشداری نیست یا پایگاه‌داده خالی است.");
}

/* ---------------- گام ۵: اجرا ---------------- */
async function doRun() {
  resetLog("log-run", "شروع محاسبه…");
  busy("busy-run", true);
  const payload = { mode: modeNow(), file_path: el("file-path").value, key: el("live-key").value,
                    live_cfg: { url_template: el("live-url").value, json_path: el("live-path").value,
                                key_header: el("live-header").value, key_query_name: el("live-qname").value },
                    use_kodal: el("use-kodal").checked, kodal_db: el("kodal-db").value, rules };
  const data = await api("/api/run", { method: "POST", headers: { "Content-Type": "application/json" },
                                       body: JSON.stringify(payload) });
  busy("busy-run", false);
  if (data.error) { logTo("log-run", "خطا: " + data.error); try{Toast.error("خطا در محاسبه", data.error);}catch(e){} return; }
  (data.messages || []).forEach((m) => logTo("log-run", "· " + m));
  const c = data.counts || {};
  el("run-kpis").innerHTML = [
    ["کل سیگنال", c.total], ["منتظر تأیید", c.pending], ["تأییدشده", c.approved], ["رد شده", c.rejected],
    ["کار بازبینی", c.tasks], ["سرمایهٔ درگیر (ریال)", (c.locked || 0).toLocaleString("fa-IR")],
  ].map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  (data.signals || []).forEach((s) => {
    logTo("log-run", `${s.mark} ${s.symbol} · ${s.kind_label} · بازده ${s.annualized} · حاشیه ${s.edge} · ${s.size}`);
    if (s.status === "rejected" && s.gate_note) logTo("log-run", "     دلیل رد: " + s.gate_note);
    (s.alerts || []).slice(0, 2).forEach((a) => logTo("log-run", `     خبر: [${a.score}] ${a.title}`));
  });
  (data.tasks || []).forEach((t) => logTo("log-run", `کار بازبینی: ${t.symbol} — ${t.reason}`));
  updateBadge(data.status, data.source_label, data.freshness, data.rows);
  logTo("log-run", "داشبورد به‌روز شد؛ از دکمهٔ «نمایش داشبورد» ببینید.");
  try{ const c2=data.counts||{}; Toast.success("محاسبه تمام شد", (c2.total||0).toLocaleString("fa-IR")+" سیگنال · "+(c2.pending||0).toLocaleString("fa-IR")+" منتظر تأیید"); }catch(e){}
  await loadSignals();
}

/* ---------------- گام ۶: تصمیم ---------------- */
async function loadSignals() {
  const data = await api("/api/signals");
  signals = data.signals || [];
  const body = document.querySelector("#signals-table tbody");
  body.innerHTML = signals.map((s) => `<tr onclick="selectSignal('${s.sid}')" style="cursor:pointer">
      <td class="hint">${s.sid}</td><td>${s.symbol}</td><td>${s.kind_label}</td>
      <td class="num">${s.annualized}</td><td class="num">${s.edge}</td><td>${s.size}</td>
      <td class="num">${(s.margin_locked || 0).toLocaleString("fa-IR")}</td>
      <td><span class="pill ${s.status}">${s.status_label}</span></td>
      <td class="hint">${s.gate_note || ""}${(s.alerts || []).length ? " | خبر: " + s.alerts[0].title : ""}</td>
    </tr>`).join("") || `<tr><td colspan="9" class="hint">سیگنالی نیست؛ اول گام ۵ را اجرا کنید.</td></tr>`;
}

function selectSignal(sid) {
  selectedSid = sid;
  const s = signals.find((x) => x.sid === sid);
  if (!s) return;
  resetLog("log-decide", `— ${s.symbol} · ${s.kind_label} · وضعیت ${s.status_label}`);
  logTo("log-decide", "   جزئیات ریاضی: " + JSON.stringify(s.detail).slice(0, 400));
  (s.alerts || []).forEach((a) => logTo("log-decide", `   خبر: [${a.score}] ${a.title}`));
}

async function decide(action) {
  if (!selectedSid) { logTo("log-decide", "اول یک ردیف از جدول را انتخاب کنید."); return; }
  const data = await api("/api/decide", { method: "POST", headers: { "Content-Type": "application/json" },
                                          body: JSON.stringify({ sid: selectedSid, action,
                                                                 note: el("decide-note").value }) });
  if (data.error) { logTo("log-decide", "خطا: " + data.error); try{Toast.error("تصمیم ثبت نشد", data.error);}catch(e){} return; }
  if (data.blocked) {
    if (!(await askConfirm(data.message + "\n\nباز هم تأیید می‌کنید؟ (در دفتر با برچسب «رد سقف» ثبت می‌شود)", {title:"رد سقف ریسک — تأیید مجدد"}))) {
      logTo("log-decide", "تأیید نشد؛ سیگنال همان‌طور منتظر تأیید ماند.");
      return;
    }
    const forced = await api("/api/decide", { method: "POST", headers: { "Content-Type": "application/json" },
                                              body: JSON.stringify({ sid: selectedSid, action, force: true,
                                                                     note: (el("decide-note").value + " | تأیید با رد سقف ریسک") }) });
    if (forced.error) { logTo("log-decide", "خطا: " + forced.error); return; }
    /* پاسخ نخست «سقف رد شد» بود و بستهٔ سفارش نداشت؛ بسته را از همین تأییدِ رد‌سقف‌شده برمی‌داریم */
    data.packet = forced.packet || data.packet || "";
    logTo("log-decide", "یادآوری: این تأیید سقف ریسک را رد کرد؛ در دفتر با برچسب «رد سقف» ثبت شد.");
  }
  logTo("log-decide", (action === "approved" ? "تأیید شد: " : "رد شد: ") + selectedSid);
  try{ Toast.success(action==="approved"?"تأیید شد":"رد شد", selectedSid); }catch(e){}
  packetText = data.packet || "";
  if (packetText) {
    el("packet-card").style.display = "block";
    el("packet").textContent = packetText;
    logTo("log-decide", "بستهٔ سفارش بالا آمده؛ آن را در سامانهٔ کارگزاری خودتان اجرا کنید.");
  }
  await loadSignals();
}

function copyPacket() {
  navigator.clipboard.writeText(packetText).then(() => logTo("log-decide", "بستهٔ سفارش در حافظه کپی شد."),
                                                () => logTo("log-decide", "کپی نشد؛ متن را دستی انتخاب کنید."));
}

/* ---------------- گام ۷: پس‌آزمایی ---------------- */
async function makeHistTemplate() {
  const data = await api("/api/template", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ kind: "history" }) });
  if (data.path) { el("hist-path").value = data.path; logTo("log-bt", "قالب ستون‌ها ساخته شد: " + data.path); }
}

async function doBacktest() {
  resetLog("log-bt", "اجرای پس‌آزمایی…");
  busy("busy-bt", true);
  const data = await api("/api/backtest", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ path: el("hist-path").value, rules }) });
  busy("busy-bt", false);
  if (data.error) { logTo("log-bt", "خطا: " + data.error); try{Toast.error("پس‌آزمایی ناموفق", data.error);}catch(e){} return; }
  (data.problems || []).forEach((p) => logTo("log-bt", "· " + p));
  const s = data.summary || {};
  el("bt-kpis").innerHTML = [
    ["سطرها", s.rows], ["ورود", s.taken], ["رد", s.skipped],
    ["نرخ برد", s.hit_rate_pct == null ? "—" : s.hit_rate_pct.toFixed(1) + "٪"],
    ["خطای مثبت کاذب", s.false_positive_rate_pct == null ? "—" : s.false_positive_rate_pct.toFixed(1) + "٪"],
    ["فرصت از دست رفته", s.missed_opportunity_rate_pct == null ? "—" : s.missed_opportunity_rate_pct.toFixed(1) + "٪"],
    ["میانگین انتظاری", s.avg_expected_annualized_pct == null ? "—" : s.avg_expected_annualized_pct.toFixed(1) + "٪"],
    ["میانگین واقعی", s.avg_realized_annualized_pct == null ? "—" : s.avg_realized_annualized_pct.toFixed(1) + "٪"],
    ["خطای پیش‌بینی", s.avg_forecast_error_pp == null ? "—" : s.avg_forecast_error_pp.toFixed(1)],
    ["سرمایهٔ پایانی", s.final_equity == null ? "—" : s.final_equity.toLocaleString("fa-IR")],
  ].map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  logTo("log-bt", `نرخ برد ${s.hit_rate_pct?.toFixed(1)}٪ · خطای مثبت کاذب ${s.false_positive_rate_pct?.toFixed(1)}٪ · ` +
                  `خطای پیش‌بینی ${s.avg_forecast_error_pp?.toFixed(1)} واحد درصد`);
  if (s.avg_forecast_error_pp != null && s.avg_forecast_error_pp < 0) {
    logTo("log-bt", "درس: میانگین واقعی از انتظار کمتر است؛ یعنی موتور خوش‌بینانه است. کف حاشیه را بالا ببرید یا انتظار را کم کنید.");
  }
  if ((data.file || "").includes("demo")) logTo("log-bt", "هشدار: این پرونده نمونهٔ ساختگی است؛ برای ارائه به شرکت دادهٔ واقعی خودتان را بدهید.");
  try{ const s2=data.summary||{}; Toast.success("پس‌آزمایی تمام شد", (s2.taken||0).toLocaleString("fa-IR")+" ورود از "+(s2.rows||0).toLocaleString("fa-IR")+" سطر · نرخ برد "+(s2.hit_rate_pct==null?"—":s2.hit_rate_pct.toFixed(1)+"٪")); }catch(e){}
}

/* ---------------- گام ۸: بسته ---------------- */
async function doBundle() {
  resetLog("log-bundle", "ساخت بسته…");
  busy("busy-bundle", true);
  const data = await api("/api/bundle", { method: "POST" });
  busy("busy-bundle", false);
  if (data.error) { logTo("log-bundle", "خطا: " + data.error); try{Toast.error("ساخت بسته ناموفق", data.error);}catch(e){} return; }
  logTo("log-bundle", "بسته ساخته شد: " + data.path);
  el("bundle-list").innerHTML = `<table><thead><tr><th>پرونده</th><th>توضیح</th><th></th></tr></thead><tbody>` +
    (data.files || []).map((f) => `<tr><td>${f.file}</td><td class="hint">${f.desc}</td>
      <td><button onclick="openFile('${f.file}')">نمایش</button></td></tr>`).join("") + `</tbody></table>`;
  (data.files || []).forEach((f) => logTo("log-bundle", "  · " + f.file));
  logTo("log-bundle", "پیشنهاد ارائه: اول سند روش کار، بعد داشبورد، و در پایان چک‌لیست راستی‌آزمایی.");
  try{ Toast.success("بسته ساخته شد", (data.files||[]).length.toLocaleString("fa-IR")+" پرونده آمادهٔ تحویل"); }catch(e){}
}

/* ---------------- گام ۲: دفتر اتصال ---------------- */
let CONN = { profiles: [], selected: "", active: {} };

async function loadConnections() {
  const data = await api("/api/connections");
  if (data.error) return;
  CONN = data;
  const sel = el("conn-select");
  sel.innerHTML = (data.profiles || []).map((p) => {
    const star = p.name === data.selected ? "★ " : "";
    const tested = p.tested ? " · آزمون‌شده" : "";
    return `<option value="${p.name}">${star}${p.label} · ${p.cost}${tested}</option>`;
  }).join("");
  sel.value = data.selected || (data.profiles || [])[0]?.name || "";
  renderConnInfo();
  await loadProfile();
}

function renderConnInfo() {
  const p = (CONN.profiles || []).find((x) => x.name === el("conn-select").value) || {};
  const a = CONN.active || {};
  const ks = (CONN.key_status || {})[p.name] || {};
  el("conn-info").innerHTML =
    `<b>${p.label || "—"}</b> — هزینه: ${p.cost || "—"}<br>` +
    `<b>چه می‌دهد:</b> ${p.gives || "—"}<br>` +
    `<b>پس از اتصال چه تغییر می‌کند:</b> ${p.after || "—"}<br>` +
    `<b>چگونه:</b> ${p.steps || "—"}` +
    (p.note ? `<br><span class="hint">${p.note}</span>` : "") +
    `<br><span class="hint">وضعیت کلید: ${ks.has_key ? ks.where : "بدون کلید"} · ` +
    `${ks.env_key ? "متغیر محیطی: " + ks.env_key : "متغیر محیطی تنظیم نشده"} · ` +
    `فعال‌شده: ${a.label || "—"}</span>`;
  el("key-status").textContent = ks.stored ? "کلید این پروفایل روی رایانه ذخیره شده است." : "کلیدی ذخیره نشده است.";
}

async function loadProfile() {
  const name = el("conn-select").value;
  const p = (CONN.profiles || []).find((x) => x.name === name);
  if (!p) return;
  el("live-url").value = p.url_template || "";
  el("live-path").value = p.json_path || "";
  el("live-header").value = p.key_header || "";
  el("live-qname").value = p.key_query_name || "";
  el("conn-name").value = p.name;
  el("conn-label").value = p.label || "";
  el("conn-env").value = p.env_key || "";
  el("peek-url").value = p.url_template || "";
  renderConnInfo();
}

function currentConnectionForm() {
  return {
    name: (el("conn-name").value || el("conn-select").value || "custom").trim(),
    label: (el("conn-label").value || "").trim(),
    url_template: el("live-url").value.trim(),
    json_path: el("live-path").value.trim(),
    key_header: el("live-header").value.trim(),
    key_query_name: el("live-qname").value.trim(),
    env_key: (el("conn-env").value || "").trim(),
    cost: ((CONN.profiles || []).find((x) => x.name === el("conn-select").value) || {}).cost || "",
    tested: false,
  };
}

async function saveProfile() {
  const body = { profile: currentConnectionForm(), key: el("live-key").value,
                 save_key: el("save-key").checked, select: true };
  const data = await api("/api/connections/save", { method: "POST", headers: { "Content-Type": "application/json" },
                                                     body: JSON.stringify(body) });
  if (data.error) { logTo("log-data", "خطا: " + data.error); return; }
  logTo("log-data", `پروفایل «${data.profile.label || data.profile.name}» ذخیره و فعال شد.` +
        (el("save-key").checked ? " کلید هم روی همین رایانه ذخیره شد." : " کلید فقط در حافظه ماند."));
  await loadConnections();
}

async function saveAsNew() {
  el("conn-select").value = "";                      // تا نام تازه جای دیگری را عوض نکند
  await saveProfile();
  logTo("log-data", "اگر نام کوتاه را به یک نام تازه عوض کنید، یک پروفایل مستقل ساخته می‌شود.");
}

async function deleteProfile() {
  const name = el("conn-select").value;
  if (!(await askConfirm(`پروفایل «${name}» و کلید ذخیره‌شدهٔ آن پاک شود؟`, {title:"حذف پروفایل"}))) return;
  const data = await api("/api/connections/delete", { method: "POST", headers: { "Content-Type": "application/json" },
                                                      body: JSON.stringify({ name }) });
  logTo("log-data", data.error ? ("خطا: " + data.error) : `پروفایل ${name} پاک شد.`);
  await loadConnections();
}

async function saveKey() {
  const name = el("conn-name").value || el("conn-select").value;
  const data = await api("/api/connections/key", { method: "POST", headers: { "Content-Type": "application/json" },
                                                   body: JSON.stringify({ name, key: el("live-key").value,
                                                                          save: el("save-key").checked }) });
  if (data.error) { logTo("log-data", "خطا: " + data.error); return; }
  logTo("log-data", data.saved ? "کلید روی همین رایانه ذخیره شد (فقط برای همین کاربر)."
                               : "کلید فقط در حافظهٔ همین اجرا نگه داشته شد و ذخیره نشد.");
  await loadConnections();
}

async function testProfile() {
  resetLog("log-data", "آزمایش اتصال پروفایل…");
  const name = el("conn-select").value;
  const sel = await api("/api/connections/select", { method: "POST", headers: { "Content-Type": "application/json" },
                                                      body: JSON.stringify({ name, key: el("live-key").value }) });
  if (sel.error) { logTo("log-data", "خطا: " + sel.error); return; }
  if (sel.is_mock) logTo("log-data", "یادآوری: این خوراک ساختگی است (برای آزمایش و نمایش).");
  await testLive();
}

async function peekService() {
  const box = el("peek-result");
  box.innerHTML = "در حال خواندن پاسخ سرویس…";
  const data = await api("/api/peek", { method: "POST", headers: { "Content-Type": "application/json" },
                                        body: JSON.stringify({ url: el("peek-url").value, key: el("live-key").value,
                                                               key_header: el("live-header").value }) });
  if (data.error) { box.innerHTML = `<span class="bad">خطا: ${data.error}</span>`; return; }
  const rows = (data.paths || []).map((x) =>
    `<tr><td style="direction:ltr">${x.path}</td><td class="num">${x.value.toLocaleString("fa-IR")}</td>
      <td><button onclick="usePeekPath('${x.path}')">استفاده</button></td></tr>`).join("");
  box.innerHTML = `<b>پاسخ آمد (${data.bytes} بایت).</b> مسیرهای عددی پیدا‌شده:
    <table><thead><tr><th>مسیر</th><th class="num">مقدار</th><th></th></tr></thead><tbody>${rows ||
    '<tr><td colspan="3" class="hint">عدد قابل‌استفاده‌ای در پاسخ نبود؛ شاید پاسخ HTML است.</td></tr>'}</tbody></table>
    <details><summary>پیش‌نمایش پاسخ خام</summary><div class="log" style="direction:ltr">${(data.preview || "").replace(/</g, "&lt;")}</div></details>`;
}

function usePeekPath(path) {
  el("live-path").value = path;
  logTo("log-data", "مسیر JSON انتخاب شد: " + path + " — حالا «آزمایش اتصال» را بزنید.");
}

/* ---------------- گام ۹: دفتر آزمون زنده ---------------- */
async function loadTrial() {
  const data = await api("/api/trial");
  if (data.error) return;
  renderTrial(data);
}

function renderTrial(data) {
  const s = data.summary || {};
  renderScorecard(data.scorecard, data.runs);
  const fa = (x, nd = 2) => (x == null ? "—" : Number(x).toLocaleString("fa-IR", { maximumFractionDigits: nd }));
  el("trial-kpis").innerHTML = [
    ["ثبت‌ها", s.entries], ["بازسنجی‌شده", s.marked], ["بازسنجی‌نشده", s.unmarked],
    ["میانگین انتظار در ثبت (٪)", fa(s.avg_expected)],
    ["میانگین تغییر (واحد درصد)", fa(s.avg_delta_pp)],
    ["بهترین تغییر", fa(s.best_delta_pp)], ["بدترین تغییر", fa(s.worst_delta_pp)],
  ].map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const buckets = s.buckets || {};
  el("chain-status").innerHTML = `<b>وضعیت زنجیره:</b> ${s.chain_ok ? "✅ " : "✗ "}${s.chain_message || "—"}` +
    ` · <span class="hint">${Object.keys(buckets).map((k) => k + ": " + buckets[k]).join(" · ") || "بازسنجی‌ای ثبت نشده"}</span>`;
  const body = document.querySelector("#trial-table tbody");
  const rows = (data.entries || []).map((e) => {
    const d = e.delta_pp;
    const color = d == null ? "" : (d >= 1 ? "var(--ok)" : (d <= -1 ? "var(--bad)" : "var(--muted)"));
    return `<tr><td class="hint">${e.id}</td><td class="hint">${e.ts}</td><td>${e.symbol}</td>
      <td>${e.kind}</td><td>${e.decision}</td>
      <td class="num">${fa(e.expected)}</td><td class="num">${fa(e.expected_now)}</td>
      <td class="num" style="color:${color};font-weight:bold">${fa(d)}</td>
      <td>${e.status_now}</td><td class="hint">${e.source_label || "—"}</td>
      <td class="hint" style="direction:ltr;font-size:10.5px">${e.hash}</td></tr>`;
  }).join("");
  body.innerHTML = rows || `<tr><td colspan="11" class="hint">هنوز چیزی ثبت نشده است؛ از دکمهٔ بالا شروع کنید.</td></tr>`;
}

async function runDaily(conservative) {
  resetLog("log-trial", "اجرای مراسم امروز…");
  busy("busy-daily", true);
  const data = await api("/api/trial/daily", { method: "POST", headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify({ note: el("daily-note").value,
                                                                       add_span: conservative ? -2 : 0 }) });
  busy("busy-daily", false);
  if (data.error) { logTo("log-trial", "خطا: " + data.error); return; }
  (data.notes || []).forEach((m) => logTo("log-trial", "· " + m));
  const r = data.record || {};
  logTo("log-trial", `امروز ${r.date} · منبع: ${data.source_label || "—"} · ` +
        `ثبت ${r.recorded} · بازسنجی ${r.marked}`);
  if (data.synthetic) logTo("log-trial", "توجه: دادهٔ امروز ساختگی بود؛ برای ارائه به شرکت روزهای واقعی لازم است.");
  if (data.report) logTo("log-trial", "گزارش سرمایه‌گذار به‌روز شد: " + data.report);
  renderTrial(data.trial || {});
}

function renderScorecard(score, runs) {
  if (!score) return;
  const fa = (x) => (x == null ? "—" : String(x));
  el("score-kpis").innerHTML = [
    ["روزهای ثبت‌شده", score.days], ["روزهای واقعی (نه ساختگی)", score.real_days],
    ["اجراها", score.runs], ["ردیف‌های دفتر", score.entries], ["بازسنجی‌شده", score.marked],
    ["حرکت‌های معنادار", score.moved], ["فرصت بازتر", score.up], ["فرصت بسته", score.down],
  ].map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${fa(v)}</div></div>`).join("");
  el("score-verdict").innerHTML = (score.ready ? "✅ " : "⏳ ") + score.verdict;
  el("score-verdict").style.background = score.ready ? "#e7f6ec" : "";
  el("score-verdict").style.borderColor = score.ready ? "#b7e0c6" : "";
  document.querySelector("#score-table tbody").innerHTML = (score.criteria || []).map((c) => {
    const have = typeof c.have === "object" ? JSON.stringify(c.have) : c.have;
    const want = typeof c.want === "object" ? JSON.stringify(c.want) : c.want;
    return `<tr><td>${c.ok ? "✅" : "✗"}</td><td>${c.name}</td><td class="num">${have}</td>
      <td class="num">${want}</td><td class="hint">${c.hint}</td></tr>`;
  }).join("");
  el("runs-list").innerHTML = (runs || []).map((r) =>
    `${r.ts || ""} · ${r.mode || ""} · ${r.synthetic ? "ساختگی" : "واقعی"} · ثبت ${r.recorded} · ` +
    `بازسنجی ${r.marked}${r.note ? " · " + r.note : ""}`).join("<br>") || "—";
}

async function recordTrial(conservative) {
  resetLog("log-trial", "ثبت در دفتر…");
  const body = { note: el("trial-note").value, add_span: conservative ? -2 : 0 };
  const data = await api("/api/trial/record", { method: "POST", headers: { "Content-Type": "application/json" },
                                                body: JSON.stringify(body) });
  if (data.error) { logTo("log-trial", "خطا: " + data.error); return; }
  logTo("log-trial", `${data.saved} ردیف ثبت شد` + (data.skipped ? ` · ${data.skipped} ردیف تکراری رد شد.` : "."));
  renderTrial(data.trial || {});
}

async function markTrial() {
  resetLog("log-trial", "خواندن قیمت‌های تازه و بازسنجی…");
  busy("busy-trial", true);
  const data = await api("/api/trial/mark", { method: "POST", headers: { "Content-Type": "application/json" },
                                              body: JSON.stringify({}) });
  busy("busy-trial", false);
  if (data.error) { logTo("log-trial", "خطا: " + data.error); return; }
  logTo("log-trial", `${data.marked_now} ردیف با قیمت‌های امروز بازسنجی شد.`);
  Object.entries(data.now_map || {}).forEach(([sym, v]) =>
    logTo("log-trial", `   ${sym}: حاشیهٔ امروز ${v.expected_now == null ? "—" : Number(v.expected_now).toFixed(2)} · کف ${v.floor}`));
  logTo("log-trial", "یادآوری: عدد منفی یعنی فرصت بسته شده — این نشانهٔ درست‌کاری موتور است، نه خرابی آن.");
  renderTrial(data);
}

async function verifyChain() {
  const data = await api("/api/trial/verify", { method: "POST" });
  logTo("log-trial", (data.ok ? "✅ " : "✗ ") + data.message);
  await loadTrial();
}

async function makeTrialReport() {
  resetLog("log-trial", "ساخت گزارش…");
  const data = await api("/api/trial/report", { method: "POST" });
  if (data.error) { logTo("log-trial", "خطا: " + data.error); return; }
  logTo("log-trial", "گزارش ساخته شد: " + data.html);
  logTo("log-trial", "پروندهٔ CSV برای دفتر شرکت: " + data.csv);
  logTo("log-trial", "این دو پرونده را در بستهٔ تحویل شرکت هم می‌شود گذاشت.");
  renderTrial(data);
}

/* ---------------- آزمون ۱۰ دقیقه‌ای و پروندهٔ سرمایه‌گذار ---------------- */
async function runSelftest() {
  resetLog("log-trial", "اجرای آزمون ۱۰ دقیقه‌ای…");
  busy("busy-exam", true);
  const data = await api("/api/selftest", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({}) });
  busy("busy-exam", false);
  if (data.error) { logTo("log-trial", "خطا: " + data.error); return; }
  renderSelftest(data);
  const s = data.summary || {};
  logTo("log-trial", `نتیجه: ${s.passed} از ${s.total} مورد سبز · موتور ${data.engine ? data.engine.version : "?"} ` +
                     `(اثر انگشت ${data.engine ? data.engine.sha256 : "?"}) · ${data.duration_ms} میلی‌ثانیه`);
  if (!s.ok) logTo("log-trial", "کارنامه سرخ است؛ موردهای سرخ را پیش از نمایش به سرمایه‌گذار حل کنید.");
  logTo("log-trial", "کارنامه و برگهٔ آزمون ساخته شد؛ با دکمه‌های بالای همین کارت بازشان کنید.");
}

function renderSelftest(data) {
  const s = data.summary || {};
  const fa = (x) => (x == null ? "—" : String(x));
  el("exam-kpis").innerHTML = [
    ["مورد سبز", `${fa(s.passed)}/${fa(s.total)}`], ["مورد سرخ", fa(s.failed)],
    ["زمان اجرا (میلی‌ثانیه)", fa(data.duration_ms)],
    ["نسخهٔ موتور ریاضی", data.engine ? data.engine.version : "—"],
    ["اثر انگشت موتور", data.engine ? data.engine.sha256 : "—"],
  ].map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  document.querySelector("#exam-table tbody").innerHTML = (data.cases || []).map((c) => {
    const detail = (c.rows || []).map((r) => `${r.key}=${r.got}`).join(" · ");
    return `<tr class="${c.ok ? "" : "red-row"}" ${c.ok ? "" : 'style="background:#fdeaea"'}>` +
      `<td>${c.ok ? "✅" : "✗"} <b>${c.id}</b><br><span class="hint">${c.title}</span></td>
      <td class="hint">${c.why}</td><td class="num" style="font-size:11px">${detail}</td>
      <td>${c.ok ? "سبز" : "سرخ"}</td></tr>`;
  }).join("") || `<tr><td colspan="4" class="hint">آزمون اجرا نشده است.</td></tr>`;
}

async function buildDossier() {
  busy("busy-dossier", true);
  const data = await api("/api/dossier", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({}) });
  busy("busy-dossier", false);
  const box = el("dossier-info");
  if (data.error) { box.textContent = "خطا: " + data.error; return; }
  const st = (data.summary && data.summary.selftest) || {};
  box.innerHTML = `ساخته شد: <code>${data.html}</code><br>
    آزمون ${st.passed || 0}/${st.total || 0} · زنجیرهٔ دفتر: ${data.summary && data.summary.chain_ok ? "سالم" : "شکسته"} ·
    کارنامه: ${data.summary && data.summary.scorecard_ready ? "آماده" : "ناتمام"} ·
    اثر انگشت پرونده: <code>${data.sha256}</code><br>
    نسخهٔ متنی برای ایمیل: <code>${data.md || ""}</code>`;
  logTo("log-trial", "پروندهٔ سرمایه‌گذار ساخته شد: " + data.html);
}

/* ---------------- گام ۲: امکان‌سنجی مسیرهای داده (پیش از خرید) ---------------- */
async function probeSources() {
  resetLog("log-src", "در حال سنجش مسیرهای داده…");
  busy("busy-src", true);
  const body = { symbol: (el("src-symbol").value || "فولاد").trim(),
                 ws_url: (el("src-ws").value || "").trim(),
                 fixture: el("src-fixture").checked, timeout: 8 };
  const data = await api("/api/sources/feasibility", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  busy("busy-src", false);
  if (data.error) { logTo("log-src", "خطا: " + data.error); return; }
  renderSources(data);
  const s = data.summary || {};
  logTo("log-src", `${s.ok} از ${s.total} نشانی جواب داد · کد نماد: ${data.code || "—"}`);
  logTo("log-src", data.verdict || "");
  if (data.fixture) logTo("log-src", "توجه: این اجرا روی دادهٔ ساختگی محلی بود؛ دربارهٔ سرویس واقعی چیزی نمی‌گوید.");
  if (data.ws) logTo("log-src", "پوش لحظه‌ای: " + data.ws.verdict + " — " + data.ws.note);
  logTo("log-src", "گزارش ساخته شد: " + data.report);
}

function renderSources(data) {
  const s = data.summary || {};
  const fa = (x) => (x == null ? "—" : String(x));
  el("src-kpis").innerHTML = [
    ["نشانی‌های سالم", `${fa(s.ok)}/${fa(s.total)}`], ["کد نماد", fa(data.code)],
    ["نماد", fa(data.symbol)], ["میزبان", data.fixture ? "سرور نمونهٔ محلی (ساختگی)" : fa(data.host)],
  ].map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const stab = {};
  (data.stability || []).forEach((x) => { stab[x.name] = x.checked ? x.verdict : (x.reason || "—"); });
  document.querySelector("#src-table tbody").innerHTML = (data.items || []).map((i) => `
    <tr><td>${i.ok ? "✅" : "✗"} ${i.label}</td>
        <td class="hint">${i.reason}</td>
        <td class="num">${fa(i.latency_ms)}</td>
        <td class="num" style="font-size:11px">${fa(i.count)}${i.top_keys && i.top_keys.length ? " · " + i.top_keys.join(", ") : ""}</td>
        <td>${stab[i.name] || "—"}</td></tr>`).join("") ||
    `<tr><td colspan="5" class="hint">سنجشی انجام نشده است.</td></tr>`;
  const ws = data.ws;
  el("src-ws-box").innerHTML = ws
    ? `<b>پوش لحظه‌ای:</b> ${ws.verdict} · TCP: ${ws.tcp ? "بله" : "نه"} · TLS: ${ws.tls ? "بله" : "نه"} ·
       کد پاسخ: ${ws.status || "—"}<br><span class="hint">${ws.note}</span>`
    : "نشانی پوش لحظه‌ای وارد نشده است؛ اگر کارگزاری‌تان نشانی داده، اینجا بگذارید تا وضعیت دسترسی‌اش را بگویید.";
}

async function makeVendorSheet() {
  const data = await api("/api/sources/sheet", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
  if (data.error) { logTo("log-src", "خطا: " + data.error); return; }
  logTo("log-src", "برگهٔ نیاز داده ساخته شد: " + data.path + " — همین را برای فروشنده‌ها بفرستید.");
}

async function makeWitness() {
  const box = el("witness-box");
  resetLog("witness-box", "در حال خواندن قیمت‌ها از سرویس فعال (بدون حافظهٔ نهان)…");
  busy("busy-witness", true);
  const data = await api("/api/witness", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
  busy("busy-witness", false);
  if (data.error) { logTo("witness-box", "خطا: " + data.error); return; }
  logTo("witness-box", data.summary);
  const faN = (x) => Number(x).toLocaleString("fa-IR");
  logTo("witness-box", `اتصال: ${data.connection} · ${faN(data.probes_ok)} از ${faN(data.probes_total)} قیمت خوانده شد`);
  logTo("witness-box", `اثر انگشت برگه: ${data.hash} — همین را با پروندهٔ data/witness-live.json بسنجید.`);
  if (data.note) logTo("witness-box", "هشدار صداقت: " + data.note);
  if (!data.ready && data.reason) logTo("witness-box", "تصمیم نمونه: " + data.reason);
  logTo("witness-box", "برگه: " + data.page + " · نسخهٔ متنی: " + data.md);
  logTo("witness-box", "برای نشان‌دادن به سرمایه‌گذار: «نمایش برگه» را بزنید و همان نشانی‌ها را در مرورگر باز کنید.");
}

function openDemoDoc() { window.open("/files/demo-investor", "_blank"); }

function openFile(name) {
  const map = { method: "method.html", backtest: "backtest.html", exam: "exam",
                selftest: "selftest", dossier: "dossier", dossierMd: "dossier-md",
                feasibility: "feasibility", requirementSheet: "requirement-sheet",
                dataStrategy: "data-strategy" };
  window.open("/files/" + (map[name] || name), "_blank");
}

/* ---------------- راه‌اندازی (بازنویسی‌شده) ---------------- */
/* ---------------- گام ۲: اتصال خودکار ---------------- */
async function autoConnect(save) {
  const box = el("auto-result");
  box.innerHTML = "در حال امتحان منابع رایگان… (هر منبع چند ثانیه)";
  busy("busy-auto", true);
  const data = await api("/api/autoconnect", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify({ save: !!save, symbol: "اهرم" }) });
  busy("busy-auto", false);
  if (data.error) { box.innerHTML = `<span class="bad">خطا: ${data.error}</span>`; return; }
  const rows = (data.results || []).map((r) =>
    `<tr><td>${r.ok ? "✅" : "✗"}</td><td>${r.label}</td>
      <td class="num">${r.value == null ? "—" : Number(r.value).toLocaleString("fa-IR")}</td>
      <td class="hint">${r.json_path || "—"}</td><td class="hint">${r.reason}</td></tr>`).join("");
  box.innerHTML = `<b>${data.summary}</b><br><span class="hint">آزمون در ${data.tested_at}</span>
    <table style="margin-top:6px"><thead><tr><th></th><th>منبع</th><th class="num">قیمت</th>
    <th>مسیر JSON</th><th>نتیجه و دلیل</th></tr></thead><tbody>${rows}</tbody></table>`;
  (data.results || []).forEach((r) => logTo("log-data", (r.ok ? "✓ " : "✗ ") + r.label + ": " + r.reason));
  logTo("log-data", data.summary);
  if (data.saved) {
    logTo("log-data", "منبع سالم ذخیره و فعال شد: " + data.saved.label);
    if (CONN.profiles) await loadConnections();
  }
  if (!data.ok) {
    logTo("log-data", "راه جایگزین: «خوراک آزمایشی محلی» برای تمرین، یا پروندهٔ دستی با اعداد کارگزاری.");
  }
}

/* ---------------- گام ۲: اسنپ‌شات دستی ---------------- */
const SNAP_COLS = [["symbol", "text"], ["kind", "kind"], ["spot", "num"], ["future", "num"],
                   ["strike", "num"], ["premium", "num"], ["days", "num"],
                   ["margin_per_contract", "num"], ["liquidity_contracts_per_day", "num"],
                   ["spread_pct", "num"], ["feed_symbol", "text"]];
const SNAP_KINDS = [["basis", "پایهٔ نقدی‌آتی"], ["box", "باکس اسپرد"], ["tabei", "تبعی"],
                    ["covered_call", "پوشش‌داده‌شده"], ["parity", "تساوی پوت‌کال"]];

function snapRowHtml(r, i) {
  const cells = SNAP_COLS.map(([key, type]) => {
    if (type === "kind") {
      return `<td><select data-f="${key}">` + SNAP_KINDS.map(([v, t]) =>
        `<option value="${v}" ${r[key] === v ? "selected" : ""}>${t}</option>`).join("") + `</select></td>`;
    }
    const v = r[key] == null ? "" : r[key];
    return `<td><input type="text" data-f="${key}" value="${v}"></td>`;
  }).join("");
  return `<tr>${cells}<td><button class="danger" onclick="this.closest('tr').remove()">حذف</button></td></tr>`;
}

async function loadSnapRows() {
  const data = await api("/api/snapshot/rows");
  if (data.error) { el("snap-status").textContent = "خطا: " + data.error; return; }
  const rows = (data.rows || []).length ? data.rows : [{ symbol: "", kind: "basis" }];
  document.querySelector("#snap-table tbody").innerHTML = rows.map(snapRowHtml).join("");
  el("snap-note").value = data.note || "";
  el("snap-status").textContent = (data.exists ? `خوانده شد از ${data.path}` : "پرونده‌ای نبود؛ جدول خالی است") +
    (data.last_dated?.length ? ` · آخرین اسنپ‌شات‌های تاریخ‌دار: ${data.last_dated.join("، ")}` : "");
  logTo("log-data", "اعداد فعلی در جدول آمد؛ هر عددی را عوض کنید و «ذخیرهٔ اسنپ‌شات امروز» را بزنید.");
}

function addSnapRow() {
  document.querySelector("#snap-table tbody").insertAdjacentHTML("beforeend", snapRowHtml({ kind: "basis" }, -1));
}

function collectSnapRows() {
  return [...document.querySelectorAll("#snap-table tbody tr")].map((tr) => {
    const row = {};
    tr.querySelectorAll("[data-f]").forEach((input) => { row[input.dataset.f] = input.value.trim(); });
    return row;
  });
}

async function saveSnapForm() {
  const rows = collectSnapRows();
  el("snap-problems").textContent = "در حال ذخیره…";
  const data = await api("/api/snapshot/save", { method: "POST", headers: { "Content-Type": "application/json" },
                                                  body: JSON.stringify({ rows, note: el("snap-note").value,
                                                                         confirm_real: el("snap-confirm").checked }) });
  if (data.error) {
    el("snap-problems").innerHTML = `<span class="bad">${data.error}</span>` + (data.problems || []).join(" · ");
    return;
  }
  el("snap-status").textContent = `ذخیره شد: ${data.path} (${data.rows} ردیف)`;
  el("snap-problems").innerHTML = (data.problems || []).join("<br>") || "بدون مشکل.";
  logTo("log-data", "اسنپ‌شات تاریخ‌دار ذخیره شد: " + data.path);
  (data.checklist || []).forEach((c) => logTo("log-data", "   · " + c));
  if (data.snapshot) updateBadge(data.snapshot.status, data.snapshot.source_label, data.snapshot.freshness, data.snapshot.rows);
}

/* ---------- دروازه: چه کسی وارد شده، کارفرما، و کلید خاموشی ---------- */
let GATE = { enabled: false, role: "admin", id: "—" };

async function loadGate() {
  try {
    const s = await api("/api/gate/status");
    GATE = s || GATE;
    const badge = el("whoami");
    if (badge) {
      const who = GATE.role === "guest" ? "کارفرما (مهمان)" : "مدیر";
      badge.textContent = GATE.enabled
        ? `دروازهٔ ورود: روشن · وارد‌شده: ${who}${GATE.id && GATE.id !== "—" ? " (" + GATE.id + ")" : ""}`
        : "دروازهٔ ورود: خاموش (همین رایانه = مدیر)";
      if (GATE.role === "guest") badge.style.background = "#fef3c7", badge.style.color = "#92400e";
    }
    const card = el("gate-card");
    if (card) card.style.display = GATE.role === "admin" ? "block" : "none";
    const adminCard = el("card-access");          // کارفرما پنل مدیریت ندارد؛ دکمهٔ بی‌نتیجه هم نمی‌بیند
    if (adminCard) adminCard.style.display = GATE.role === "guest" ? "none" : "block";
    gateMeter();
    renderGateUsers();
  } catch (e) { /* اگر وضعیت خوانده نشد، چیزی را قایم نمی‌کنیم */ }
}

function gateMeter() {
  const box = el("gate-state");
  if (!box) return;
  const g = GATE.guest || {};
  const users = GATE.users || [];
  box.textContent = (GATE.enabled ? "دروازه: روشن" : "دروازه: خاموش") +
    ` · مهمان (کارفرما): ` + (g.set ? `${g.id} — ${g.enabled ? "فعال" : "قطع‌شده"}` : "ساخته نشده") +
    ` · کاربران تازه: ${users.length ? users.map((u) => u.id + (u.enabled ? "" : " (قطع)")).join("، ") : "هیچ‌کدام"}` +
    ` · نشست‌های باز: ${GATE.open_sessions ?? 0}`;
}

function renderGateUsers() {
  const box = el("gate-users");
  if (!box) return;
  const users = GATE.users || [];
  if (!users.length) {
    box.innerHTML = "هیچ کاربر مهمانی ساخته نشده است. بالا شناسه و رمز بنویس و «ساخت کاربر» را بزن.";
    return;
  }
  box.innerHTML = users.map((u) =>
    `<span style="display:inline-block;background:#eef2f5;border-radius:8px;padding:3px 9px;margin:3px">` +
    `<code>${u.id}</code> ${u.enabled ? "فعال" : "قطع‌شده"}${u.sessions ? ` · نشست باز: ${u.sessions}` : ""} ` +
    `<a href="#" onclick="delGateUser('${u.id}');return false">حذف</a> · ` +
    `<a href="#" onclick="toggleGateUser('${u.id}', ${u.enabled ? "false" : "true"});return false">` +
    `${u.enabled ? "قطع" : "وصل"}</a></span>`).join("");
}

async function addGateUser() {
  const id = (el("new-gate-user").value || "").trim();
  const pass = el("new-gate-pass").value || "";
  const note = (el("new-gate-note").value || "").trim();
  if (!id || !pass) { logTo("log-gate", "شناسه و رمز کاربر تازه را بنویس."); return; }
  const res = await api("/api/gate/update", { method: "POST",
    body: JSON.stringify({ action: "user-add", id, pass, note }) });
  if (res.error) { logTo("log-gate", "خطا: " + res.error); return; }
  logTo("log-gate", res.note);
  el("new-gate-pass").value = "";
  GATE.users = res.users; renderGateUsers(); gateMeter();
}

async function delGateUser(id) {
  if (!(await askConfirm(`کاربر «${id}» کامل حذف شود؟ نشست بازش هم همین حالا بسته می‌شود.`, {title:"حذف کاربر"}))) return;
  const res = await api("/api/gate/update", { method: "POST",
    body: JSON.stringify({ action: "user-del", id }) });
  if (res.error) { logTo("log-gate", "خطا: " + res.error); return; }
  logTo("log-gate", res.note);
  GATE.users = res.users; renderGateUsers(); gateMeter();
}

async function toggleGateUser(id, enable) {
  const res = await api("/api/gate/update", { method: "POST",
    body: JSON.stringify({ action: enable ? "user-on" : "user-off", id }) });
  if (res.error) { logTo("log-gate", "خطا: " + res.error); return; }
  logTo("log-gate", res.note);
  GATE.users = res.users; renderGateUsers(); gateMeter();
}

async function gateAction(action) {
  logTo("log-gate", "در حال اجرا: " + action);
  const res = await api("/api/gate/update", { method: "POST",
    body: JSON.stringify({ action }) });
  if (res.error) { logTo("log-gate", "خطا: " + res.error); return; }
  if (res.users) { GATE.users = res.users; renderGateUsers(); }
  logTo("log-gate", res.note + (res.guest ? ` · مهمان: ${res.guest.set ? res.guest.id : "—"} ${res.guest.enabled ? "(فعال)" : "(قطع)"}` : ""));
  GATE.enabled = res.enabled; GATE.guest = res.guest;
  gateMeter();
}

async function saveGuest() {
  const id = (el("guest-id").value || "").trim();
  const pass = el("guest-pass").value || "";
  if (!id || !pass) { logTo("log-gate", "شناسه و رمز مهمان را بنویسید."); return; }
  logTo("log-gate", "در حال ذخیرهٔ رمز مهمان…");
  const res = await api("/api/gate/update", { method: "POST",
    body: JSON.stringify({ action: "set-guest", id, pass }) });
  if (res.error) { logTo("log-gate", "خطا: " + res.error); return; }
  logTo("log-gate", res.note + " · کارفرما با همین شناسه وارد می‌شود؛ رمز را خودش می‌داند.");
  el("guest-pass").value = "";
  GATE.guest = res.guest; gateMeter();
}

async function shutdownApp() {
  if (!(await askConfirm("برنامه همین حالا خاموش شود؟ کارفرما هم بیرون می‌افتد.", {title:"خاموشی برنامه"}))) return;
  const res = await api("/api/shutdown", { method: "POST", body: JSON.stringify({ confirm: true }) });
  if (res.error) { logTo("log-gate", "خطا: " + res.error); return; }
  logTo("log-gate", res.note);
  document.body.innerHTML = '<div style="padding:40px;font-family:Tahoma;direction:rtl">' +
    "<h2>برنامه خاموش شد.</h2><p>برای روشن‌کردن دوباره، همان میان‌بر/فرمان همیشگی را بزنید.</p></div>";
}

async function logoutApp() {
  await api("/api/logout", { method: "POST", body: "{}" });
  location.href = "/login";
}

async function boot() {
  buildNav();                   // نوار گام‌ها اول، تا صفحه حتی بدون شبکه شکل داشته باشد
  await loadGate();
  await loadGuide();
  await pickMode();
  await loadConnections();      // دفتر اتصال + پروفایل فعال ذخیره‌شده
  await loadSnapRows();         // جدول اعداد کارگزاری
  await loadRules();
  await loadTrial();
  await prospectLoad();         // تابلوی پیگیری مخاطبان (گام ۸)
  // vibefarsi progress — برای هر busy یک نوار پیشرفت راست‌به‌چپ بساز (اگر نبود)
  try {
    ["busy-run","busy-bt","busy-bundle","busy-daily","busy-trial","busy-exam","busy-dossier","busy-src","busy-auto","busy-witness","busy-blind","busy-rec","busy-strategies","busy-bankroll","busy-judge"].forEach(id=>{
      if (document.getElementById(id)) ensureProgressNear(id, 0);
    });
  } catch(e){}
  showStep(0);
  // اعلان خوش‌آمد با toast (provider آماده است)
  try { setTimeout(()=>Toast.info("ایستگاه آماده است", "از گام ۲ دادهٔ امروز را انتخاب کنید — همه‌چیز آفلاین و راست‌چین است.", {actionLabel:"باشه"}), 600); } catch(e){}
}

document.addEventListener("DOMContentLoaded", boot);

/* ---------------- گام ۱۰: آزمون کور سرمایه‌گذار ---------------- */
let CASES_CACHE = [];

async function loadCases() {
  busy("busy-blind", true);
  const data = await api("/api/investor/cases", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
  busy("busy-blind", false);
  if (data.error) { logTo("log-blind", "خطا: " + data.error); return; }
  CASES_CACHE = data.cases || [];
  el("blind-list").innerHTML = CASES_CACHE.map((c) => `
    <div class="card" style="margin:10px 0">
      <b>${c.title}</b>
      <div class="hint" style="margin:4px 0">${c.question}</div>
      <table>${c.given.map(([k, v]) => `<tr><td class="hint">${k}</td><td class="num">${v}</td></tr>`).join("")}</table>
      <div class="row" style="margin-top:6px">
        <span class="hint">حدس شما (${c.unit}):</span>
        <input type="text" id="guess-${c.id}" style="min-width:120px" placeholder="عدد یا بله/خیر">
      </div>
      <div id="res-${c.id}" class="hint"></div>
    </div>`).join("");
  logTo("log-blind", "شش پرسش نمایش داده شد. حدس‌های خودتان را بنویسید، بعد «داوری حدس‌های من» را بزنید.");
}

async function checkGuesses() {
  if (!CASES_CACHE.length) { await loadCases(); }
  busy("busy-blind", true);
  let done = 0;
  for (const c of CASES_CACHE) {
    const box = el("guess-" + c.id);
    const guess = box ? box.value.trim() : "";
    if (!guess) { continue; }
    const res = await api("/api/investor/check", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: c.id, guess }) });
    const t = el("res-" + c.id);
    if (res.error || !res.ok) { t.innerHTML = `<span class="warn">${res.error || res.detail}</span>`; continue; }
    done++;
    const off = (res.off_pct == null) ? "" : ` · فاصله ${res.off_pct}٪`;
    t.innerHTML = `<div class="kpi" style="margin-top:4px"><b>پاسخ برنامه: ${res.answer} ${res.unit || ""}</b>
      · داوری: ${res.verdict}${off}</div>
      <div class="hint">فرمول: ${res.formula}</div>
      <div class="hint">روش دوم (برای بازبینی با ماشین‌حساب): ${res.second || "—"}</div>
      <div class="hint">${res.note || ""}</div>`;
  }
  busy("busy-blind", false);
  logTo("log-blind", done ? `${done} پرسش داوری شد و در دفتر زنجیره‌هش‌دار ثبت شد.` :
    "هیچ حدسی نوشته نشده بود؛ اول حدس‌ها را بنویسید.");
}

async function loadLadder() {
  const data = await api("/api/investor/ladder", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client: (el("blind-client") ? el("blind-client").value.trim() : "") }) });
  if (data.error) { el("ladder-box").textContent = "خطا: " + data.error; return; }
  const doc = data.doc || {};
  const docLine = doc.counts && doc.counts.checked
    ? `<div class="hint" style="margin-top:6px">سند پلهٔ تصمیم: ${doc.counts.checked} ردیف بررسی شد · `
      + `${doc.counts.actionable} ردیف قابل اجرا · ${doc.counts.no_action} ردیف بدون اقدام`
      + (doc.titles && doc.titles.length ? ` · فهرست: ${doc.titles.join("، ")}` : "")
      + ` · نقطهٔ برگشت هر ردیف در سند نوشته شده است.`
      + (doc.verify && doc.verify.ok === false ? " ⚠️ زنجیرهٔ دفتر شکسته است." : "") + "</div>"
    : "";
  const hs = data.ladder.hurdles;
  const head = `<tr><th>راهبرد</th><th>بازده سالانه</th>${hs.map((h) => `<th>سد ${h}٪</th>`).join("")}</tr>`;
  const rows = data.ladder.rows.map((t) => `<tr><td>${t.name}</td>
    <td class="num">${t.annualized_pct == null ? "—" : t.annualized_pct + "٪"}</td>
    ${hs.map((h) => `<td>${t.cells[h].go ? "می‌گذرد" : "می‌افتد"}</td>`).join("")}</tr>`).join("");
  const sz = data.sizing.map((x) => `<tr><td class="num">${x.risk_pct}٪</td><td class="num">${x.contracts}</td>
    <td class="num">${x.margin_locked.toLocaleString("fa-IR")}</td><td class="num">${x.free_cash.toLocaleString("fa-IR")}</td></tr>`).join("");
  el("ladder-box").innerHTML = `<table>${head}${rows}</table>
    <div class="hint" style="margin-top:6px">${data.ladder.verdict}</div>
    <h4 style="margin-top:10px">اندازهٔ موقعیت: ۱۰۰ میلیون تومان، وجه تضمین ۲ میلیون</h4>
    <table><tr><th>سقف ریسک</th><th>قرارداد</th><th>وجه تضمین درگیر</th><th>نقد آزاد</th></tr>${sz}</table>`
    + docLine;
}

async function makePledge() {
  busy("busy-blind", true);
  const data = await api("/api/investor/pledge", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client: (el("blind-client") ? el("blind-client").value.trim() : "") }) });
  busy("busy-blind", false);
  if (data.error) { logTo("log-blind", "خطا: " + data.error); return; }
  logTo("log-blind", `پیمان‌نامهٔ نمایش ساخته شد (${data.chars} نویسه): ${data.path}`);
  logTo("log-blind", `زنجیره: ${data.verify.ok ? "سالم" : "شکسته"} `
    + `· ${data.verify.rows} ردیف · ${data.verify.detail}`);
  logTo("log-blind", "پیمان‌نامه می‌گوید چه چیزی اثبات می‌شود و چه چیزی نه؛ همان را قبل از نمایش بخوانید.");
}

async function doReconcile() {
  resetLog("log-rec", "در حال حساب…");
  busy("busy-rec", true);
  const body = { symbol: el("rec-symbol").value.trim(), entry: el("rec-entry").value.trim(),
                 exit: el("rec-exit").value.trim(), days: el("rec-days").value.trim(),
                 units: el("rec-units").value.trim(), expected: el("rec-expected").value.trim() };
  const data = await api("/api/investor/reconcile", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  busy("busy-rec", false);
  if (data.error) { logTo("log-rec", "خطا: " + data.error); return; }
  logTo("log-rec", `${data.symbol}: هزینهٔ کل ${data.cost.toLocaleString("fa-IR")} · ` +
    `دریافتی خالص ${data.proceeds.toLocaleString("fa-IR")} · سود/زیان ${data.profit.toLocaleString("fa-IR")}`);
  logTo("log-rec", `بازده دوره ${data.period_pct}٪ · سالانه ${data.annualized_pct}٪ → ${data.verdict}`);
  if (data.compare && data.compare !== "—") { logTo("log-rec", data.compare); }
  logTo("log-rec", data.note);
  logTo("log-rec", `زنجیره: ${data.chain.ok ? "سالم" : "شکسته"} · کلید آخر ${data.chain.last_fingerprint}`);
}

async function buildBlindSheet() {
  const data = await api("/api/investor/sheet", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ client: (el("blind-client") ? el("blind-client").value.trim() : "") }) });
  if (data.error) { logTo("log-blind", "خطا: " + data.error); return; }
  logTo("log-blind", "برگهٔ آزمون ساخته شد: " + data.html);
  logTo("log-blind", "نسخهٔ متنی: " + data.md);
  const ch = data.scorecard ? data.scorecard.verify : data.chain;
  logTo("log-blind", `زنجیره: ${ch.ok ? "سالم" : "شکسته"} · ${ch.rows} ردیف · کلید ${ch.last_fingerprint}`);
  if (data.scorecard && data.scorecard.scored) {
    logTo("log-blind", `${data.scorecard.scored} پرسش سنجیده شد و ${data.scorecard.near} پاسخ `
      + `نزدیک یا درست بود (${data.scorecard.fair_pp}٪). این عدد دربارهٔ شهود است، نه سود.`);
  }
}

async function verifyBlindChain() {
  const data = await api("/api/investor/verify", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
  logTo("log-blind", `زنجیره: ${data.ok ? "سالم" : "شکسته"} · ردیف ${data.rows} · ${data.detail}`);
}

/* ---------------- داوری سیگنال ابزارهای دیگر ---------------- */
const JUDGE_PRESETS = {
  basis: '{"spot":20000,"future":22800,"days":50,"spread_pct":0.005,"liquidity_contracts_per_day":900}',
  covered: '{"spot":7000,"strike":7400,"premium":120,"days":30}',
  tabei: '{"stock_price":50000,"put_price":200,"strike":62500,"days":90}',
  box: '{"call_low":300,"put_low":420,"call_high":180,"put_high":560,"strike_low":1200,"strike_high":1500,"days":45}',
  parity: '{"call":420,"put":380,"spot":9000,"strike":9000,"days":30}',
};

function judgePreset() {
  const k = el("judge-kind").value;
  el("judge-params").value = JUDGE_PRESETS[k] || "{}";
  el("judge-margin").value = el("judge-margin").value || "2000000";
  el("judge-contracts").value = el("judge-contracts").value || "10";
  el("judge-price").value = el("judge-price").value || (k === "basis" ? "20000" : "7000");
  logTo("log-judge", "نمونهٔ آماده برای «" + k + "» گذاشته شد؛ «داوری کن» را بزنید.");
}

async function judgeSignal(sheet) {
  busy("busy-judge", true);
  let params = {};
  try { params = JSON.parse(el("judge-params").value || "{}"); }
  catch (e) { busy("busy-judge", false); logTo("log-judge", "عددهای ورودی JSON درست نیستند."); return; }
  const body = { kind: el("judge-kind").value, params, sheet: !!sheet,
                 hurdle: el("judge-hurdle").value ? Number(el("judge-hurdle").value) / 100 : null,
                 claimed: el("judge-claimed").value || null,
                 margin: el("judge-margin").value || null,
                 contracts: el("judge-contracts").value || null,
                 price: el("judge-price").value || null };
  const data = await api("/api/judge", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  busy("busy-judge", false);
  if (data.error || !data.ok) { logTo("log-judge", "خطا: " + (data.error || data.detail)); return; }
  const ann = data.annualized_pct == null ? "—" : data.annualized_pct + "٪";
  el("judge-kpis").innerHTML = [
    ["داوری", data.verdict], ["بازده سالانهٔ خالص", ann],
    ["حاشیه بر نرخ سد", (data.edge_pp == null ? "—" : data.edge_pp + " واحد")],
    ["فاصله تا مارجین‌کال", (data.margin && data.margin.ok ? data.margin.move_pct + "٪" : "—")],
    ["اثر انگشت", data.fingerprint],
  ].map(([k, v]) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  (data.gates || []).forEach((g) => logTo("log-judge", (g.ok ? "✓ " : "✗ ") + g.gate + ": " + g.detail));
  if (data.break_even && data.break_even.value != null) {
    logTo("log-judge", "نقطهٔ برگشت — " + data.break_even.label + ": " + data.break_even.value);
  } else if (data.break_even) { logTo("log-judge", data.break_even.note); }
  if (data.margin && data.margin.ok) {
    logTo("log-judge", "مارجین‌کال: " + data.margin.formula
      + (data.margin.price_note ? " " + data.margin.price_note : ""));
  } else if (data.margin) { logTo("log-judge", data.margin.detail); }
  logTo("log-judge", `دو روش حساب: موتور ${data.annualized_pct}٪ · دستی ${data.hand.annualized_pct}٪ (اختلاف ${data.hand_diff_pp} واحد)`);
  if (data.claim_note) logTo("log-judge", data.claim_note);
  if (data.sheet_html) logTo("log-judge", "برگهٔ داوری ساخته شد: " + data.sheet_html);
  logTo("log-judge", "حالا می‌توانید همین برگه را به شرکت یا سرمایه‌گذار بدهید.");
}

/* ---------------- مجوز دسترسی، پشتیبانی و عیب‌یابی ---------------- */



/* ---------------- چسباندن اعداد کارگزاری و تشخیص خودکار ---------------- */
async function importPaste() {
  const text = (el("snap-paste").value || "").trim();
  if (!text) { logTo("paste-report", "کادر خالی است؛ متن را از سامانهٔ کارگزاری بچسبانید."); return; }
  logTo("paste-report", "در حال خواندن متن…");
  const d = await api("/api/snapshot/import", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, toman: el("paste-toman").checked }),
  });
  if (d.error) { logTo("paste-report", "خطا: " + d.error); return; }
  const tbody = document.querySelector("#snap-table tbody");
  const before = tbody.querySelectorAll("tr").length;
  (d.rows || []).forEach((r, i) => tbody.insertAdjacentHTML("beforeend", snapRowHtml(r, before + i)));
  logTo("paste-report", `${d.count} ردیف خوانده و به جدول اضافه شد (جمع: ${tbody.querySelectorAll("tr").length}).`);
  (d.hints || []).slice(0, 8).forEach((h) => logTo("paste-report", "· " + h));
  (d.problems || []).forEach((p) => logTo("paste-report", "✗ " + p));
  if (!d.count) logTo("paste-report", "هیچ ردیفی خوانده نشد؛ راهنمای ستون‌ها را ببینید.");
  el("snap-status").textContent = "ردیف‌های تازه اضافه شدند؛ عددها را بازبینی کنید و بعد «ذخیرهٔ اسنپ‌شات امروز» را بزنید.";
}

/* ---------------- گواهی استفادهٔ موفق ---------------- */


/* ---------------- تابلوی پیگیری مخاطبان (گام ۸) ---------------- */

function prospectPayload(extra) {
  return Object.assign({
    name: (el("prospect-name").value || "").trim(),
    kind: el("prospect-kind").value,
    channel: el("prospect-channel").value,
    date: (el("prospect-date").value || "").trim(),
  }, extra || {});
}

function paintProspects(res) {
  const wk = res.week || {};
  const todo = res.todo || [];
  const kpi = el("prospect-kpis");
  if (kpi) {
    kpi.innerHTML =
      `<div class="k"><b>${wk.messages ?? 0}</b><span>پیام این هفته (هدف ${wk.targets?.messages ?? 5})</span></div>` +
      `<div class="k"><b>${wk.calls ?? 0}</b><span>تماس (هدف ${wk.targets?.calls ?? 1})</span></div>` +
      `<div class="k"><b>${wk.meetings ?? 0}</b><span>جلسه (هدف ${wk.targets?.meetings ?? 1})</span></div>` +
      `<div class="k"><b>${todo.length}</b><span>کار امروز</span></div>`;
  }
  if (todo.length) {
    todo.forEach((t) => logTo("log-prospects",
      `→ ${t.name}: ${t.action}${t.urgent ? " ⚡" : ""} — ${t.why}`));
  } else {
    logTo("log-prospects", "امروز کاری در نوبت نیست.");
  }
}

async function prospectCall(payload, okMsg) {
  const res = await api("/api/prospects", { method: "POST", body: JSON.stringify(payload) });
  if (res.error) { logTo("log-prospects", "خطا: " + res.error); return null; }
  logTo("log-prospects", okMsg);
  paintProspects(res);
  return res;
}

async function prospectAdd() {
  const p = prospectPayload({ action: "add", note: "" });
  if (!p.name) { logTo("log-prospects", "اول نام مخاطب را بنویسید."); return; }
  const res = await prospectCall(p, `«${p.name}» به تابلو اضافه شد.`);
  if (res) { el("prospect-name").value = ""; }
}

async function prospectMark(event) {
  const p = prospectPayload({ action: event });
  if (!p.name) { logTo("log-prospects", "نام مخاطب را بنویسید."); return; }
  const labels = { sent: "پیام اول ثبت شد", followup: "پیگیری ثبت شد",
                   reply: "جواب ثبت شد", meeting: "جلسه ثبت شد" };
  await prospectCall(p, `${labels[event] || event}: ${p.name}`);
}

async function prospectOutcome() {
  const p = prospectPayload({ action: "outcome", result: el("prospect-result").value });
  if (!p.name) { logTo("log-prospects", "نام مخاطب را بنویسید."); return; }
  await prospectCall(p, `نتیجهٔ جلسه ثبت شد (${p.result}): ${p.name}`);
}

async function prospectClose() {
  const p = prospectPayload({ action: "close" });
  if (!p.name) { logTo("log-prospects", "نام مخاطب را بنویسید."); return; }
  await prospectCall(p, `پروندهٔ «${p.name}» بسته شد.`);
}

async function prospectSheet() {
  const res = await api("/api/prospects", { method: "POST", body: JSON.stringify({ action: "sheet" }) });
  if (res.error) { logTo("log-prospects", "خطا: " + res.error); return; }
  logTo("log-prospects", `برگهٔ تابلو ساخته شد: ${res.html}`);
  logTo("log-prospects", `نسخهٔ متنی: ${res.md}`);
  paintProspects(res);
}

async function prospectLoad() {
  const res = await api("/api/prospects", { method: "POST", body: JSON.stringify({ action: "list" }) });
  if (res.error) return;
  paintProspects(res);
}

async function buildOutreach() {
  const client = (el("offer-client").value || "").trim();
  const kind = el("outreach-kind").value || "company";
  logTo("log-bundle", "در حال ساخت پیام‌های معرفی…");
  const res = await api("/api/outreach", { method: "POST", body: JSON.stringify({ client, kind }) });
  if (res.error) { logTo("log-bundle", "خطا: " + res.error); return; }
  logTo("log-bundle", `پیام‌ها ساخته شد (${res.kind_label}): ${res.md}`);
  logTo("log-bundle", "چهار متن آماده: پیام اول، پیام بعد از جواب، تأیید وقت، و پیگیری " +
    "— به‌همراه اسکریپت تماس و پاسخ چهار مخالفت. هدف پیام اول فقط نیم‌ساعت وقت است.");
  logTo("log-bundle", "قاعده: پیگیری فقط سه بار (روز ۰، ۳، ۱۰) و هیچ عدد سودی در هیچ پیامی نیست.");
}

async function buildReviewMeeting() {
  const client = (el("offer-client").value || "").trim();
  const start = (el("onboard-start").value || "").trim();
  const on = (el("review-on").value || "").trim();
  logTo("log-bundle", "در حال ساخت برگهٔ جلسهٔ بازبینی…");
  const res = await api("/api/review-meeting", { method: "POST",
    body: JSON.stringify({ client, start, on }) });
  if (res.error) { logTo("log-bundle", "خطا: " + res.error); return; }
  logTo("log-bundle", `برگهٔ جلسهٔ بازبینی ساخته شد: ${res.html}`);
  logTo("log-bundle", `روز بازبینی: ${res.review} — ${res.status}`);
  logTo("log-bundle", `نسخهٔ متنی: ${res.md}`);
  logTo("log-bundle", "روی برگه: سه شاهد، پنج شرط کارنامه، دو خروجی (ادامه با پرداخت / توقف) و پیگیری تاریخ‌دار.");
  if (!res.price_given) logTo("log-bundle", "قیمت روی برگه «توافقی» است؛ عدد در جلسه گذاشته می‌شود.");
}

async function buildSalesRitual() {
  const sender = (el("ritual-sender").value || "").trim() || "مسعود";
  const on = (el("ritual-on").value || "").trim();
  resetLog("log-ritual", "در حال خواندن تابلو و چیدن کار امروز…");
  const res = await api("/api/sales-ritual", { method: "POST", body: JSON.stringify({ sender, on }) });
  if (res.error) { logTo("log-ritual", "خطا: " + res.error); return; }
  const c = res.counts || {};
  const faN = (x) => Number(x || 0).toLocaleString("fa-IR");      // رقم فارسی، مثل بقیهٔ صفحه
  logTo("log-ritual", `${res.date} · ${faN(res.used_minutes)} از ${faN(res.budget)} دقیقه — `
    + `${faN(c.messages)} پیام · ${faN(c.calls)} تماس · ${faN(c.internal)} کار دفتری`);
  (res.items || []).forEach((i) => logTo("log-ritual",
    `→ ${i.name} (${i.channel_label}): ${i.action}`));
  (res.deferred || []).forEach((d) => logTo("log-ritual", `↷ فردا: ${d.name} — ${d.reason}`));
  logTo("log-ritual", res.note);
  logTo("log-ritual", `برگهٔ امروز ساخته شد: ${res.html} · نسخهٔ متنی: ${res.md}`);
}

async function buildOnboarding() {
  const client = (el("offer-client").value || "").trim();
  const start = (el("onboard-start").value || "").trim();
  logTo("log-bundle", "در حال ساخت برگهٔ روز اول مشتری…");
  const res = await api("/api/onboarding", { method: "POST",
    body: JSON.stringify({ client, start }) });
  if (res.error) { logTo("log-bundle", "خطا: " + res.error); return; }
  logTo("log-bundle", `برگهٔ روز اول ساخته شد: ${res.html}`);
  logTo("log-bundle", `نسخهٔ متنی: ${res.md}`);
  logTo("log-bundle", `آزمون ${res.trial_days} روزه · روز بازبینی: ${res.review} — `
    + "پنج کار روز اول، دو هفته بدون خرید، و شرط‌های کارنامه روی برگه است.");
  if (!res.price_given) logTo("log-bundle", "قیمت روی برگه «توافقی» است؛ عدد در جلسه گذاشته می‌شود.");
}

async function buildOffer() {
  const client = (el("offer-client").value || "").trim();
  logTo("log-bundle", "در حال ساخت پیشنهاد یک‌صفحه‌ای…");
  const res = await api("/api/offer", { method: "POST", body: JSON.stringify({ client }) });
  if (res.error) { logTo("log-bundle", "خطا: " + res.error); return; }
  logTo("log-bundle", `پیشنهاد ساخته شد: ${res.html}`);
  logTo("log-bundle", `نسخهٔ متنی برای ایمیل/واتساپ: ${res.md}`);
  if (!res.price_given) {
    logTo("log-bundle", "قیمت روی برگه «توافقی» نوشته شد؛ عدد را در جلسه بگذارید (یا با مبلغ بسازید).");
  }
  if (res.kit && res.kit.files) {
    logTo("log-bundle", `روی برگه نوشته شد: بستهٔ ${res.kit.files} پرونده‌ای آمادهٔ تحویل.`);
  }
}

function openAdminPanel() {
  window.open("/admin", "_blank", "noopener");
}
window.openAdminPanel = openAdminPanel;
window.buildOffer = buildOffer;
window.buildOnboarding = buildOnboarding;
window.buildSalesRitual = buildSalesRitual;
window.gateAction = gateAction;
window.addGateUser = addGateUser;
window.delGateUser = delGateUser;
window.toggleGateUser = toggleGateUser;
window.saveGuest = saveGuest;
window.shutdownApp = shutdownApp;
window.logoutApp = logoutApp;
window.loadGate = loadGate;
window.buildReviewMeeting = buildReviewMeeting;
window.buildOutreach = buildOutreach;
window.prospectAdd = prospectAdd;
window.prospectMark = prospectMark;
window.prospectOutcome = prospectOutcome;
window.prospectClose = prospectClose;
window.prospectSheet = prospectSheet;
window.prospectLoad = prospectLoad;

