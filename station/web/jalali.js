/* jalali.js — تقویمِ شمسی برای ایستگاه (خودکفا و آفلاین)
 *
 * الگوریتمِ Kazimierz M. Borkowski («The Persian calendar for 3000 years»،
 * ۱۹۶)، همان الگوریتمِ کتابخانهٔ jalaali-js (مجوز MIT، github.com/jalaali/jalaali-js)
 * که این‌جا بدونِ وابستگی و برای بستهٔ آفلاین بازپیموده شده است.
 *
 * API:
 *   Jalali.g2j(gy, gm, gd)  -> [jy, jm, jd]
 *   Jalali.j2g(jy, jm, jd)  -> [gy, gm, gd]
 *   Jalali.fmt(iso)         -> «۱۴۵/۰۷/۰۲ ۱۸:۲۰» (وقتِ تهران، ارقامِ فارسی)
 * وقتِ نمایش همیشه **تهران** (UTC+3:30) است، نه UTCِ سرور.
 */
"use strict";
(function (root) {
  // div/mod به‌سبکِ کتابخانهٔ اصلی (برشِ سمتِ صفر؛ الگوریتمِ Borkowski با همین‌ها دقیق است)
  function div(a, b) { return ~~(a / b); }
  function mod(a, b) { return a - ~~(a / b) * b; }

  var BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181,
                1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];
  var MIN_JY = BREAKS[0];
  var MAX_JY = BREAKS[BREAKS.length - 1] - 1;

  function jalCalCore(jy) {
    if (!isFinite(jy) || jy < MIN_JY || jy > MAX_JY) return null;
    var gy = jy + 621;
    var leapJ = -14;
    var jp = BREAKS[0];
    var jm = 0, jump = 0;
    for (var i = 1; i < BREAKS.length; i += 1) {
      jm = BREAKS[i];
      jump = jm - jp;
      if (jy < jm) break;
      leapJ = leapJ + div(jump, 33) * 8 + div(mod(jump, 33), 4);
      jp = jm;
    }
    var n = jy - jp;
    leapJ = leapJ + div(n, 33) * 8 + div(mod(n, 33) + 3, 4);
    if (mod(jump, 33) === 4 && jump - n === 4) leapJ += 1;
    var leapG = div(gy, 4) - div((div(gy, 100) + 1) * 3, 4) - 150;
    var march = 20 + leapJ - leapG;
    return { gy: gy, march: march, jump: jump, n: n };
  }

  function g2d(gy, gm, gd) {
    var d = div((gy + div(gm - 8, 6) + 100100) * 1461, 4) +
            div(153 * mod(gm + 9, 12) + 2, 5) + gd - 34840408;
    d = d - div(div(gy + 100100 + div(gm - 8, 6), 100) * 3, 4) + 752;
    return d;
  }

  function d2g(jdn) {
    var j = 4 * jdn + 139361631;
    j = j + div(div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908;
    var i = div(mod(j, 1461), 4) * 5 + 308;
    var gd = div(mod(i, 153), 5) + 1;
    var gm = mod(div(i, 153), 12) + 1;
    var gy = div(j, 1461) - 100100 + div(8 - gm, 6);
    return [gy, gm, gd];
  }

  function j2d(jy, jm, jd) {
    var r = jalCalCore(jy);
    if (!r) throw new RangeError("سالِ شمسی خارج از محدودهٔ " + MIN_JY + " تا " + MAX_JY);
    return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - div(jm, 7) * (jm - 7) + jd - 1;
  }

  function d2j(jdn) {
    var gy = d2g(jdn)[0];
    var jy = Math.min(gy - 621, MAX_JY);
    var r = jalCalCore(jy);
    if (!r) throw new RangeError("جایگاهِ جولیانی خارج از محدوده");
    var leap = 0, adjusted = r.n;
    if (r.jump - r.n < 6) adjusted = r.n - r.jump + div(r.jump + 4, 33) * 33;
    leap = mod(mod(adjusted + 1, 33) - 1, 4);
    if (leap === -1) leap = 4;
    var jdn1f = g2d(r.gy, 3, r.march);
    var k = jdn - jdn1f;
    if (k >= 0) {
      if (k <= 185) return [jy, 1 + div(k, 31), mod(k, 31) + 1];
      k -= 186;
    } else {
      jy -= 1;
      k += 179;
      // سالِ شمسیِ قبلی کبیس بود (r.leap===1 یعنی آخرین سالِ کبیس، سالِ پیش بوده)
      if (leap === 1) k += 1;
    }
    return [jy, 7 + div(k, 30), mod(k, 30) + 1];
  }

  function monthLength(jy, jm) {
    if (jm <= 6) return 31;
    if (jm <= 11) return 30;
    var r = jalCalCore(jy);
    if (!r) return 29;
    var adjusted = r.n;
    if (r.jump - r.n < 6) adjusted = r.n - r.jump + div(r.jump + 4, 33) * 33;
    var leap = mod(mod(adjusted + 1, 33) - 1, 4);
    if (leap === -1) leap = 4;
    return leap === 0 ? 30 : 29;
  }

  var FA_DIGITS = "";
  for (var _i = 0; _i < 10; _i++) FA_DIGITS += String.fromCharCode(0x06F0 + _i); // ۰ تا ۹ (ساختِ برنامه‌ای، بدونِ خطرِ تایپ)
  function faNum(x) {
    return String(x).replace(/[0-9]/g, function (d) { return FA_DIGITS[+d]; });
  }
  function pad2(x) { return (x < 10 ? "0" : "") + x; }

  /** ISO (یا millisecond) ← «۱۴۰/۰۷/۲ ۱۸:۲۰» بر پایهٔ وقتِ تهران (UTC+3:30). */
  function fmt(iso) {
    try {
      var t = (iso instanceof Date) ? iso.getTime()
            : (typeof iso === "number") ? iso
            : Date.parse(String(iso).replace(" ", "T"));
      if (isNaN(t)) return String(iso);
      t += 3.5 * 3600 * 1000;                       // وقتِ تهران
      var d = new Date(t);
      var j = d2j(g2d(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate()));
      return faNum(j[0]) + "/" + faNum(pad2(j[1])) + "/" + faNum(pad2(j[2])) +
             " " + faNum(pad2(d.getUTCHours())) + ":" + faNum(pad2(d.getUTCMinutes()));
    } catch (e) {
      return String(iso);
    }
  }

  var Jalali = {
    g2j: function (gy, gm, gd) { return d2j(g2d(gy, gm, gd)); },
    j2g: function (jy, jm, jd) { return d2g(j2d(jy, jm, jd)); },
    monthLength: monthLength,
    fmt: fmt, faNum: faNum,
    MIN_YEAR: MIN_JY, MAX_YEAR: MAX_JY
  };
  if (typeof module !== "undefined" && module.exports) module.exports = Jalali;
  root.Jalali = Jalali;
})(typeof window !== "undefined" ? window : globalThis);
