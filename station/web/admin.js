/* پنل مدیریت ایستگاه — ورود، بررسی سلامت، مجوز/عیب‌یابی، گواهی استفاده.
   همهٔ درخواست‌ها با سرآیند X-Admin-Token می‌روند؛ توکن فقط در همین مرورگر می‌ماند. */

const CREDIT = 'دولوپر: مهندس مسعود مجربیان · همراه: 09126630554 · ' +
  'Telegram: <a href="https://t.me/Mojarabian" target="_blank" rel="noopener">Mojarabian</a> · ' +
  'Instagram: <a href="https://instagram.com/Mojarabian.Art" target="_blank" rel="noopener">Mojarabian.Art</a>';

const KEY = "station-admin-token";
const $ = (id) => document.getElementById(id);

const token = () => sessionStorage.getItem(KEY) || "";
function setToken(t) { if (t) sessionStorage.setItem(KEY, t); else sessionStorage.removeItem(KEY); }

function logTo(id, line) {
  const box = $(id);
  if (!box) return;
  const t = new Date().toLocaleTimeString("fa-IR");
  box.textContent = (box.dataset.fresh === "1" ? "" : box.textContent + "\n") + `[${t}] ${line}`;
  box.dataset.fresh = "0";
  box.scrollTop = box.scrollHeight;
}
function resetLog(id, line) {
  const box = $(id);
  if (!box) return;
  box.textContent = line || "";
  box.dataset.fresh = "1";
}

async function api(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Token": token() },
    body: JSON.stringify(body || {}),
  });
  let data = {};
  try { data = await r.json(); } catch (e) { data = { error: "پاسخ خوانده نشد" }; }
  data.__status = r.status;
  return data;
}

function showArea(on) {
  $("admin-area").classList.toggle("hidden", !on);
  $("login-card").classList.toggle("hidden", on);
  $("who").textContent = on ? "وارد شده‌اید — دسترسی مدیر" : "وارد نشده‌اید";
}

async function doLogin() {
  const id = $("admin-id").value.trim();
  const pass = $("admin-password").value;
  if (!id || !pass) { logTo("login-box", "شناسه و رمز را پر کنید."); return; }
  const d = await api("/api/admin/login", { id, pass });
  if (!d.ok) { logTo("login-box", "ورود ناموفق: " + (d.error || "دلیل نامشخص")); return; }
  setToken(d.token);
  resetLog("login-box", `ورود موفق · اعتبار توکن: ${d.expires_in_minutes} دقیقه بی‌کاری.`);
  $("admin-password").value = "";
  showArea(true);
  await licenseStatus();
}

async function whoami() {
  if (!token()) { showArea(false); return false; }
  const d = await api("/api/admin/whoami");
  if (!d.ok) { setToken(""); showArea(false); logTo("login-box", "توکن منقضی شده؛ دوباره وارد شوید."); return false; }
  showArea(true);
  return true;
}

async function logout() {
  if (token()) await api("/api/admin/logout");
  setToken("");
  showArea(false);
  resetLog("login-box", "از پنل خارج شدید.");
}

/* ---------------------------------------------------- ۱. بررسی سلامت */

async function doHealth() {
  resetLog("log-health", "در حال بررسی…");
  const d = await api("/api/admin/health");
  if (!d.ok && !d.items) { logTo("log-health", "خطا: " + (d.error || "نامشخص")); return; }
  const rows = (d.items || []).map((it) =>
    `<tr><td>${it.ok ? "✅" : "⚠️"}</td><td>${it.name}</td><td class="hint">${it.note || ""}</td></tr>`).join("");
  $("health-table").innerHTML =
    `<p class="hint">نسخهٔ ایستگاه: <code>${d.version || "—"}</code> · گذشت ${d.passed || 0} از ${d.total || 0} جزء.</p>
     <table><thead><tr><th></th><th>جزء</th><th>توضیح</th></tr></thead><tbody>${rows}</tbody></table>`;
  resetLog("log-health", d.ok ? "همهٔ اجزا سالم‌اند." : "بعضی اجزا هشدار دادند؛ به جدول بالا نگاه کنید.");
}

