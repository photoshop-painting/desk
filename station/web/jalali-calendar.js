/* jalali-calendar.js — تقویمِ شمسیِ ایستگاه (خودکفا و آفلاین)
 *
 * کامپوننتِ «تقویم شمسی / انتخاب تاریخ» بر اساسِ مهارتِ jalali-calendar از وایب‌فارسی
 * (vibefarsi.ir/skills/jalali-calendar):
 *   - هفته از **شنبه** شروع می‌شود؛ جمعه تعطیله و خاکستری.
 *   - در RTL جهتِ فلش‌ها برعکس است: ماهِ قبل → فلش به راست، ماهِ بعد → فلش به چپ.
 *   - حالت‌ها فقط با رنگ مشخص نمی‌شوند: «امروز» حلقه دارد، «انتخاب‌شده» تیک ✓ می‌گیرد.
 *   - نمایش همیشه وقتِ تهران (UTC+3:30، بدون وقت تابستانی) و ارقامِ فارسی است.
 *   - تبدیلِ تاریخ با همان jalali.jsِ اعتبارسنجی‌شدهٔ ایستگاه (الگوریتم Borkowski).
 *
 * API:
 *   JalaliCal.today()                 -> [jy, jm, jd] (تقویمِ تهرانِ همین‌لحظه)
 *   JalaliCal.monthLength(jy, jm)     -> ۳۱/۳۰/۲۹
 *   JalaliCal.firstWeekday(jy, jm)    -> ۰=شنبه … ۶=جمعه
 *   JalaliCal.addDays([jy,jm,jd], n)  -> [jy, jm, jd]
 *   JalaliCal.diffDays(a, b)          -> b - a (روز)
 *   JalaliCal.fmt([jy,jm,jd])         -> «۱۴۰۵/۰۷/۰۱»
 *   JalaliCal.fmtLong([jy,jm,jd])     -> «۱ مهر ۱۴۰۵»
 *   JalaliCal.presets()               -> {week, month, lastMonth} به‌صورت {from, to}
 *   JalaliCal.tehranDayUtc(jy,jm,jd)  -> {fromIso, toIso}  (روزِ تهران به‌عنوان بازهٔ UTC)
 *   JalaliCal.open(anchor, opts)      -> popover؛ opts: {initial, onPick, onClose}
 *   JalaliCal.close()
 */
