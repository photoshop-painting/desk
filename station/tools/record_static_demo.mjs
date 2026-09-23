/* آزمون تعاملی رابط گرافیکی ایستگاه تصمیم مشتقه (گام‌های ۱ تا ۱۱).
   اجرا:  node test-interactive.mjs        (کارساز باید روی درگاه ۸۷۶۵ بالا باشد)
   این آزمون واقعاً دکمه‌ها را می‌زند و نتیجه را از خود صفحه می‌خواند. */
import { JSDOM, VirtualConsole, CookieJar } from "jsdom";
import fs from "node:fs";

/* ── ضبط پاسخ‌های واقعی برنامه برای ساخت «نمونهٔ ثابت نمایشی» ─────────────────
   همین آزمون، همان دکمه‌ها را می‌زند؛ ما در حاشیهٔ آن، هر پاسخ سرور را نگه می‌داریم تا
   بعداً یک صفحهٔ ایستا بسازیم که همان رابط را بدون سرور نشان می‌دهد. */
const DEMO_OUT = process.env.DEMO_OUT || "/tmp/demo-recording.json";
const RECORDING = {};
const SKIP_PATHS = ["/api/login", "/api/logout", "/api/gate/update"];
const key_of = (method, pathname) => (method || "GET").toUpperCase() + " " + pathname.split("?")[0];
function tap(url, method, res) {
  const pathname = new URL(url).pathname;
  if (SKIP_PATHS.some((p) => pathname.startsWith(p))) return;
  const k = key_of(method, pathname);
  const prev = RECORDING[k];
  if (prev && prev.status < 400) return;                       // پاسخ سالم را نگه دار، خطا را نه
  const text = res.clone().text();
  return text.then((body) => {
    RECORDING[k] = { status: res.status, ctype: res.headers.get("content-type") || "", body };
  }).catch(() => {});
}
function saveRecording() {
  try {
    fs.writeFileSync(DEMO_OUT, JSON.stringify(RECORDING, null, 1));
    console.log(`  ⌛ ضبط شد: ${Object.keys(RECORDING).length} پاسخ → ${DEMO_OUT}`);
  } catch (e) { console.log("  ! ضبط نشد: " + e.message); }
}
process.on("exit", saveRecording);

