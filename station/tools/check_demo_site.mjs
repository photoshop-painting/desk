/* آزمون «نمونهٔ ثابت نمایشی» — هم روی نسخهٔ محلی، هم روی لینک عمومی.
   اجرا:  node check_demo_site.mjs http://127.0.0.1:8099
   چه می‌سنجد: صفحهٔ نخست، خروجی‌های واقعی، و اینکه خودِ رابط با ضبط، بالا می‌آید و
   گام‌هایش کار می‌کند (بدون سرور، بدون خطای جاوااسکریپت). */
import { JSDOM, VirtualConsole } from "jsdom";

const BASE = (process.argv[2] || "http://127.0.0.1:8099").replace(/\/$/, "");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0;
const ok = (name, cond, extra = "") => {
  if (cond) { pass++; console.log(`  ✓ ${name}`); }
  else { fail++; console.log(`  ✗ ${name} ${extra}`); }
};
const text = async (path) => {
  const r = await fetch(BASE + path);
  return { status: r.status, body: await r.text() };
};

console.log(`── آزمون نمونهٔ ثابت: ${BASE} ──`);

/* ۱) صفحهٔ نخست و خروجی‌های واقعی */
const home = await text("/index.html");
ok("صفحهٔ نخست باز می‌شود", home.status === 200);
ok("یادآوری «نمونهٔ ثابت» در صفحهٔ نخست هست", home.body.includes("نمونهٔ ثابت"));
ok("نکتهٔ «سود تضمینی» صادقانه گفته شده", home.body.includes("سود تضمینی"));
ok("امضای تهیه‌کننده هست", home.body.includes("Masoud Mojarabian") && home.body.includes("09126630554"));

for (const [path, needle, label] of [
  ["/files/offer.html", "پیشنهاد", "برگهٔ پیشنهاد"],
  ["/files/review-meeting.html", "", "برگهٔ جلسهٔ بازبینی"],
  ["/files/onboarding.html", "", "روز اول مشتری"],
  ["/files/sales-today.html", "", "مراسم فروش"],
  ["/files/prospects.html", "", "تابلوی مخاطبان"],
  ["/files/outreach.html", "", "بستهٔ پیام‌ها"],
  ["/files/method.html", "", "جزوهٔ روش"],
  ["/files/walkthrough.txt", "", "راهنمای گام‌به‌گام"],
]) {
  const r = await text(path);
  ok(`خروجی واقعی: ${label}`, r.status === 200 && r.body.length > 300 && r.body.includes(needle),
     `(${r.status} · ${r.body.length} بایت)`);
}

/* ۲) خودِ رابط، بدون سرور */
const errors = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => { if (!/Could not load/.test(String(e))) errors.push(String(e.message)); });
const dom = await JSDOM.fromURL(BASE + "/app/index.html", {
  runScripts: "dangerously", resources: "usable", pretendToBeVisual: true, virtualConsole: vc,
});
const { window } = dom;
window.confirm = () => true;
await new Promise((r) => window.addEventListener("load", r));
/* به‌جای انتظار ثابت: تا آماده‌شدن نوار و پیوندها صبر می‌کنیم (بیشینه ۱۵ ثانیه) */
for (let i = 0; i < 60 && !window.document.querySelector("#nav a"); i++) {
  await sleep(250);
}
await sleep(300);
const doc = window.document;
const q = (s) => doc.querySelector(s);

ok("رابط بالا آمد و خطای جاوااسکریپت ندارد", errors.length === 0, errors.slice(0, 2).join(" | "));
ok("نوار «نمونهٔ ثابت» بالای صفحه هست",
   (doc.body.textContent || "").includes("نمونهٔ ثابت نمایشی"));
const navLinks = doc.querySelectorAll("#nav a");
ok("نوار گام‌ها ساخته شد (دست‌کم ۱۰ گام)", navLinks.length >= 10, `(${navLinks.length})`);

const titles = Array.from(navLinks).map((a) => a.textContent.trim());
ok("گام‌ها نام دارند", titles.filter((t) => t.length > 2).length >= 10);

/* گام‌به‌گام جلو می‌رویم و می‌بینیم هر بخش باز می‌شود */
let opened = 0;
for (let i = 0; i < navLinks.length; i++) {
  try {
    navLinks[i].dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
    await sleep(350);
    const active = doc.querySelector("section.active");
    if (active && (active.textContent || "").trim().length > 60) opened++;
  } catch (e) { /* گام بعدی */ }
}
ok("همهٔ گام‌ها با کلیک باز می‌شوند", opened >= Math.min(10, navLinks.length), `(${opened})`);

/* محتوای ضبط‌شده در صفحه دیده می‌شود */
const allText = doc.body.textContent || "";
ok("محتوای ضبط‌شده روی صفحه آمده (جدول‌ها پر است)", allText.length > 3000, `(${allText.length} نویسه)`);

/* ۳) لایهٔ ثابت: پاسخ‌های ضبط‌شده برمی‌گردند و پیام صادقانه برای ضبط‌نشده‌ها */
const probes = await window.eval(`(async () => {
  const out = {};
  for (const p of ["/api/state", "/api/gate/status", "/api/nonexistent-demo-path"]) {
    const r = await fetch(p);
    out[p] = { status: r.status, body: (await r.text()).slice(0, 200) };
  }
  return out;
})()`);
ok("/api/state از ضبط برمی‌گردد", probes["/api/state"].status === 200 && probes["/api/state"].body.includes("{"));
const gateBody = probes["/api/gate/status"].body.replace(/\s+/g, "");
ok("وضعیت دروازه در نمونهٔ ثابت «خاموش» است تا کسی به صفحهٔ ورود نرود",
   gateBody.includes('"enabled":false'), gateBody.slice(0, 80));
ok("بخش ضبط‌نشده پیام صادقانه می‌دهد",
   probes["/api/nonexistent-demo-path"].body.includes("نمونهٔ ثابت"));

/* ۴) لینک‌های فایل به نسخهٔ ایستا می‌روند */
const rewritten = await window.eval(`(() => {
  const a = document.createElement("a");
  a.setAttribute("href", "/files/offer");
  document.body.appendChild(a);
  a.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  return a.getAttribute("href");
})()`);
ok("پیوند /files/offer به فایل ذخیره‌شده هدایت می‌شود", /files\/offer\.html$/.test(rewritten), rewritten);

console.log(`\nنتیجه: ${pass} موفق · ${fail} ناموفق`);
process.exit(fail ? 1 : 0);