/* ------------------------------------------- ۲. مجوز و عیب‌یابی */

function licPayload(extra) {
  return Object.assign({
    client: $("lic-client").value.trim(),
    months: parseInt($("lic-months").value || "12", 10),
    contact: $("lic-contact").value.trim(),
  }, extra || {});
}

async function licenseStatus() {
  const d = await api("/api/admin/license", { action: "status" });
  const lic = d.license || {};
  $("license-state").innerHTML = lic.client
    ? `<p class="ok">مجوز فعلی: <b>${lic.client}</b> · ${lic.months} ماه · صادر: ${lic.issued_on || "—"}
       · انقضا: ${lic.expires_on || "—"} · امضا: <code>${lic.signature || "—"}</code></p>`
    : `<p class="hint">هیچ مجوزی صادر نشده است. نام شرکت را بنویسید و «صدور مجوز دسترسی» را بزنید.</p>`;
  resetLog("log-access", "وضعیت مجوز خوانده شد.");
}

async function grantLicense() {
  if (!$("lic-client").value.trim()) { logTo("log-access", "اول نام شرکت را بنویسید."); return; }
  const d = await api("/api/admin/license", licPayload({ action: "grant" }));
  if (!d.ok) { logTo("log-access", "خطا: " + (d.error || "صدور ناموفق")); return; }
  logTo("log-access", `مجوز برای «${d.license.client}» صادر شد · مسیر: ${d.path}`);
  logTo("log-access", `امضا: ${d.license.signature} · انقضا: ${d.license.expires_on}`);
  await licenseStatus();
  logTo("log-access", "مجوز نام‌دار صادر شد.");
  logTo("log-access", "قدم بعدی: «ساخت سند مجوز (چاپی)» و بعد بستهٔ شاهد گام ۸ — مجوز و گواهی خودکار داخل بسته می‌روند.");
}

async function licenseDocument() {
  const d = await api("/api/admin/license", { action: "document" });
  if (!d.ok) { logTo("log-access", "خطا: " + (d.error || "ساخت سند ناموفق")); return; }
  logTo("log-access", `سند چاپی اجازه‌نامه: ${d.html}`);
  logTo("log-access", `نسخهٔ متنی برای ایمیل: ${d.md}`);
}

async function makeTrialLicense() {
  const d = await api("/api/admin/license", licPayload({ action: "trial" }));
  logTo("log-access", d.ok ? `مجوز آزمون ارزیابی ساخته شد · ${d.path}` : "خطا: " + (d.error || "—"));
  await licenseStatus();
}

async function revokeLicense() {
  if (!confirm("مجوز فعلی باطل شود؟")) return;
  const d = await api("/api/admin/license", { action: "revoke" });
  logTo("log-access", d.ok ? "مجوز باطل شد." : "خطا: " + (d.error || "—"));
  await licenseStatus();
}

async function runDiagnose() {
  logTo("log-access", "در حال ساخت گزارش عیب‌یابی…");
  // «quick» تا درایورِ آزمون را داخلِ درخواست نکشیم: روی میزبان ابریِ ۰.۱ هسته و ۵۱۲ مگابایت،
  // همان ۷۳۳ آزمون می‌تواند چند دقیقه بکشد و درخواست را بماند؛ درایور را جای خود (رایانهٔ
  // کاربر) اجرا کنید. بقیهٔ گزارش‌گیر — سلامت، مجوز، اتصال، پرونده‌ها — کامل می‌آید.
  const d = await api("/api/admin/diagnose", {quick: true});
  if (!d.ok) { logTo("log-access", "خطا: " + (d.error || "ساخت ناموفق")); return; }
  logTo("log-access", `گزارش ساخته شد: ${d.path || d.html}`);
  if (d.fingerprint) logTo("log-access", `اثر انگشت موتور: ${d.fingerprint}`);
}