const BASE = process.env.STATION_URL || "http://127.0.0.1:8765";
// خوراک آزمایشی روی درگاه جداگانه سرو می‌شود؛ اگر ایستگاه روی درگاه دیگری باشد، همین را هم بدهید
const MOCK = process.env.STATION_MOCK_URL || "http://127.0.0.1:8788";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0;
const skip = (name, why) => { console.log(`  – ${name} (${why})`); };
const ok = (name, cond, extra = "") => {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name} ${extra}`); }
};

const vc = new VirtualConsole();
vc.on("jsdomError", (e) => { if (!/Could not load/.test(String(e))) console.log("  ! ", e.message); });

/* دروازهٔ ورود: اگر روشن باشد، آزمون مثل مدیر وارد می‌شود و کوکی نشست را با خود می‌برد
   (آزمون کارفرما در گام ۱۵ با کوکی جداگانه انجام می‌شود). */
const GATE_ADMIN_ID = process.env.STATION_ADMIN_ID || "mafhoom";
const GATE_ADMIN_PASS = process.env.STATION_ADMIN_PASS || "Smm@1101001";
const GUEST_ID = process.env.STATION_GUEST_ID || "";
const GUEST_PASS = process.env.STATION_GUEST_PASS || "";
const jar = new CookieJar();
const setCookies = (res) => (res.headers.getSetCookie ? res.headers.getSetCookie()
                                                      : [res.headers.get("set-cookie")]);
const withCookie = (opts = {}) => {            // کوکی نشست آزمون (مدیر) به هر درخواست
  const h = new Headers(opts.headers || {});
  const c = jar.getCookieStringSync(BASE);
  if (c) h.set("Cookie", c);
  return { ...opts, headers: h };
};
const gfetch = async (url, opts) => {
  const res = await fetch(url, withCookie(opts));
  tap(url, (opts && opts.method) || "GET", res);
  return res;
};

let gateStatus = {};
try { gateStatus = await (await gfetch(BASE + "/api/gate/status")).json(); } catch (e) { gateStatus = {}; }
const gateOn = !!gateStatus.enabled;
let adminLoggedIn = !gateOn;
if (gateOn) {
  const r = await fetch(BASE + "/api/login", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: GATE_ADMIN_ID, pass: GATE_ADMIN_PASS }) });
  for (const c of setCookies(r)) if (c) jar.setCookieSync(c, BASE);
  adminLoggedIn = r.ok;
  if (!adminLoggedIn) {
    console.log("  ! ورود مدیر انجام نشد؛ آزمون دروازه محدود می‌مانَد. پاسخ: " + r.status + " " +
                (await r.text()).slice(0, 90));
  }
}
console.log(`دروازه: ${gateOn ? "روشن" : "خاموش"} · ورود مدیر برای آزمون: `
            + `${adminLoggedIn ? "انجام شد" : "نشد"} · ${BASE}`);

const dom = await JSDOM.fromURL(BASE + "/", {
  runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole: vc,
  cookieJar: jar,
});
const { window } = dom;
// fetch در jsdom نیست؛ نسخهٔ node را با نشانی مطلق تزریق می‌کنیم (مثل خود مرورگر نسبت به میزبان)
window.fetch = (url, opts) => {
  const href = new URL(url, BASE).href;
  return fetch(href, withCookie(opts)).then((res) => {
    tap(href, (opts && opts.method) || "GET", res);
    return res;
  });
};
await new Promise((r) => window.addEventListener("load", r));
/* در jsdom، fetch تا لحظهٔ تزریق وجود ندارد؛ اگر boot زودتر اجرا شده باشد نیمه‌کاره مانده است */
if (!window.document.querySelectorAll("#nav a").length && typeof window.boot === "function") {
  try { await window.eval("boot()"); } catch (e) { console.log("  ! اجرای دوبارهٔ boot: " + e.message); }
}
/* jsdom پنجرهٔ confirm را پیاده نکرده است؛ در آزمون همیشه «بله» می‌گیریم
   تا مسیر «تأیید با رد سقف ریسک» هم آزموده شود. */
window.confirm = () => true;

const $ = (id) => window.document.getElementById(id);
const click = (fn) => window.eval(`${fn}()`);

async function waitFor(fn, ms = 8000, step = 120) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(step); }
  return false;
}

console.log("۱. بارگذاری و ناوبری");
ok("صفحه بالا آمد و app.js اجرا شد", typeof window.boot === "function" || typeof window.openAdminPanel === "function");
await waitFor(() => window.document.querySelectorAll("#nav a").length >= 11);
const navLinks = [...window.document.querySelectorAll("#nav a")].map((a) => a.textContent);
ok("یازده گام در نوار کنار ساخته شد", navLinks.length === 11, `(${navLinks.length})`);
ok("گام نهم «دفتر سرمایه‌گذار» است", /دفتر سرمایه‌گذار/.test(navLinks[8] || ""), navLinks[8]);
ok("گام دهم «آزمون کور سرمایه‌گذار» است", /آزمون کور/.test(navLinks[9] || ""), navLinks[9]);
ok("گام یازدهم «راهبردها و ریاضیِ پول» است", /راهبردها و ریاضی/.test(navLinks[10] || ""), navLinks[10]);
ok("یازده بخش گام‌ها در HTML هست", window.document.querySelectorAll("main section").length === 11);

console.log("۲. گام ۱ — خوش‌آمد و پنل مدیریت");
await waitFor(() => window.document.querySelectorAll("main section.active").length === 1, 10000);
ok("گام ۱ باز شد", $("s-health").classList.contains("active"),
   "فعال: " + ([...window.document.querySelectorAll("main section")].filter((x) => x.classList.contains("active")).map((x) => x.id).join(",") || "هیچ") + " · nav: " + window.document.querySelectorAll("#nav a").length);
ok("بخش‌های اداری از صفحهٔ کاربر برداشته شدند",
   !$("health-table") && !$("lic-client") && !$("usage-client") && !$("log-access"),
   "باید در پنل مدیریت باشند");
ok("دکمهٔ پنل مدیریت روی صفحه هست", /باز کردن پنل مدیریت/.test($("card-access").textContent));
ok("بیانیهٔ «سفارشی نمی‌فرستد» با صدای خود برنامه نوشته شده",
   /سفارش را خودتان/.test($("s-health").textContent));
ok("امضای دولوپر در پای صفحه هست",
   /مهندس مسعود مجربیان/.test(window.document.querySelector("footer").textContent));
const guard = await gfetch(BASE + "/api/health", { method: "POST",
  headers: { "Content-Type": "application/json" }, body: "{}" });
ok("بدون ورود، بررسی سلامت جواب نمی‌دهد", guard.status === 403, `(${guard.status})`);
const guardGet = await gfetch(BASE + "/api/health");
ok("بدون ورود، خواندن بررسی سلامت هم بسته است", guardGet.status === 403, `(${guardGet.status})`);
const guardUsage = await gfetch(BASE + "/api/usage", { method: "POST",
  headers: { "Content-Type": "application/json" }, body: '{"action":"summary"}' });
ok("بدون ورود، دفتر استفاده جواب نمی‌دهد", guardUsage.status === 403, `(${guardUsage.status})`);

console.log("۳. گام ۲ — دفتر اتصال و حالت داده");
await waitFor(() => ($("conn-select")?.options?.length || 0) >= 5);
const opts = [...$("conn-select").options].map((o) => o.textContent);
ok("فهرست پروفایل‌های اتصال پر شد", opts.length >= 5, `(${opts.length})`);
ok("خوراک آزمایشی محلی در فهرست است", opts.some((t) => /خوراک آزمایشی/.test(t)));
ok("اطلاعات پروفایل نمایش داده شد", /چه می‌دهد/.test($("conn-info").textContent));
$("conn-select").value = "mock-local";
$("conn-select").dispatchEvent(new window.Event("change"));
await sleep(400);
ok("قالب نشانی خوراک محلی در کادر نشست", ($("live-url").value || "").includes("8788"), $("live-url").value);
ok("مسیر JSON پیش‌فرض پر شد", ($("live-path").value || "").length > 0, $("live-path").value);

console.log("۴. گام ۲ — آزمایش اتصال و کاوشگر");
await click("testProfile");
await waitFor(() => /وضعیت:/.test($("log-data").textContent), 12000);
const dataLog = $("log-data").textContent;
ok("آزمایش اتصال نتیجه داد", /وضعیت:\s*(ok|partial)/.test(dataLog), dataLog.split("\n").pop());
ok("برچسب ساختگی بودن داده نشان داده شد", dataLog.includes("ساختگی") || ($("badge").textContent || "").includes("ساختگی"));
ok("نوار بالای صفحه به‌روز شد", /منبع:/.test($("badge").textContent), $("badge").textContent);
$("peek-url").value = MOCK + "/quote?symbol={symbol}";
await click("peekService");
await waitFor(() => ($("peek-result").textContent || "").includes("مسیرهای عددی"), 12000);
ok("کاوشگر پاسخ، مسیرهای عددی را پیدا کرد", $("peek-result").innerHTML.includes("data.0.pl"), $("peek-result").textContent.slice(0, 80));
window.eval("usePeekPath('data.0.pl')");
ok("دکمهٔ «استفاده» مسیر را در کادر گذاشت", $("live-path").value === "data.0.pl");

console.log("۴ب. گام ۲ — اتصال خودکار و فرم اعداد کارگزاری");
window.eval("autoConnect(false)");
await waitFor(() => /منبع رایگان|هیچ‌کدام/.test($("auto-result").textContent), 90000);
ok("اتصال خودکار گزارش داد", /منبع رایگان سالم پیدا شد|هیچ‌کدام از منابع رایگان/.test($("auto-result").textContent),
   $("auto-result").textContent.slice(0, 70));
ok("جدول دلیل هر منبع نمایش داده شد", $("auto-result").querySelectorAll("tbody tr").length >= 3,
   `(${$("auto-result").querySelectorAll("tbody tr").length})`);
ok("دلیل هر منبع نوشته شده", /پاسخ|مسیر|عدد|شبکه|کد نماد/.test($("auto-result").textContent));

await waitFor(() => window.document.querySelectorAll("#snap-table tbody tr").length >= 1, 8000);
const snapRowsBefore = window.document.querySelectorAll("#snap-table tbody tr").length;
window.eval("addSnapRow()");
ok("افزودن ردیف به فرم کار می‌کند", window.document.querySelectorAll("#snap-table tbody tr").length === snapRowsBefore + 1);
const tr = window.document.querySelector("#snap-table tbody tr");
tr.querySelector('[data-f="symbol"]').value = "اهرم";
tr.querySelector('[data-f="spot"]').value = "21500";
tr.querySelector('[data-f="future"]').value = "24900";
tr.querySelector('[data-f="days"]').value = "88";
tr.querySelector('[data-f="margin_per_contract"]').value = "20000000";
window.eval("saveSnapForm()");
await waitFor(() => /تیک|ذخیره شد|خطا/.test($("snap-problems").textContent), 10000);
ok("بدون تیک تأیید، ذخیره انجام نمی‌شود", /تیک/.test($("snap-problems").textContent),
   $("snap-problems").textContent.slice(0, 70));

console.log("۵. گام ۳ — تنظیمات ریاضی");
ok("کادرهای تنظیمات ساخته شد", $("rules-box").querySelectorAll("input").length >= 8);
$("rule-hurdle").value = "0.45";
await click("saveRules");
await waitFor(() => /ذخیره شد|خطا/.test($("log-settings").textContent));
ok("ذخیرهٔ تنظیمات جواب داد", /ذخیره شد/.test($("log-settings").textContent), $("log-settings").textContent.slice(0, 60));

console.log("۶. گام ۴ — دیده‌بان کدال");
await click("runKodalDemo");
await waitFor(() => /هشدار ساخته/.test($("log-news").textContent), 12000);
ok("دیده‌بان روی دادهٔ نمونه اجرا شد", /هشدار ساخته/.test($("log-news").textContent));

console.log("۷. گام ۵ — اجرا و محاسبه");
await click("doRun");
await waitFor(() => $("run-kpis").querySelectorAll(".kpi").length >= 4, 15000);
const kpis = [...$("run-kpis").querySelectorAll(".kpi")].map((k) => k.textContent.replace(/\s+/g, " "));
ok("کارت‌های خلاصهٔ محاسبه پر شد", kpis.length >= 4, `(${kpis.length})`);
ok("لاگ محاسبه سیگنال نشان داد", /بازده/.test($("log-run").textContent), $("log-run").textContent.slice(0, 80));

console.log("۸. گام ۶ — جدول سیگنال‌ها و تصمیم");
await waitFor(() => window.document.querySelectorAll("#signals-table tbody tr").length >= 2, 8000);
const rows = window.document.querySelectorAll("#signals-table tbody tr");
ok("جدول سیگنال‌ها پر شد", rows.length >= 2, `(${rows.length})`);
/* ردیفِ «منتظر تأیید» را برمی‌داریم؛ اگر آزمون دوباره اجرا شود، ردیف تأییدشدهٔ دفعهٔ پیش را برنمی‌داریم */
const pickPending = () => [...window.document.querySelectorAll("#signals-table tbody tr")]
  .find((tr) => /منتظر تأیید/.test(tr.textContent));
let pendingRow = pickPending();
if (!pendingRow) { await click("doRun"); await waitFor(() => !!pickPending(), 20000); pendingRow = pickPending(); }
(pendingRow || rows[0]).dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
await sleep(200);
ok("انتخاب ردیف، جزئیات را نشان داد", /جزئیات ریاضی/.test($("log-decide").textContent));
window.eval("decide('approved')");
await waitFor(() => /تأیید شد|خطا|بستهٔ سفارش/.test($("log-decide").textContent), 8000);
ok("تأیید سیگنال انجام شد", /تأیید شد/.test($("log-decide").textContent), $("log-decide").textContent.split("\n").pop());
await waitFor(() => $("packet-card").style.display !== "none" && ($("packet").textContent || "").length > 10, 8000);
ok("بستهٔ سفارش ساخته شد", $("packet-card").style.display !== "none" && ($("packet").textContent || "").length > 10,
   "برگشت: " + $("log-decide").textContent.split("\n").pop().slice(0, 70));

console.log("۸ب. گام ۶ — داوری سیگنال ابزارهای دیگر");
window.eval("showStep(5)");
await click("judgePreset");
ok("نمونهٔ آماده در کادر ورودی نشست", ($("judge-params").value || "").includes("spot"), $("judge-params").value.slice(0, 40));
window.eval("judgeSignal(true)");
await waitFor(() => ($("judge-kpis").textContent || "").includes("اثر انگشت"), 20000);
const jk = $("judge-kpis").textContent;
ok("داوری انجام شد و کارت‌های خلاصه پر شد", /داوری/.test(jk) && /اثر انگشت/.test(jk), jk.slice(0, 70));
ok("گزارش دروازه‌ها در لاگ آمد", /✓|✗/.test($("log-judge").textContent), $("log-judge").textContent.slice(-80));
ok("نقطهٔ برگشت گزارش شد", /نقطهٔ برگشت/.test($("log-judge").textContent));
ok("مارجین‌کال گزارش شد", /مارجین‌کال|وجه تضمین/.test($("log-judge").textContent));
ok("دو روش حساب گزارش شد", /دو روش حساب/.test($("log-judge").textContent));
ok("برگهٔ داوری ساخته شد", /signal-verdict\.html/.test($("log-judge").textContent));
$("judge-params").value = '{"call":420,"put":380,"spot":9000,"strike":9000,"days":30}';
$("judge-kind").value = "parity";
window.eval("judgeSignal(true)");
await waitFor(() => /می‌افتد/.test($("judge-kpis").textContent), 20000);
ok("سیگنال غیرقابل‌اجرا رد شد", /می‌افتد/.test($("judge-kpis").textContent), $("judge-kpis").textContent.slice(0, 60));
ok("دلیل رد گفته شد", /استقراضی|جهت/.test($("log-judge").textContent));

console.log("۹. گام ۷ — پس‌آزمایی");
await click("makeHistTemplate");
await sleep(500);
ok("قالب ستون‌های تاریخ ساخته شد", ($("hist-path").value || "").length > 0, $("hist-path").value);
$("hist-path").value = "demo/history-demo.csv";
await click("doBacktest");
await waitFor(() => ($("bt-kpis").textContent || "").includes("نرخ برد"), 15000);
const bt = $("bt-kpis").textContent;
ok("کارت‌های پس‌آزمایی پر شد", bt.includes("خطای پیش‌بینی"));
ok("درس خطای پیش‌بینی نوشته شد", /خوش‌بین|درس/.test($("log-bt").textContent), $("log-bt").textContent.slice(-70).trim());

console.log("۱۰. گام ۸ — بستهٔ تحویل شرکت");
await click("doBundle");
await waitFor(() => /بسته ساخته شد/.test($("log-bundle").textContent), 15000);
ok("بسته ساخته شد", /بسته ساخته شد/.test($("log-bundle").textContent));
ok("فهرست پرونده‌های بسته نمایش داده شد", $("bundle-list").querySelectorAll("tr").length >= 5);
const methodRes = await gfetch(BASE + "/files/method");
const methodTxt = await methodRes.text();
ok("سند روش کار نمایش‌پذیر است و همان‌جا ساخته می‌شود",
   methodRes.status === 200 && /سند روش کار/.test(methodTxt), `(${methodRes.status})`);
$("offer-client").value = "نمونهٔ نمایشی";
await click("buildOffer");
await waitFor(() => /پیشنهاد ساخته شد/.test($("log-bundle").textContent), 20000);
ok("پیشنهاد یک‌صفحه‌ای ساخته شد", /one-pager\.html/.test($("log-bundle").textContent),
   $("log-bundle").textContent.split("\n").slice(-2).join(" | ").slice(0, 90));
ok("برگه می‌گوید قیمت توافقی است (عدد خودساخته نمی‌گذارد)",
   /توافقی/.test($("log-bundle").textContent));
$("outreach-kind").value = "brokerage";
await click("buildOutreach");
await waitFor(() => /پیام‌ها ساخته شد/.test($("log-bundle").textContent), 20000);
ok("پیام‌های معرفی ساخته شد", /outreach-pack\.md/.test($("log-bundle").textContent),
   $("log-bundle").textContent.split("\n").slice(-3).join(" | ").slice(0, 90));
ok("قاعدهٔ پیگیری سه‌باره در لاگ گفته شد", /سه بار/.test($("log-bundle").textContent));

/* ---- برگهٔ روز اول مشتری (بعد از «بله») ---- */
$("onboard-start").value = "2026-09-22";
await click("buildOnboarding");
await waitFor(() => /onboarding-pack\.html/.test($("log-bundle").textContent), 20000);
ok("برگهٔ روز اول مشتری ساخته شد", /onboarding-pack\.html/.test($("log-bundle").textContent),
   $("log-bundle").textContent.split("\n").slice(-2).join(" | ").slice(0, 90));
const onbRes = await gfetch(BASE + "/files/onboarding");
const onbTxt = await onbRes.text();
ok("برگهٔ روز اول باز می‌شود و نام مشتری و روز بازبینی رویش است",
   onbRes.status === 200 && /روز اول/.test(onbTxt) && /نمونهٔ نمایشی/.test(onbTxt)
   && /۲۰۲۶-۱۰-۰۶/.test(onbTxt), `(${onbRes.status})`);
ok("پنج کار روز اول و شرط‌های کارنامه روی برگه است",
   /license\.py --grant/.test(onbTxt) && /کارنامه|نام‌دار/.test(onbTxt)
   && /زنجیرهٔ هش/.test(onbTxt));
ok("مرز صادقانه روی برگهٔ روز اول نوشته شده", /هیچ سود تضمینی/.test(onbTxt));
const onbMd = await (await gfetch(BASE + "/files/onboarding-md")).text();
let badClaim = null;
for (const m of onbMd.matchAll(/تضمین/g)) {
  const before = onbMd.slice(Math.max(0, m.index - 6), m.index);
  if (before.endsWith("وجه ")) continue;                 // «وجه تضمین» اصطلاح بازار است
  if (!/هیچ/.test(onbMd.slice(Math.max(0, m.index - 20), m.index))) badClaim = m.index;
}
ok("روی برگهٔ روز اول هیچ وعدهٔ تضمینی نیست", badClaim === null && /توافقی/.test(onbMd));

/* ---- جلسهٔ بازبینی دو هفته‌ای: سه شاهد، دو خروجی، یک تصمیم ---- */
await click("buildReviewMeeting");
await waitFor(() => /review-meeting\.html/.test($("log-bundle").textContent), 20000);
ok("برگهٔ جلسهٔ بازبینی ساخته شد", /review-meeting\.html/.test($("log-bundle").textContent)
   && /روز بازبینی/.test($("log-bundle").textContent),
   $("log-bundle").textContent.split("\n").slice(-3).join(" | ").slice(0, 96));
const rvRes = await gfetch(BASE + "/files/review-meeting");
const rvTxt = await rvRes.text();
ok("برگهٔ بازبینی باز می‌شود و سه شاهد رویش است",
   rvRes.status === 200 && /سه شاهد/.test(rvTxt) && /selftest\.py/.test(rvTxt)
   && /usage_meter\.py --summary --verify/.test(rvTxt) && /نمونهٔ نمایشی/.test(rvTxt),
   `(${rvRes.status})`);
ok("پنج شرط کارنامه و دو خروجی و روز بازبینی رویش است",
   /تداوم روزانه/.test(rvTxt) && /خروجی دو — توقف/.test(rvTxt) && /۲۰۲۶-۱۰-۰۶/.test(rvTxt));
ok("پیگیری تاریخ‌دار و مرز صادقانه رویش است",
   /--next-on ۲۰۲۶|--next-on 2026/.test(rvTxt) && /هیچ سود تضمینی/.test(rvTxt)
   && /هیچ درصدی از سود/.test(rvTxt));
const rvMd = await (await gfetch(BASE + "/files/review-meeting-md")).text();
ok("روی برگهٔ بازبینی هیچ فوریت ساختگی و هیچ وعدهٔ تضمینی نیست",
   !/فرصت محدود|فقط امروز|فوری اقدام/.test(rvMd) && /هیچ/.test(rvMd) && /توافقی/.test(rvMd));
/* نام یکتا تا اجرای دوبارهٔ آزمون روی همان دفتر، «نام تکراری» نگیرد */
const PNAME = "کارگزاری نمونه " + String(Date.now()).slice(-4);
const plog = () => ($("log-prospects").textContent || "").replace(/\s+/g, " ").slice(-90);
$("prospect-name").value = PNAME;
$("prospect-kind").value = "brokerage";
$("prospect-channel").value = "phone";
await click("prospectAdd");
await waitFor(() => /به تابلو اضافه شد/.test($("log-prospects").textContent), 20000);
ok("مخاطب به تابلو اضافه شد", /به تابلو اضافه شد/.test($("log-prospects").textContent), plog());
ok("کارت‌های سه عدد هفته پر شد", /پیام این هفته/.test($("prospect-kpis").textContent),
   $("prospect-kpis").textContent.replace(/\s+/g, " ").slice(0, 70));
$("prospect-name").value = PNAME;
$("prospect-date").value = "2026-09-01";
// دکمهٔ «پیام اول رفت» پارامتر دارد؛ پس تابع را مستقیم صدا می‌زنیم
await window.prospectMark("sent");
await waitFor(() => /پیام اول ثبت شد/.test($("log-prospects").textContent), 15000);
ok("پیام اول ثبت شد", /پیام اول ثبت شد/.test($("log-prospects").textContent), plog());
$("prospect-name").value = PNAME;
$("prospect-date").value = "2026-09-05";
$("prospect-name").value = PNAME;
await window.prospectMark("followup");
await waitFor(() => /پیگیری ثبت شد/.test($("log-prospects").textContent), 15000);
ok("پیگیری ثبت شد", /پیگیری ثبت شد/.test($("log-prospects").textContent), plog());

/* ---- مراسم فروش امروز: تابلو + متن آماده، در بیست دقیقه ---- */
$("ritual-sender").value = "مسعود";
await click("buildSalesRitual");
await waitFor(() => /sales-today\.html/.test($("log-ritual").textContent), 20000);
ok("مراسم فروش امروز ساخته شد", /sales-today\.html/.test($("log-ritual").textContent)
   && /از ۲۰ دقیقه/.test($("log-ritual").textContent),
   $("log-ritual").textContent.replace(/\s+/g, " ").slice(0, 90));
ok("برنامه روی تابلو بسته شد و تماس تلفنی درست شمرده شد",
   /۱ تماس/.test($("log-ritual").textContent) && new RegExp(PNAME).test($("log-ritual").textContent),
   $("log-ritual").textContent.replace(/\s+/g, " ").slice(-90));
const rtRes = await gfetch(BASE + "/files/sales-today");
const rtTxt = await rtRes.text();
ok("برگهٔ امروز باز می‌شود و متن آمادهٔ همان مخاطب رویش است",
   rtRes.status === 200 && rtTxt.includes(PNAME) && /۴۰ ثانیهٔ اول تماس/.test(rtTxt),
   `(${rtRes.status})`);
ok("برگهٔ امروز، تیک‌های اجرا و سقف‌های قفل‌شده را دارد",
   /فرستادم ☐/.test(rtTxt) && /۵ پیام/.test(rtTxt) && /بیست‌دقیقه|۲۰ دقیقه/.test(rtTxt));
ok("روی برگهٔ امروز هیچ عدد سود و هیچ فوریت ساختگی نیست",
   !/٪/.test(rtTxt) && !/فرصت محدود|فقط امروز|فوری اقدام/.test(rtTxt));
$("prospect-name").value = PNAME;
await click("prospectSheet");
await waitFor(() => /prospects-board\.html/.test($("log-prospects").textContent), 20000);
ok("برگهٔ تابلوی پیگیری ساخته شد", /prospects-board\.html/.test($("log-prospects").textContent), plog());
const boardRes = await gfetch(BASE + "/files/prospects");
const boardTxt = await boardRes.text();
ok("برگهٔ تابلو باز می‌شود و قاعدهٔ پیگیری را دارد",
   boardRes.status === 200 && /تابلوی پیگیری/.test(boardTxt) && /روز ۰/.test(boardTxt),
   `(${boardRes.status})`);
$("prospect-name").value = PNAME;
$("prospect-result").value = "نه";
await click("prospectOutcome");
await waitFor(() => /نتیجهٔ جلسه ثبت شد/.test($("log-prospects").textContent), 15000);
ok("نتیجهٔ جلسه ثبت شد", /نتیجهٔ جلسه ثبت شد/.test($("log-prospects").textContent), plog());
$("prospect-date").value = "";
await click("prospectClose");
await waitFor(() => /بسته شد/.test($("log-prospects").textContent), 15000);
ok("پرونده بسته شد", /بسته شد/.test($("log-prospects").textContent), plog());

const outreachRes = await gfetch(BASE + "/files/outreach");
const outreachTxt = await outreachRes.text();
ok("برگهٔ پیام‌ها باز می‌شود و لحن کارگزاری را دارد",
   outreachRes.status === 200 && /پیام‌های معرفی/.test(outreachTxt) && /کارگزاری/.test(outreachTxt),
   `(${outreachRes.status})`);
ok("در برگهٔ پیام‌ها هیچ درصدی و هیچ عدد سودی نیست", !/٪|درصد/.test(outreachTxt));
ok("مرز صادقانه (بدون سود تضمینی) روی برگه نوشته شده", /هیچ سود تضمینی/.test(outreachTxt));
const offerRes = await gfetch(BASE + "/files/offer");
const offerTxt = await offerRes.text();
ok("برگهٔ پیشنهاد برای چاپ باز می‌شود",
   offerRes.status === 200 && /پیشنهاد یک‌صفحه‌ای/.test(offerTxt) && /نمونهٔ نمایشی/.test(offerTxt),
   `(${offerRes.status})`);
const walkRes = await gfetch(BASE + "/files/walkthrough");
const walkTxt = await walkRes.text();
ok("راهنمای هر بخش برای تازه‌کار سرو می‌شود",
   walkRes.status === 200 && /راهنمای هر بخش/.test(walkTxt), `(${walkRes.status})`);
ok("راهنمای تازه‌کار از گام ۲ باز می‌شود",
   /راهنمای هر بخش \(برای تازه‌کار\)/.test($("s-data").textContent));
ok("راهنمای تازه‌کار از گام ۹ هم باز می‌شود",
   /راهنمای هر بخش، برای تازه‌کار/.test($("s-trial").textContent));

console.log("۱۱. گام ۹ — دفتر آزمون زنده");
$("trial-note").value = "آزمون تعاملی خودکار";
await click("recordTrial");
await waitFor(() => /ردیف ثبت شد/.test($("log-trial").textContent), 10000);
ok("ثبت در دفتر انجام شد", /ردیف ثبت شد/.test($("log-trial").textContent), $("log-trial").textContent.split("\n")[1] || "");
await waitFor(() => window.document.querySelectorAll("#trial-table tbody tr").length >= 1, 8000);
ok("جدول دفتر پر شد", window.document.querySelectorAll("#trial-table tbody tr").length >= 1);
await click("markTrial");
await waitFor(() => /بازسنجی شد/.test($("log-trial").textContent), 20000);
ok("بازسنجی با قیمت تازه انجام شد", /بازسنجی شد/.test($("log-trial").textContent));
ok("وضعیت‌های بازسنجی در دفتر آمد", /بازتر شد|کم شد|تقریباً ثابت|زیر کف رفت|دادهٔ تازه نبود/.test($("trial-table").textContent));
await click("verifyChain");
await waitFor(() => /زنجیرهٔ/.test($("log-trial").textContent), 8000);
ok("زنجیرهٔ هش بررسی شد و سالم است", /سالم است/.test($("log-trial").textContent), $("log-trial").textContent.slice(-60).trim());
await click("makeTrialReport");
await waitFor(() => /گزارش ساخته شد/.test($("log-trial").textContent), 12000);
ok("گزارش سرمایه‌گذار ساخته شد", /گزارش ساخته شد/.test($("log-trial").textContent));
ok("کارت‌های خلاصهٔ دفتر پر شد", $("trial-kpis").querySelectorAll(".kpi").length >= 5);

console.log("۱۲. گام ۹ — مراسم روزانه و کارنامه");
$("daily-note").value = "اجرای آزمایشی هنگام تحویل برنامه";
await click("runDaily");
await waitFor(() => /امروز \d{4}-/.test($("log-trial").textContent), 30000);
ok("مراسم امروز با یک دکمه اجرا شد", /امروز \d{4}-/.test($("log-trial").textContent), $("log-trial").textContent.slice(-70).trim());
ok("منبع داده در لاگ مراسم آمد", /منبع:/.test($("log-trial").textContent));
ok("هشدار دادهٔ ساختگی نوشته شد", /ساختگی/.test($("log-trial").textContent));
await waitFor(() => $("score-kpis").querySelectorAll(".kpi").length >= 6, 8000);
ok("کارت‌های کارنامه پر شد", $("score-kpis").querySelectorAll(".kpi").length >= 6, `(${$("score-kpis").querySelectorAll(".kpi").length})`);
ok("پنج شرط کارنامه نمایش داده شد", window.document.querySelectorAll("#score-table tbody tr").length === 5, `(${window.document.querySelectorAll("#score-table tbody tr").length})`);
ok("کارنامه وضعیت «ناتمام» را می‌گوید (فقط یک روز گذشته)", /هنوز نه|آماده/.test($("score-verdict").textContent), $("score-verdict").textContent.slice(0, 60));
ok("تاریخ اجراها ثبت شد", /اجرای آزمایشی هنگام تحویل/.test($("runs-list").textContent));
ok("گزارش سرمایه‌گذار ساخته شد", /گزارش سرمایه‌گذار به‌روز شد/.test($("log-trial").textContent));

console.log("۱۲ب. گام ۹ — آزمون ۱۰ دقیقه‌ای و پروندهٔ سرمایه‌گذار");
await click("runSelftest");
await waitFor(() => ($("exam-kpis").textContent || "").includes("مورد سبز"), 30000);
const examKpis = $("exam-kpis").textContent;
ok("کارت‌های آزمون پر شد", examKpis.includes("مورد سبز") && examKpis.includes("اثر انگشت موتور"), examKpis.slice(0, 60));
const examRows = window.document.querySelectorAll("#exam-table tbody tr").length;
ok("جدول آزمون سطرهای واقعی دارد", examRows >= 12, `(${examRows} سطر)`);
ok("هیچ مورد سرخی در آزمون نیست", window.document.querySelectorAll("#exam-table tr.red-row").length === 0, $("exam-table").textContent.replace(/\s+/g, " ").slice(0, 80));
ok("حساب مستقل در متن هر مورد آمده", /چک با ماشین‌حساب|حساب دستی/.test($("log-trial").textContent) || $("exam-table").textContent.includes("="));
ok("اثر انگشت موتور ریاضی گزارش شد", /اثر انگشت/.test($("log-trial").textContent));
await click("buildDossier");
await waitFor(() => ($("dossier-info").textContent || "").includes("ساخته شد"), 40000);
ok("پروندهٔ سرمایه‌گذار ساخته شد", /ساخته شد/.test($("dossier-info").textContent), $("dossier-info").textContent.slice(-90).trim());
ok("اثر انگشت پرونده نوشته شد", /اثر انگشت پرونده:/.test($("dossier-info").textContent));
ok("وضعیت زنجیره در پرونده گزارش شد", /زنجیرهٔ دفتر:/.test($("dossier-info").textContent));
ok("نسخهٔ متنی پرونده هم ساخته شد", /investor-dossier\.md/.test($("dossier-info").textContent));

console.log("۱۳ب. گام ۱۰ — آزمون کور سرمایه‌گذار");
window.eval("showStep(9)");
await click("loadCases");
await waitFor(() => window.document.querySelectorAll("#blind-list .card").length >= 6, 20000);
const blindCards = window.document.querySelectorAll("#blind-list .card").length;
ok("شش پرسش کور نمایش داده شد", blindCards === 6, `(${blindCards})`);
ok("کادر حدس برای هر پرسش ساخته شد", !!$("guess-basis_annual") && !!$("guess-parity_yn"));
ok("پاسخ برنامه در فهرست پرسش‌ها پنهان مانده", !/پاسخ برنامه/.test($("blind-list").textContent));
// مقدارِ «حدس» را از داراییِ خود پرسش‌ها می‌خوانیم تا آزمون با تغییر داده نشکند
const revealed = await (await gfetch(BASE + "/api/investor/blind", { method: "POST",
  headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reveal: true }) })).json();
const basisAns = (revealed.cases.find((c) => c.id === "basis_annual") || {}).answer;
ok("پرسش کور با آشکارسازی هم پاسخ دارد", basisAns != null, String(basisAns));
$("guess-basis_annual").value = String(basisAns);
$("guess-parity_yn").value = "خیر";
await click("checkGuesses");
await waitFor(() => ($("res-basis_annual").textContent || "").includes("پاسخ برنامه"), 30000);
ok("داوری حدس عددی انجام شد", /دقیقاً درست/.test($("res-basis_annual").textContent), $("res-basis_annual").textContent.slice(0, 70));
ok("داوری حدس بله/خیر انجام شد", /داوری: (درست|نادرست)/.test($("res-parity_yn").textContent), $("res-parity_yn").textContent.slice(0, 50));
ok("فرمول و روش دوم نشان داده شد", /فرمول:/.test($("res-basis_annual").textContent) && /روش دوم/.test($("res-basis_annual").textContent));
ok("ثبت در دفتر زنجیره‌هش‌دار گزارش شد", /ثبت شد/.test($("log-blind").textContent), $("log-blind").textContent.slice(-60));
await click("loadLadder");
await waitFor(() => window.document.querySelectorAll("#ladder-box tbody tr").length >= 5, 20000);
ok("جدول آستانهٔ ریزش ساخته شد", window.document.querySelectorAll("#ladder-box tbody tr").length >= 5,
   `(${window.document.querySelectorAll("#ladder-box tbody tr").length})`);
ok("جدول اندازهٔ موقعیت هم آمد", /اندازهٔ موقعیت/.test($("ladder-box").textContent));
$("rec-symbol").value = "فولاد"; $("rec-entry").value = "7000"; $("rec-exit").value = "7400";
$("rec-days").value = "30"; $("rec-units").value = "100"; $("rec-expected").value = "";
await click("doReconcile");
await waitFor(() => /سود\/زیان/.test($("log-rec").textContent), 20000);
ok("حساب‌رسی واقعیت با کارمزد انجام شد", /سود\/زیان/.test($("log-rec").textContent), $("log-rec").textContent.slice(0, 80));
ok("زنجیره پس از حساب‌رسی سالم است", /زنجیره: سالم/.test($("log-rec").textContent));
await click("buildBlindSheet");
await waitFor(() => /برگهٔ آزمون ساخته شد/.test($("log-blind").textContent), 25000);
ok("برگهٔ آزمون کور ساخته شد", /investor-blind-test\.html/.test($("log-blind").textContent));
await click("verifyBlindChain");
await waitFor(() => /زنجیره:/.test($("log-blind").textContent.split("ساخته شد").pop() || ""), 15000);
ok("بررسی زنجیرهٔ هش کار کرد", /زنجیره: سالم/.test($("log-blind").textContent), $("log-blind").textContent.slice(-70));

console.log("۱۲ب. گام ۱ و ۲ — راهنمای ورودی روزانه (پنل مدیریت جدا آزموده می‌شود)");
ok("دکمه‌های راهنمای ورودی روزانه هست", /هر روز چه عددی بگیرم/.test($("card-snap").textContent));

console.log("۱۲ج. گام ۲ — چسباندن اعداد کارگزاری");
window.eval("showStep(1)");
ok("راهنمای ستون‌به‌ستون در کارت هست", /راهنمای ستون/.test($("card-snap").textContent));
const rowsBefore = window.document.querySelectorAll("#snap-table tbody tr").length;
$("snap-paste").value = "فولاد , covered_call , 7000 , 7600 , 400 , 45 , 7000 , 160 , 1.8\n" +
                        "کگل , قیمت سهم , پوت , اعمال , روز , 9800 , 40 , 14210 , 365";
await click("importPaste");
await waitFor(() => /ردیف خوانده/.test($("paste-report").textContent), 20000);
const rowsAfter = window.document.querySelectorAll("#snap-table tbody tr").length;
ok("اعداد چسبانده‌شده به جدول اضافه شدند", rowsAfter >= rowsBefore + 2, `(${rowsBefore}→${rowsAfter})`);
ok("گزارش تشخیص، شفاف نوشته شد", /ردیف خوانده/.test($("paste-report").textContent) && /· |✗ /.test($("paste-report").textContent),
   $("paste-report").textContent.slice(-60));

console.log("۱۲د. گام ۱۰ — پلهٔ تصمیم، پیمان‌نامه و کارنامهٔ جلسه");
window.eval("showStep(9)");
await click("loadLadder");
await waitFor(() => /سند پلهٔ تصمیم/.test($("ladder-box").textContent), 25000);
ok("سند پلهٔ تصمیم با خلاصهٔ ردیف‌ها ساخته شد", /سند پلهٔ تصمیم:.*قابل اجرا/.test($("ladder-box").textContent),
   $("ladder-box").textContent.slice(-90));
ok("نقطهٔ برگشت هر ردیف در جدول آمد", /می‌گذرد|می‌افتد/.test($("ladder-box").textContent));
$("blind-client").value = "سرمایه‌گذار نمونه";
await click("makePledge");
await waitFor(() => /پیمان‌نامهٔ نمایش ساخته شد/.test($("log-blind").textContent), 20000);
ok("پیمان‌نامهٔ دواِمضا ساخته شد", /پیمان‌نامهٔ نمایش ساخته شد/.test($("log-blind").textContent));
ok("زنجیرهٔ هش در همان گزارش بررسی شد", /زنجیره: سالم|زنجیره: شکسته/.test($("log-blind").textContent));
await click("buildBlindSheet");
await waitFor(() => /investor-blind-test\.html/.test($("log-blind").textContent), 25000);
ok("برگه با نام سرمایه‌گذار و کارنامهٔ جلسه ساخته شد", /پرسش سنجیده شد/.test($("log-blind").textContent),
   $("log-blind").textContent.slice(-80));

console.log("۱۲هـ. گام ۲ — برگهٔ شاهد زنده (برای سرمایه‌گذار/کارفرما)");
window.eval("showStep(1)");
ok("دکمه‌های برگهٔ شاهد در گام ۲ هست", /برگهٔ شاهد زنده/.test($("s-data").textContent));
await click("makeWitness");
await waitFor(() => /اثر انگشت برگه/.test($("witness-box").textContent), 60000);
const wit = $("witness-box").textContent;
ok("برگهٔ شاهد ساخته شد", /اثر انگشت برگه: [0-9a-f]{16}/.test(wit), wit.slice(0, 90));
ok("قیمت‌ها همین حالا از سرویس خوانده شد", /\d+ از \d+ قیمت( زنده)? خوانده شد/.test(wit), wit.slice(0, 90));
ok("هشدار صداقت یا تصمیم نمونه گزارش شد", /هشدار صداقت|تصمیم نمونه/.test(wit), wit.slice(-90));

console.log("۱۲و. گام ۱۱ — راهبردها، شوک‌آزمون و ریاضیِ پول");
window.eval("showStep(10)");
ok("بخش گام ۱۱ فعال شد", $("s-math").classList.contains("active"));
ok("کارت‌های گام ۱۱ در صفحه هست", /جزوهٔ راهبردها/.test($("s-math").textContent)
   && /شوک‌آزمون/.test($("s-math").textContent) && /ریاضیِ پول/.test($("s-math").textContent));
await click("buildStrategies");
await waitFor(() => /تاب‌آوری/.test($("strategy-table").textContent), 90000);
const stTxt = $("strategy-table").textContent;
ok("جدول راهبردها ساخته شد", /مبنا|پوشش/.test(stTxt), stTxt.slice(0, 80));
ok("حالت خنثی شوک‌آزمون با موتور یکی است", /موتور ✅/.test(stTxt) && !/ناهم‌خوان/.test(stTxt),
   stTxt.slice(-70));
ok("دسته‌بندی سخت‌جان/لبِ مرز/افتاده آمد", /سخت‌جان:/.test(stTxt) && /افتاده:/.test(stTxt));
await click("buildStress");
await waitFor(() => /تحمل کارمزد/.test($("stress-table").textContent), 90000);
ok("برگهٔ شوک‌آزمون با ستون تحمل کارمزد ساخته شد", /٪/.test($("stress-table").textContent),
   $("stress-table").textContent.slice(0, 60));
await click("buildBankroll");
await waitFor(() => /کم‌ترین نرخ برد لازم/.test($("bankroll-box").textContent), 120000);
const bk = $("bankroll-box").textContent;
ok("ریاضیِ پول: کسر کِلی و نصف‌کِلی آمد", /کِلی/.test(bk) && /نصف/.test(bk), bk.slice(0, 90));
ok("ریاضیِ پول: احتمال نیم‌شدن حساب آمد", /نیم‌شدن حساب/.test(bk));
ok("ریاضیِ پول: مسیر راهبرد با کارمزد و چرخش آمد", /مسیر راهبرد/.test(bk) && /خالص/.test(bk));
ok("هشدار صداقت در کارت ریاضی هست", /وعدهٔ سود نیست/.test(bk) || /وعدهٔ سود/.test(bk));

console.log("۱۳. ناوبری گام‌ها");
window.eval("showStep(8)");
ok("پرش به گام نهم کار کرد", $("s-trial").classList.contains("active"));
window.eval("showStep(9)");
ok("پرش به گام دهم کار کرد", $("s-blind").classList.contains("active"));
window.eval("go(-1)");
ok("دکمهٔ گام قبل کار کرد", $("s-trial").classList.contains("active"));
window.eval("showStep(10)");
ok("پرش به گام یازدهم کار کرد", $("s-math").classList.contains("active"));
window.eval("go(-1)");
ok("دکمهٔ گام قبل از گام ۱۱ کار کرد", $("s-blind").classList.contains("active"));

/* ---------------------------------------------- ۱۴. پنل مدیریت (ورود و سه بخش) */
console.log("۱۴. پنل مدیریت");

const ADMIN_ID = process.env.STATION_ADMIN_ID || "mafhoom";
const ADMIN_PASS = process.env.STATION_ADMIN_PASS || "Smm@1101001";

const adminDom = await JSDOM.fromURL(BASE + "/admin", {
  runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole: vc,
  cookieJar: jar,
});
const aw = adminDom.window;
aw.fetch = (url, opts) => fetch(new URL(url, BASE).href, withCookie(opts));
aw.confirm = () => true;
await new Promise((r) => aw.addEventListener("load", r));
const a$ = (id) => aw.document.getElementById(id);
const aclick = (fn) => aw.eval(`${fn}()`);
async function awaitFor(fn, ms = 20000, step = 150) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (fn()) return true; await sleep(step); }
  return false;
}

ok("صفحهٔ پنل بالا آمد", typeof aw.doLogin === "function");
ok("کارت ورود نشان داده می‌شود و بخش‌ها پنهان‌اند",
   !a$("login-card").classList.contains("hidden") && a$("admin-area").classList.contains("hidden"));
ok("امضای دولوپر در پنل هست", /مهندس مسعود مجربیان/.test(a$("dev-credit").textContent));

a$("admin-id").value = ADMIN_ID;
a$("admin-password").value = "رمزغلط۱۲۳۴";
await aclick("doLogin");
await awaitFor(() => /ورود ناموفق/.test(a$("login-box").textContent), 15000);
ok("رمز غلط رد می‌شود", /ورود ناموفق/.test(a$("login-box").textContent),
   a$("login-box").textContent.slice(-60));

a$("admin-id").value = ADMIN_ID;
a$("admin-password").value = ADMIN_PASS;
await aclick("doLogin");
await awaitFor(() => !a$("admin-area").classList.contains("hidden"), 15000);
ok("ورود درست انجام شد و پنل باز شد", !a$("admin-area").classList.contains("hidden"));
ok("وضعیت ورود در سرصفحه گزارش شد", /وارد شده‌اید/.test(a$("who").textContent));

await aclick("doHealth");
await awaitFor(() => (a$("health-table").innerHTML || "").includes("<table"), 30000);
ok("۱) جدول سلامت در پنل پر شد", a$("health-table").innerHTML.includes("<table"));
ok("۱) خلاصهٔ سلامت نوشته شد", /سالم|از .* جزء|از ۸|از 8/.test(a$("log-health").textContent),
   a$("log-health").textContent.slice(-50));

await aclick("licenseStatus");
await awaitFor(() => /وضعیت مجوز خوانده شد/.test(a$("log-access").textContent), 15000);
ok("۲) وضعیت مجوز خوانده شد", /وضعیت مجوز/.test(a$("log-access").textContent));
a$("lic-client").value = "نمونهٔ نمایشی";
a$("lic-months").value = "6";
await aclick("grantLicense");
await awaitFor(() => /مجوز نام‌دار صادر شد/.test(a$("log-access").textContent), 20000);
ok("۲) مجوز نام‌دار صادر شد", /مجوز نام‌دار صادر شد/.test(a$("log-access").textContent),
   a$("log-access").textContent.slice(-70));
ok("۲) وضعیت مجوز پس از صدور نمایش داده شد", /نمونهٔ نمایشی/.test(a$("license-state").textContent));

await aclick("licenseDocument");
await awaitFor(() => /license-doc\.html/.test(a$("log-access").textContent), 30000);
ok("۲) سند چاپی مجوز ساخته شد", /license-doc\.html/.test(a$("log-access").textContent),
   a$("log-access").textContent.slice(-70));
const licDocGuard = await gfetch(BASE + "/files/license-doc", { method: "GET" });
ok("۲) سند مجوز بدون ورود باز نمی‌شود", licDocGuard.status === 403, `(${licDocGuard.status})`);

await aclick("runDiagnose");
await awaitFor(() => /گزارش ساخته شد/.test(a$("log-access").textContent), 120000);
ok("۲) گزارش عیب‌یابی ساخته شد", /diagnostic-report/.test(a$("log-access").textContent),
   a$("log-access").textContent.slice(-70));

const noTokenFile = await gfetch(BASE + "/files/usage", { method: "GET" });
ok("۲) پروندهٔ گواهی بدون ورود باز نمی‌شود", noTokenFile.status === 403, `(${noTokenFile.status})`);

await aclick("loadUsage");
await awaitFor(() => /مجموع کارهای موفق/.test(a$("usage-box").textContent), 20000);
ok("۳) دفتر استفاده در پنل خوانده شد", /مجموع کارهای موفق/.test(a$("usage-box").textContent),
   a$("usage-box").textContent.slice(0, 60));
a$("usage-client").value = "نمونهٔ نمایشی";
await aclick("buildUsageStatement");
await awaitFor(() => /گواهی ساخته شد/.test(a$("usage-box").textContent), 20000);
ok("۳) گواهی استفاده ساخته شد", /usage-statement\.html/.test(a$("usage-box").textContent));
ok("۳) زنجیرهٔ دفتر در گواهی گزارش شد", /زنجیره: سالم/.test(a$("usage-box").textContent),
   a$("usage-box").textContent.slice(-60));
ok("۳) کارت‌های شمارش ساخته شد", a$("usage-kpis").querySelectorAll("div").length >= 3);

await aclick("logout");
await awaitFor(() => a$("admin-area").classList.contains("hidden"), 10000);
ok("خروج از پنل کار کرد", a$("admin-area").classList.contains("hidden"));

/* ------------------------------------------- ۱۵. دروازهٔ ورود (مدیر و کارفرما) */
console.log("۱۵. دروازهٔ ورود");
const gateApi = async (path, opts = {}) => {
  const r = await gfetch(BASE + path, opts);
  return { status: r.status, body: await r.json().catch(() => ({})) };
};
const gst = await gateApi("/api/gate/status");
ok("وضعیت دروازه از خود برنامه خوانده می‌شود",
   gst.status === 200 && typeof gst.body.enabled === "boolean", `(${gst.status})`);
ok("نوار بالای صفحه می‌گوید چه کسی وارد شده",
   /دروازه/.test($("whoami").textContent) && /مدیر|مهمان|خاموش/.test($("whoami").textContent),
   $("whoami").textContent.slice(0, 70));

if (gateOn) {
  ok("ورود با رمز غلط رد می‌شود",
     (await fetch(BASE + "/api/login", { method: "POST",
       headers: { "Content-Type": "application/json" },
       body: JSON.stringify({ id: GATE_ADMIN_ID, pass: "غلط‌۱۲۳۴" }) })).status === 401);
  const noCookie = await fetch(BASE + "/files/offer");
  ok("بدون ورود، خروجی‌ها باز نمی‌شوند", noCookie.status === 401, `(${noCookie.status})`);
  const bogus = await fetch(BASE + "/api/signals", { method: "POST",
    headers: { "Content-Type": "application/json", Cookie: "station_gate=deadbeefdeadbeef" }, body: "{}" });
  ok("کوکی جعلی هم قبول نمی‌شود", [401, 302].includes(bogus.status), `(${bogus.status})`);
  ok("مدیر کارت کارفرما و کلید خاموشی را می‌بیند",
     $("gate-card").style.display !== "none"
     && /مهمان/.test($("gate-state").textContent)
     && /نشست‌های باز/.test($("gate-state").textContent),
     $("gate-state").textContent.slice(0, 70));
  const dry = await gateApi("/api/shutdown", { method: "POST",
    body: JSON.stringify({ dry: true }) });
  ok("کلید خاموشی برای مدیر کار می‌کند (بررسی خشک، بی‌خاموشی)",
     dry.body.would_stop === true && /خاموش نشد/.test(String(dry.body.note || "")),
     String(dry.body.note || "").slice(0, 44));
  if (GUEST_ID && GUEST_PASS) {
    const gl = await fetch(BASE + "/api/login", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: GUEST_ID, pass: GUEST_PASS }) });
    ok("ورود کارفرما با حساب مهمان انجام می‌شود", gl.status === 200, `(${gl.status})`);
    const rawCookie = (setCookies(gl)[0] || "").split(";")[0];
    ok("کوکی کارفرما با کوکی مدیر یکی نیست",
       /^station_gate=/.test(rawCookie)
       && !jar.getCookieStringSync(BASE).includes(rawCookie.split("=")[1]),
       rawCookie.slice(0, 22));
    /* عمداً fetch ساده (نه gfetch): کوکی کارفرما باید دست‌نخورده برود، نه کوکی مدیر */
    const gGet = (path, o = {}) => fetch(BASE + path,
      { ...o, redirect: "manual", headers: { ...(o.headers || {}), Cookie: rawCookie } });
    ok("کارفرما برنامه را کامل می‌بیند", (await gGet("/")).status === 200);
    ok("کارفرما خروجی‌ها را می‌بیند", (await gGet("/files/offer")).status === 200
       && (await gGet("/files/review-meeting")).status === 200);
    const adminPage = await gGet("/admin");
    ok("پنل مدیریت برای کارفرما بسته است", adminPage.status === 403, `(${adminPage.status})`);
    ok("کارفرما نمی‌تواند مجوز صادر کند",
       (await gGet("/api/license", { method: "POST",
         body: JSON.stringify({ action: "status" }) })).status === 403);
    ok("کارفرما نمی‌تواند رمزها را عوض کند",
       (await gGet("/api/gate/update", { method: "POST",
         body: JSON.stringify({ action: "set-admin", id: "x", pass: "yyyyyyyy" }) })).status === 403);
    ok("کارفرما نمی‌تواند دسترسی مهمان را قطع کند",
       (await gGet("/api/gate/update", { method: "POST",
         body: JSON.stringify({ action: "guest-off" }) })).status === 403);
    ok("کارفرما نمی‌تواند برنامه را خاموش کند",
       (await gGet("/api/shutdown", { method: "POST",
         body: JSON.stringify({ confirm: true }) })).status === 403);
    ok("برنامه بعد از تلاش خاموشی کارفرما هنوز زنده است",
       (await gGet("/api/gate/status")).status === 200);
  } else {
    skip("بررسی‌های حساب کارفرما", "STATION_GUEST_ID/PASS داده نشد");
  }
  /* خود-ترمیمی: اگر آزمون (بر خلاف انتظار) چیزی را عوض کرده باشد، همین‌جا برگردانده می‌شود */
  const healA = await gateApi("/api/gate/update", { method: "POST",
    body: JSON.stringify({ action: "set-admin", id: GATE_ADMIN_ID, pass: GATE_ADMIN_PASS }) });
  ok("رمز مدیر بعد از آزمون همان رمز شناخته‌شده است", healA.status === 200, `(${healA.status})`);
  if (GUEST_ID && GUEST_PASS) {
    const healG = await gateApi("/api/gate/update", { method: "POST",
      body: JSON.stringify({ action: "set-guest", id: GUEST_ID, pass: GUEST_PASS }) });
    const healOn = await gateApi("/api/gate/update", { method: "POST",
      body: JSON.stringify({ action: "guest-on" }) });
    ok("دسترسی کارفرما بعد از آزمون روشن و سالم است",
       healG.status === 200 && healOn.status === 200, `(${healG.status}/${healOn.status})`);
  }
} else {
  skip("بررسی‌های دروازه", "دروازه خاموش است");
}

console.log(`\nنتیجه: ${pass} موفق · ${fail} ناموفق`);
process.exit(fail ? 1 : 0);