"use strict";
(function (root) {
  var J = root.Jalali;
  if (!J) throw new Error("jalali-calendar.js بدونِ jalali.js کار نمی‌کند");

  var MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];
  var WEEK = ["ش", "ی", "د", "س", "چ", "پ", "ج"];
  var WEEK_FULL = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];
  var TEH_MS = 3.5 * 3600 * 1000;          // UTC+3:30، بدون وقت تابستانی
  var DAY = 86400000;

  function fa(x) { return J.faNum(x); }
  function pad2(x) { return (x < 10 ? "0" : "") + x; }

  function tehranNowMs() { return Date.now() + TEH_MS; }

  function today() {
    var d = new Date(tehranNowMs());
    return J.g2j(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
  }

  function monthLength(jy, jm) { return J.monthLength(jy, jm); }

  /* روزِ هفتهٔ اولِ ماه (۰=شنبه). روزِ JS: ۰=یکشنبه … ۶=شنبه ⇒ (js+1)٪۷ */
  function firstWeekday(jy, jm) {
    var g = J.j2g(jy, jm, 1);
    var js = new Date(Date.UTC(g[0], g[1] - 1, g[2])).getUTCDay();
    return (js + 1) % 7;
  }

  function addDays(dj, n) {
    var g = J.j2g(dj[0], dj[1], dj[2]);
    var t = new Date(Date.UTC(g[0], g[1] - 1, g[2]) + n * DAY);
    return J.g2j(t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate());
  }

  function diffDays(a, b) {
    var ga = J.j2g(a[0], a[1], a[2]);
    var gb = J.j2g(b[0], b[1], b[2]);
    return Math.round((Date.UTC(gb[0], gb[1] - 1, gb[2]) - Date.UTC(ga[0], ga[1] - 1, ga[2])) / DAY);
  }

  function sameDay(a, b) { return a[0] === b[0] && a[1] === b[1] && a[2] === b[2]; }

  /* «1405/7/1» یا «۱۴۰۵/۰۷/۰۱» (با «/» یا «-») ← [1405, 7, 1]؛ در صورتِ نامعتبری null. */
  function parse(s) {
    if (Array.isArray(s)) return s;
    var m = /^([۰-۹0-9]{3,4})[\/\-]([۰-۹0-9]{1,2})[\/\-]([۰-۹0-9]{1,2})$/.exec(String(s || "").trim());
    if (!m) return null;
    function toLat(x) { return parseInt(x.replace(/[۰-۹]/g, function (c) { return String(c.charCodeAt(0) - 0x06F0); }), 10); }
    var y = toLat(m[1]), mo = toLat(m[2]), da = toLat(m[3]);
    if (!y || mo < 1 || mo > 12 || da < 1 || y < J.MIN_YEAR || y > J.MAX_YEAR ||
        da > monthLength(y, mo)) return null;
    return [y, mo, da];
  }

  function fmt(dj) { return fa(dj[0]) + "/" + fa(pad2(dj[1])) + "/" + fa(pad2(dj[2])); }

  function fmtLong(dj) {
    var wd = WEEK_FULL[(firstWeekday(dj[0], dj[1]) + dj[2] - 1) % 7];
    return fa(dj[2]) + " " + MONTHS[dj[1] - 1] + " " + fa(dj[0]) + " (" + wd + ")";
  }

  /* بازه‌های آماده — «۷ روز گذشته»، «این ماه»، «ماه گذشته» — همه در تقویمِ شمسی محاسبه می‌شوند. */
  function presets() {
    var t = today();
    var ly, lm;
    if (t[1] === 1) { ly = t[0] - 1; lm = 12; } else { ly = t[0]; lm = t[1] - 1; }
    return {
      week:      { from: addDays(t, -6), to: t },
      month:     { from: [t[0], t[1], 1], to: [t[0], t[1], monthLength(t[0], t[1])] },
      lastMonth: { from: [ly, lm, 1], to: [ly, lm, monthLength(ly, lm)] }
    };
  }

  /* یک روزِ تقویمیِ تهران به‌عنوان بازهٔ UTC: [از نیمه‌شب، تا نیمه‌شبِ بعد).
   * ۰۰:۰۰ تهران = ۲۰:۳۰ UTCِ روزِ قبل — پس از تاریخِ میلادیِ آن روز ۳:۳۰ ساعت کم می‌شود. */
  function tehranDayUtc(jy, jm, jd) {
    var g = J.j2g(jy, jm, jd);
    var start = Date.UTC(g[0], g[1] - 1, g[2]) - TEH_MS;
    function iso(ms) { return new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z"); }
    return { fromIso: iso(start), toIso: iso(start + DAY) };
  }

  /* ---------------- popover ---------------- */
  var node = null, closeBtn = null;

  function injectStyle() {
    if (document.getElementById("jlcal-style")) return;
    var st = document.createElement("style");
    st.id = "jlcal-style";
    st.textContent = [
      ".jlcal{position:fixed;z-index:999;direction:rtl;background:#fff;border:1px solid #e3e6ea;",
      "border-radius:12px;box-shadow:0 10px 30px rgba(16,24,40,.14);padding:10px;width:296px;",
      "font-family:inherit;font-size:13px;color:#1d1d1f;text-align:right}",
      ".jlcal-h{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}",
      ".jlcal-t{font-size:14px;font-weight:700}",
      ".jlcal-b{border:1px solid #e3e6ea;background:#fff;border-radius:7px;width:30px;height:30px;",
      "cursor:pointer;font-size:14px;line-height:1;padding:0}",
      ".jlcal-b:hover{background:#f0f4f3}",
      ".jlcal-w,.jlcal-g{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}",
      ".jlcal-w span{text-align:center;font-size:11.5px;color:#6b7280;padding:3px 0}",
      ".jlcal-w span.fr{color:#9aa3ad;font-weight:700}",
      ".jlcal-d{border:0;background:transparent;border-radius:8px;min-height:34px;cursor:pointer;",
      "font:inherit;font-size:13px;padding:4px 0}",
      ".jlcal-d:hover{background:#eef4f1}",
      ".jlcal-d.fr{color:#9aa3ad}",
      ".jlcal-d.today{box-shadow:inset 0 0 0 1.5px #0b3d2e;font-weight:700}",
      ".jlcal-d.sel{background:#0b3d2e;color:#fff;font-weight:700}",
      ".jlcal-d.sel::before{content:'✓ '}",
      ".jlcal-d:focus-visible{outline:2px solid #2b5fb0;outline-offset:1px}"
    ].join("");
    document.head.appendChild(st);
  }

  function close() {
    if (!node) return;
    node.remove();
    node = null;
    document.removeEventListener("mousedown", onDown, true);
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("scroll", close, true);
    var cb = closeBtn; closeBtn = null;
    if (cb) cb.focus();
  }

  function onDown(ev) {
    if (node && !node.contains(ev.target) && ev.target !== closeBtn) close();
  }
  function onKey(ev) {
    if (!node) return;
    if (ev.key === "Escape") { ev.preventDefault(); close(); }
  }

  function open(anchor, opts) {
    opts = opts || {};
    close();
    injectStyle();
    var d = document;
    var sel = (opts.initial && opts.initial.length === 3) ? opts.initial.slice() : null;
    var t = today();
    var view = sel ? [sel[0], sel[1]] : [t[0], t[1]];

    node = d.createElement("div");
    node.className = "jlcal";
    node.setAttribute("role", "dialog");
    node.setAttribute("aria-label", "تقویم شمسی — انتخاب تاریخ");

    function render() {
      node.innerHTML = "";
      var h = d.createElement("div"); h.className = "jlcal-h";
      /* RTL: ماهِ قبل سمتِ راست (فلش به راست)، ماهِ بعد سمتِ چپ (فلش به چپ) */
      var bPrev = d.createElement("button");
      bPrev.type = "button"; bPrev.className = "jlcal-b";
      bPrev.setAttribute("aria-label", "ماه قبل"); bPrev.textContent = "→";
      var title = d.createElement("div"); title.className = "jlcal-t";
      title.textContent = MONTHS[view[1] - 1] + " " + fa(view[0]);
      var bNext = d.createElement("button");
      bNext.type = "button"; bNext.className = "jlcal-b";
      bNext.setAttribute("aria-label", "ماه بعد"); bNext.textContent = "←";
      h.appendChild(bPrev); h.appendChild(title); h.appendChild(bNext);
      node.appendChild(h);

      var w = d.createElement("div"); w.className = "jlcal-w";
      for (var i = 0; i < 7; i++) {
        var s = d.createElement("span");
        s.textContent = WEEK[i];
        if (i === 6) s.className = "fr";           // جمعه
        w.appendChild(s);
      }
      node.appendChild(w);

      var g = d.createElement("div"); g.className = "jlcal-g";
      var lead = firstWeekday(view[0], view[1]);
      var n = monthLength(view[0], view[1]);
      for (var b = 0; b < lead; b++) {
        var bl = d.createElement("span"); bl.className = "jlcal-d"; bl.style.visibility = "hidden";
        g.appendChild(bl);
      }
      for (var day = 1; day <= n; day++) {
        (function (day) {
          var dj = [view[0], view[1], day];
          var c = d.createElement("button");
          c.type = "button"; c.className = "jlcal-d";
          if ((firstWeekday(view[0], view[1]) + day - 1) % 7 === 6) c.className += " fr";
          if (sameDay(dj, t)) c.className += " today";
          if (sel && sameDay(dj, sel)) c.className += " sel";
          c.textContent = fa(day);
          c.setAttribute("aria-label", fmtLong(dj));
          if (sameDay(dj, t)) c.setAttribute("aria-current", "date");
          if (sel && sameDay(dj, sel)) c.setAttribute("aria-pressed", "true");
          c.addEventListener("click", function () {
            sel = dj;
            if (opts.onPick) opts.onPick(dj[0], dj[1], dj[2]);
            close();
            if (anchor && anchor.focus) anchor.focus();
          });
          g.appendChild(c);
        })(day);
      }
      node.appendChild(g);

      bPrev.addEventListener("click", function () {
        if (view[1] === 1) { view[0] -= 1; view[1] = 12; } else { view[1] -= 1; }
        render();
      });
      bNext.addEventListener("click", function () {
        if (view[1] === 12) { view[0] += 1; view[1] = 1; } else { view[1] += 1; }
        render();
      });
      var focusTarget = node.querySelector(".jlcal-d.sel") || node.querySelector(".jlcal-d.today") ||
                        node.querySelectorAll(".jlcal-d")[lead];
      if (focusTarget) focusTarget.focus();
    }

    render();
    closeBtn = anchor;

    /* موقعیت: زیرِ ورودی، چسبیده به لبهٔ صفحه */
    d.body.appendChild(node);
    var r = anchor ? anchor.getBoundingClientRect() : { left: 40, bottom: 80 };
    var vw = window.innerWidth || 1000, vh = window.innerHeight || 700;
    var left = Math.min(Math.max(8, r.left), vw - node.offsetWidth - 8);
    var top = r.bottom + 6;
    if (top + node.offsetHeight > vh - 8) top = Math.max(8, r.top - node.offsetHeight - 6);
    node.style.left = left + "px";
    node.style.top = top + "px";

    document.addEventListener("mousedown", onDown, true);
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("scroll", close, true);
    return close;
  }

  /* ---------------- بازهٔ تاریخ (دو ماهِ کنارِ هم) ----------------
   * مطابقِ specِ date-range-picker از وایب‌فارسی: دو ماه کنار هم (قدیمی‌تر
   * سمتِ چپ، تازه‌تر سمتِ راست)، پیش‌نمایشِ بازه با هاور، بازه‌های آماده
   * و شمارشِ روزها. کلیکِ اول = «از»، کلیکِ دوم = «تا» (اگر برعکس شد،
   * خودش جابه‌جا می‌شود) و بازه تمام می‌شود. حالت‌ها فقط با رنگ مشخص
   * نمی‌شوند: دو سرِ بازه تیک ✓ دارند، میانهٔ بازه سایه‌روشنِ جدا
   * می‌گیرد و شمارشِ روز هم نوشته می‌شود. */
  var rnode = null, rcloseBtn = null;

  function rangeInjectStyle() {
    if (document.getElementById("jlcal-rstyle")) return;
    var st = document.createElement("style");
    st.id = "jlcal-rstyle";
    st.textContent = [
      ".jlcal-range{position:fixed;z-index:999;direction:rtl;background:#fff;border:1px solid #e3e6ea;",
      "border-radius:12px;box-shadow:0 10px 30px rgba(16,24,40,.14);padding:10px 12px;width:592px;",
      "font-family:inherit;font-size:13px;color:#1d1d1f;text-align:right}",
      ".jlcal-rr{display:grid;grid-template-columns:1fr 1fr;gap:14px}",
      ".jlcal-rm{border:0;border-radius:8px}",
      ".jlcal-rf{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px;padding-top:8px;",
      "border-top:1px solid #eef1f4}",
      ".jlcal-rf .count{font-size:13px;font-weight:700;margin-inline-start:auto}",
      ".jlcal-rf .pv-count{color:#0b3d2e}",
      ".jlcal-d.pv{background:#eef4f1}",
      ".jlcal-d.pv::before{content:''}",
      ".jlcal-d.sel::before{content:'✓ '}"
    ].join("");
    document.head.appendChild(st);
  }

  function rClose() {
    if (!rnode) return;
    rnode.remove();
    rnode = null;
    document.removeEventListener("mousedown", rOnDown, true);
    document.removeEventListener("keydown", rOnKey, true);
    document.removeEventListener("scroll", rClose, true);
    var b = rcloseBtn; rcloseBtn = null;
    if (b && b.focus) b.focus();
  }
  function rOnDown(ev) {
    if (rnode && !rnode.contains(ev.target) && ev.target !== rcloseBtn) rClose();
  }
  function rOnKey(ev) {
    if (!rnode) return;
    if (ev.key === "Escape") { ev.preventDefault(); rClose(); }
  }

  function openRange(anchor, opts) {
    opts = opts || {};
    rClose();
    injectStyle();
    rangeInjectStyle();
    var d = document;
    var t = today();
    var view = (opts.to) ? [opts.to[0], opts.to[1]] : (opts.from ? [opts.from[0], opts.from[1]] : [t[0], t[1]]);
    var sel = { a: opts.from ? opts.from.slice() : null, b: opts.to ? opts.to.slice() : null, hover: null };

    rnode = d.createElement("div");
    rnode.className = "jlcal-range";
    rnode.setAttribute("role", "dialog");
    rnode.setAttribute("aria-label", "تقویم شمسی — انتخاب بازهٔ تاریخ");

    function prevMonthOf(m) {
      return m[1] === 1 ? [m[0] - 1, 12] : [m[0], m[1] - 1];
    }
    function monthLabel(m) { return MONTHS[m[1] - 1] + " " + fa(m[0]); }
    function inRange(x) {
      if (!sel.a || !sel.hover) return false;
      var lo = sel.a, hi = sel.hover;
      if (diffDays(lo, hi) < 0) { var s = lo; lo = hi; hi = s; }
      return diffDays(lo, x) >= 0 && diffDays(x, hi) <= 0;
    }
    function countText() {
      var a = sel.a, b = sel.b || sel.hover;
      if (!a || !b) return "برای انتخاب: یکی روی «از»، یکی روی «تا»";
      var n = Math.abs(diffDays(a, b)) + 1;
      return fa(n) + " روز";
    }

    function renderGrid(m) {
      var box = d.createElement("div");
      box.className = "jlcal-rm";
      var head = d.createElement("div");
      head.className = "jlcal-t";
      head.style.textAlign = "center";
      head.textContent = monthLabel(m);
      box.appendChild(head);
      var w = d.createElement("div");
      w.className = "jlcal-w";
      for (var i = 0; i < 7; i++) {
        var s = d.createElement("span");
        s.textContent = WEEK[i];
        if (i === 6) s.className = "fr";
        w.appendChild(s);
      }
      box.appendChild(w);
      var g = d.createElement("div");
      g.className = "jlcal-g";
      var lead = firstWeekday(m[0], m[1]);
      var n = monthLength(m[0], m[1]);
      for (var b = 0; b < lead; b++) {
        var bl = d.createElement("span");
        bl.className = "jlcal-d";
        bl.style.visibility = "hidden";
        g.appendChild(bl);
      }
      for (var day = 1; day <= n; day++) {
        (function (day) {
          var dj = [m[0], m[1], day];
          var c = d.createElement("button");
          c.type = "button";
          c.className = "jlcal-d";
          if ((lead + day - 1) % 7 === 6) c.className += " fr";
          if (sameDay(dj, t)) c.className += " today";
          c.setAttribute("aria-label", fmtLong(dj));
          c.setAttribute("data-day", dj.join("/"));
          g.appendChild(c);
          c.addEventListener("click", function () { onPickDay(dj); });
          c.addEventListener("mouseover", function () {
            sel.hover = dj;
            paint();
          });
        })(day);
      }
      box.appendChild(g);
      return box;
    }

    function paint() {
      var cells = rnode.querySelectorAll(".jlcal-g button.jlcal-d");
      for (var i = 0; i < cells.length; i++) {
        var dj = cells[i].getAttribute("data-day").split("/").map(Number);
        var cls = "jlcal-d" +
          (((firstWeekday(dj[0], dj[1]) + dj[2] - 1) % 7) === 6 ? " fr" : "") +
          (sameDay(dj, t) ? " today" : "");
        if (sel.a && sameDay(dj, sel.a)) cls += " sel";
        else if (sel.b && sameDay(dj, sel.b)) cls += " sel";
        else if (inRange(dj)) cls += " pv";
        cells[i].className = cls;
        cells[i].setAttribute("aria-pressed", cls.indexOf(" sel") >= 0 ? "true" : "false");
      }
      var cnt = rnode.querySelector(".jlcal-rf .count");
      if (cnt) {
        cnt.textContent = countText();
        cnt.className = "jlcal-rf count" + (sel.b ? " pv-count" : "");
      }
    }

    function onPickDay(dj) {
      if (!sel.a) {
        sel.a = dj; sel.b = null; sel.hover = dj;
        paint();
        return;
      }
      var b = dj;
      if (diffDays(sel.a, b) < 0) { var s = sel.a; sel.a = b; b = s; }
      sel.b = b; sel.hover = b;
      paint();
      if (opts.onDone) opts.onDone(sel.a.slice(), sel.b.slice());
      rClose();
      if (anchor && anchor.focus) anchor.focus();
    }

    function render() {
      rnode.innerHTML = "";
      var nav = d.createElement("div");
      nav.className = "jlcal-h";
      var bPrev = d.createElement("button");
      bPrev.type = "button";
      bPrev.className = "jlcal-b";
      bPrev.setAttribute("aria-label", "ماه‌های قبل");
      bPrev.textContent = "→";
      var title = d.createElement("div");
      title.className = "jlcal-t";
      title.textContent = "انتخاب بازهٔ تاریخ";
      var bNext = d.createElement("button");
      bNext.type = "button";
      bNext.className = "jlcal-b";
      bNext.setAttribute("aria-label", "ماه‌های بعد");
      bNext.textContent = "←";
      nav.appendChild(bPrev);
      nav.appendChild(title);
      nav.appendChild(bNext);
      rnode.appendChild(nav);

      var rr = d.createElement("div");
      rr.className = "jlcal-rr";
      rr.appendChild(renderGrid(view));            // راست: ماهِ تازه‌تر
      rr.appendChild(renderGrid(prevMonthOf(view))); // چپ: ماهِ قبل
      rnode.appendChild(rr);

      var rf = d.createElement("div");
      rf.className = "jlcal-rf";
      var mkPreset = function (kind, label) {
        var p = d.createElement("button");
        p.type = "button";
        p.className = "jlcal-rp";
        p.textContent = label;
        p.setAttribute("aria-label", label);
        p.addEventListener("click", function () {
          var pr = presets()[kind];
          sel.a = pr.from.slice();
          sel.b = pr.to.slice();
          sel.hover = null;
          view = [pr.to[0], pr.to[1]];
          render();
        });
        return p;
      };
      rf.appendChild(mkPreset("week", "۷ روز گذشته"));
      rf.appendChild(mkPreset("month", "این ماه"));
      rf.appendChild(mkPreset("lastMonth", "ماه گذشته"));
      var bClear = d.createElement("button");
      bClear.type = "button";
      bClear.textContent = "پاک کردن بازه";
      bClear.addEventListener("click", function () {
        sel.a = null; sel.b = null; sel.hover = null;
        paint();
      });
      var bCancel = d.createElement("button");
      bCancel.type = "button";
      bCancel.textContent = "انصراف";
      bCancel.addEventListener("click", rClose);
      var bOk = d.createElement("button");
      bOk.type = "button";
      bOk.className = "primary";
      bOk.textContent = "تأیید";
      bOk.addEventListener("click", function () {
        if (sel.a && sel.b) {
          if (opts.onDone) opts.onDone(sel.a.slice(), sel.b.slice());
        } else if (opts.onClear) {
          opts.onClear();
        }
        rClose();
        if (anchor && anchor.focus) anchor.focus();
      });
      var cnt = d.createElement("span");
      cnt.className = "jlcal-rf count";
      cnt.setAttribute("aria-live", "polite");
      cnt.textContent = countText();
      rf.appendChild(bClear);
      rf.appendChild(bCancel);
      rf.appendChild(bOk);
      rf.appendChild(cnt);
      rnode.appendChild(rf);

      bPrev.addEventListener("click", function () {
        if (view[1] === 1) { view[0] -= 1; view[1] = 12; } else { view[1] -= 1; }
        render();
      });
      bNext.addEventListener("click", function () {
        if (view[1] === 12) { view[0] += 1; view[1] = 1; } else { view[1] += 1; }
        render();
      });
      paint();
      var first = rnode.querySelector(".jlcal-d.today") || rnode.querySelector(".jlcal-g button.jlcal-d");
      if (first) first.focus();
    }

    render();
    rcloseBtn = anchor;

    d.body.appendChild(rnode);
    var r = anchor ? anchor.getBoundingClientRect() : { left: 60, bottom: 100 };
    var vw = window.innerWidth || 1000, vh = window.innerHeight || 700;
    var left = Math.min(Math.max(8, r.left - 120), vw - rnode.offsetWidth - 8);
    var top = r.bottom + 6;
    if (top + rnode.offsetHeight > vh - 8) top = Math.max(8, r.top - rnode.offsetHeight - 6);
    rnode.style.left = left + "px";
    rnode.style.top = top + "px";

    document.addEventListener("mousedown", rOnDown, true);
    document.addEventListener("keydown", rOnKey, true);
    document.addEventListener("scroll", rClose, true);
    return rClose;
  }

  root.JalaliCal = {
    MONTHS: MONTHS, WEEK: WEEK, WEEK_FULL: WEEK_FULL,
    today: today, monthLength: monthLength, firstWeekday: firstWeekday,
    addDays: addDays, diffDays: diffDays, sameDay: sameDay, parse: parse,
    fmt: fmt, fmtLong: fmtLong, presets: presets, tehranDayUtc: tehranDayUtc,
    open: open, close: close, openRange: openRange
  };
})(typeof window !== "undefined" ? window : this);