/* ------------------------------------------- ۳′. پشتیبان ابری وضعیت */

async function loadStateInfo() {
  const d = await api("/api/admin/state", {});
  if (!d || d.error) { logTo("log-state", "خطا: " + ((d && d.error) || "نامشخص")); return; }
  if (!d.online) {
    el("state-box").textContent = d.note || "پشتیبان ابری در این نسخه نیست.";
    logTo("log-state", "پشتیبان ابری خاموش است (برنامه سالم است).");
    return;
  }
  const last = d.last || {};
  const done = last.ok ? `${last.at} · ${last.files} پرونده · ${last.kb} کیلوبایت` : "هنوز نه";
  el("state-box").innerHTML =
    `زیر نگهبانی: <b>${d.files}</b> پرونده · <b>${d.kb}</b> کیلوبایت · هر ${Math.round((d.interval_seconds || 0) / 60)} دقیقه<br>` +
    `آخرین پشتیبان: <b>${done}</b>${last.reason ? " (" + last.reason + ")" : ""}<br>` +
    `سرِ روشن‌شدن برگشت: <b>${(d.restored && d.restored.files) || 0}</b> پرونده` +
    `${(d.restored && d.restored.at) ? " (" + d.restored.at + ")" : ""}<br>` +
    `مخزن: <span dir="ltr">${d.repo || "—"}</span>`;
  logTo("log-state", "وضعیت نگهبان خوانده شد.");
}

async function backupNow() {
  logTo("log-state", "در حال پشتیبان‌گیری…");
  const d = await api("/api/admin/backup", {});
  if (!d || d.error) { logTo("log-state", "خطا: " + ((d && d.error) || "نامشخص")); return; }
  if (!d.ok) { logTo("log-state", d.note || "انجام نشد."); return; }
  const last = d.last || {};
  logTo("log-state", `پشتیبان گرفته شد: ${last.files} پرونده · ${last.kb} کیلوبایت · ${last.at}`);
  await loadStateInfo();
}

/* ------------------------------------------- ۳. گواهی استفاده */

async function loadUsage() {
  const d = await api("/api/admin/usage", { action: "summary" });
  if (!d.ok) { logTo("usage-box", "خطا: " + (d.error || "نامشخص")); return; }
  const s = d.summary || {};
  resetLog("usage-box", "");
  logTo("usage-box",
    `مجموع کارهای موفق: ${s.success_total} · روزهای فعال: ${s.active_days} · امروز: ${s.today}` +
    ` · زنجیره: ${s.chain_ok ? "سالم" : "شکسته در ردیف " + s.broken_at}`);
  Object.entries(s.by_kind_label || s.by_kind || {}).forEach(([k, n]) => logTo("usage-box", `· ${k}: ${n}`));
  if (!s.rows) logTo("usage-box", "هنوز کاری ثبت نشده؛ با اجرای گام ۵ یا یک داوری سیگنال شروع می‌شود.");
  $("usage-kpis").innerHTML = [
    ["کار موفق", s.success_total], ["روزهای فعال", s.active_days],
    ["هفت روز گذشته", s.last_7_days], ["زنجیره", s.chain_ok ? "سالم ✅" : "شکسته ⚠️"],
  ].map(([k, v]) => `<div><b>${v}</b><span>${k}</span></div>`).join("");
}

async function buildUsageStatement() {
  const d = await api("/api/admin/usage",
    { action: "statement", client: $("usage-client").value.trim() });
  if (!d.ok) { logTo("usage-box", "خطا: " + (d.error || "نامشخص")); return; }
  logTo("usage-box", `گواهی ساخته شد: ${d.html}`);
  logTo("usage-box", `نسخهٔ متنی برای ایمیل: ${d.md}`);
  if (d.summary) logTo("usage-box", `کارهای موفق در این گواهی: ${d.summary.success_total} · زنجیره: ` +
    (d.summary.chain_ok ? "سالم" : "شکسته در ردیف " + d.summary.broken_at));
}

/* ------------------------------------------- ۴. کاربران (شناسه/رمز دست خودت) */

async function gateUpdate(payload) {
  /* دروازه با کوکیِ ورودِ خودش کار می‌کند؛ درخواست از همین صفحه فرستاده می‌شود */
  const r = await fetch("/api/gate/update", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return await r.json();
}

function renderUsers(rows) {
  const box = $("users-table");
  if (!rows || !rows.length) {
    box.innerHTML = '<div class="hint">هیچ کاربر مهمانی ساخته نشده است. ' +
      'می‌توانی همین‌جا برای هر نفر یک شناسه/رمز بسازی.</div>';
    return;
  }
  box.innerHTML = "<table><tr><th>شناسه</th><th>وضعیت</th><th>یادداشت</th><th>نشست باز</th>" +
    "<th>کار</th></tr>" + rows.map((u) =>
      `<tr><td><code>${u.id}</code></td>` +
      `<td>${u.enabled ? "فعال" : "قطع‌شده"}</td>` +
      `<td class="hint">${u.note || "—"}</td>` +
      `<td>${u.sessions || 0}</td>` +
      `<td>` +
      `<button onclick="toggleUser('${u.id}', ${u.enabled ? "false" : "true"})">` +
      `${u.enabled ? "قطع دسترسی" : "وصل کردن"}</button> ` +
      `<button onclick="deleteUser('${u.id}')">حذف کامل</button>` +
      `</td></tr>`).join("") + "</table>";
}

async function loadUsers() {
  const d = await fetch("/api/gate/status").then((r) => r.json()).catch(() => ({}));
  renderUsers(d.users);
  logTo("log-users", d.users ? `فهرست خوانده شد: ${d.users.length} کاربر (به‌جز حساب مهمانِ قدیمی).`
                             : "فهرست خوانده نشد؛ مطمئن شو با حساب مدیر وارد شده‌ای.");
}

async function addUser() {
  const id = $("new-user-id").value.trim();
  const pass = $("new-user-pass").value;
  const note = $("new-user-note").value.trim();
  if (!id || !pass) { logTo("log-users", "شناسه و رمز را بنویس."); return; }
  const res = await gateUpdate({ action: "user-add", id, pass, note });
  if (res.error) { logTo("log-users", "خطا: " + res.error); return; }
  logTo("log-users", res.note);
  $("new-user-pass").value = "";
  renderUsers(res.users);
}

async function toggleUser(id, enable) {
  const res = await gateUpdate({ action: enable ? "user-on" : "user-off", id });
  if (res.error) { logTo("log-users", "خطا: " + res.error); return; }
  logTo("log-users", res.note);
  renderUsers(res.users);
}

async function deleteUser(id) {
  if (!confirm(`کاربر «${id}» کامل حذف شود؟ نشست بازش هم همین حالا بسته می‌شود.`)) return;
  const res = await gateUpdate({ action: "user-del", id });
  if (res.error) { logTo("log-users", "خطا: " + res.error); return; }
  logTo("log-users", res.note);
  renderUsers(res.users);
}

async function setAdminCreds() {
  const id = $("admin-new-id").value.trim();
  const pass = $("admin-new-pass").value;
  if (!id || !pass) { logTo("log-admin-creds", "شناسه و رمز تازه را بنویس."); return; }
  if (!confirm(`شناسهٔ ورود به «${id}» عوض شود؟ از این به بعد با همین وارد می‌شوی.`)) return;
  const res = await gateUpdate({ action: "set-admin", id, pass });
  if (res.error) { logTo("log-admin-creds", "خطا: " + res.error); return; }
  $("admin-new-pass").value = "";
  logTo("log-admin-creds", res.note + ` · شناسهٔ فعلی مدیر: ${res.admin.id}`);
}

/* ------------------------------------------- پرونده‌های پنل (با توکن) */

async function openAdminFile(key) {
  try {
    const r = await fetch("/files/" + encodeURIComponent(key),
      { headers: { "X-Admin-Token": token() } });
    if (!r.ok) { logTo(token() ? "log-access" : "login-box", "پرونده در دسترس نیست (" + r.status + ")"); return; }
    const blob = await r.blob();
    window.open(URL.createObjectURL(blob), "_blank");
  } catch (e) {
    logTo("log-access", "باز کردن پرونده ناموفق: " + e.message);
  }
}

/* ------------------------------------------- ۵. لاگ‌ها (ممیزی) */

/* تاریخِ انتخاب‌شده به‌شکلِ «1405/7/1» (ارقامِ لاتین، بر اساسِ مهارتِ jalali-calendar) نگه داشته
 * می‌شود و برای نمایش فارسی می‌شود. بازهٔ «از/تا» به مرزهای UTCِ روزهای تهران تبدیل می‌شود. */
function auditRange() {
  const el = $("audit-range");
  const from = el.dataset.j || null;
  const to = el.dataset.t || null;
  if (from && to && JalaliCal.diffDays(JalaliCal.parse(from), JalaliCal.parse(to)) < 0) return null;
  return { from, to };
}
function auditRangeUi() {
  const el = $("audit-range");
  const r = auditRange();
  if (r && r.from && r.to) {
    const a = JalaliCal.parse(r.from), b = JalaliCal.parse(r.to);
    const days = JalaliCal.diffDays(a, b) + 1;
    el.value = `از ${JalaliCal.fmt(a)} تا ${JalaliCal.fmt(b)} · ${Jalali.faNum(days)} روز`;
  } else el.value = "";
}
/* بازهٔ تاریخ با کامپوننتِ دو ماهه: کلیکِ اول «از»، دوم «تا» (specِ date-range-picker). */
function openAuditRange() {
  const el = $("audit-range");
  const r = auditRange() || { from: null, to: null };
  JalaliCal.openRange(el, {
    from: r.from ? JalaliCal.parse(r.from) : null,
    to: r.to ? JalaliCal.parse(r.to) : null,
    onDone: (f, t) => {
      el.dataset.j = f ? f.join("/") : "";
      el.dataset.t = t ? t.join("/") : "";
      auditRangeUi();
    },
    onClear: () => {
      el.dataset.j = "";
      el.dataset.t = "";
      auditRangeUi();
    }
  });
}
window.openAuditRange = openAuditRange;

async function loadAudit() {
  const user = $("audit-user").value;
  const search = $("audit-search").value.trim();
  const level = $("audit-level").value;
  const limit = $("audit-limit").value || "500";
  const qs = new URLSearchParams({ limit });
  if (user) qs.set("user", user);
  if (search) qs.set("search", search);
  if (level) qs.set("level", level);
  const r = auditRange();
  if (r && r.from) {
    const b = JalaliCal.tehranDayUtc(...JalaliCal.parse(r.from));
    qs.set("from", b.fromIso);
  }
  if (r && r.to) {
    const b = JalaliCal.tehranDayUtc(...JalaliCal.parse(r.to));
    qs.set("to", b.toIso);
  }
  try {
    const r = await fetch("/api/admin/audit?" + qs.toString(),
      { headers: { "X-Admin-Token": token() } });
    const d = await r.json();
    if (!r.ok || !d.ok) throw new Error(d.error || r.status);
    const tb = $("audit-table").querySelector("tbody");
    tb.innerHTML = "";
    for (const e of d.entries) {
      const tr = document.createElement("tr");
      const det = (e.details && e.details.query)
        ? Object.entries(e.details.query).map(([k, v]) => `${k}=${Array.isArray(v) ? v[0] : v}`).join(" · ")
        : "";
      const err = e.error ? `<div style="color:#b3261e;font-size:12px;white-space:pre-wrap">${e.error.slice(0, 300)}</div>` : "";
      const stColor = (e.status >= 500) ? "#b3261e" : (e.status === 401 || e.status === 403) ? "#b45309" : "#0a7d33";
      const tsFa = (window.Jalali && e.ts)
        ? `<span title="UTC: ${e.ts}">${Jalali.fmt(e.ts)}</span>`
        : (e.ts || "—");
      tr.innerHTML =
        `<td style="white-space:nowrap">${tsFa}</td>` +
        `<td>${e.user}</td><td>${e.role}</td>` +
        `<td>${e.method} ${e.path}${e.action && e.action !== e.path ? `<div class="hint">${e.action}</div>` : ""}</td>` +
        `<td>${det}${err}</td>` +
        `<td style="color:${stColor};font-weight:bold;white-space:nowrap">${e.status} · ${e.ms}ms</td>`;
      tb.appendChild(tr);
    }
    if (!d.entries.length) {
      // حالتِ خالی (specِ empty-state): وضعیت + قدمِ بعدی، نه صفحهٔ صاف
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="6" style="text-align:center;padding:26px 10px">
        <div style="font-size:14px;font-weight:700;margin-bottom:4px">هیچ ردیفی در این فیلترها نیست</div>
        <div class="hint">بازهٔ تاریخ را گسترده‌تر کنید یا «جست‌وجو/سطح/کاربر» را خالی کنید؛
        اگر تازه کار کرده‌اید، همان کار همین حالا باید اینجا ثبت باشد.</div></td>`;
      tb.appendChild(tr);
    }
    const s = d.stats;
    $("audit-stats").textContent =
      `جمع: ${s.entries} ردیف · خطا: ${s.errors} · کاربر: ${s.users} · آرشیو: ${s.archived} · ${Math.round(s.bytes / 1024)}KB`;
    logTo("log-audit", `${d.count} ردیف خوانده شد.`);
    // فیلترِ کاربرها را با همان کاربرانِ دیدگی پر می‌کنیم
    const sel = $("audit-user");
    const cur = sel.value;
    const seen = [...new Set(d.entries.map((e) => e.user).filter((u) => u !== "—"))];
    for (const u of seen) {
      if (![...sel.options].some((o) => o.value === u)) {
        const o = document.createElement("option");
        o.value = u; o.textContent = u;
        sel.appendChild(o);
      }
    }
    sel.value = cur;
  } catch (e) {
    logTo("log-audit", "خواندن لاگ ناموفق: " + e.message);
  }
}

async function copyAudit() {
  try {
    const d = await api("/api/admin/audit", { action: "copy", limit: 5000 });
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(d.text);
      logTo("log-audit", "لاگ در حافظه کپی شد (قابل چسباندن در تلگرام/ایمیل).");
    } else {
      logTo("log-audit", "کپی آماده است (این مرورگر حافظه ندارد؛ متن در پاسخِ سرور بود).");
    }
  } catch (e) {
    logTo("log-audit", "کپی ناموفق: " + e.message);
  }
}

async function clearAudit() {
  if (!confirm("کل لاگِ ممیزی پاک شود؟ (آرشیو نمی‌شود)")) return;
  const d = await api("/api/admin/audit", { action: "clear" });
  logTo("log-audit", `${d.cleared} ردیف پاک شد.`);
  loadAudit();
}

async function resetAudit() {
  if (!confirm("لاگِ جاری آرشیو شود و پروندهٔ تازه باز شود؟")) return;
  const d = await api("/api/admin/audit", { action: "reset" });
  logTo("log-audit", "ریست شد؛ آرشیو: " + d.archived);
  loadAudit();
}

window.loadAudit = loadAudit; window.copyAudit = copyAudit;
window.clearAudit = clearAudit; window.resetAudit = resetAudit;

/* ---------------------------------------------------- راه‌اندازی */

$("dev-credit").innerHTML = CREDIT;
window.addUser = addUser; window.loadUsers = loadUsers;
window.toggleUser = toggleUser; window.deleteUser = deleteUser;
window.setAdminCreds = setAdminCreds;
$("admin-id").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
$("admin-password").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
window.bootAdmin = async function bootAdmin() { await whoami(); if (token()) await loadUsers(); };
window.addEventListener("load", () => window.bootAdmin());
