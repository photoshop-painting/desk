#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ریاضیِ پول — «با ریاضی می‌شود ثروتمند شد؟» جواب صادقانه، با عدد.

جواب کوتاه: بله، ولی نه با یک معاملهٔ خوش‌شانس. سه چیز لازم است و هر سه ریاضی است:
  ۱) مزیت مثبت در هر معامله (احتمال برد × سود برد > احتمال باخت × زیان باخت + کارمزد).
  ۲) بقا: اندازهٔ موقعیت طوری باشد که «نیم‌شدن حساب» احتمالش کم باشد.
  ۳) زمان: رشد مرکب کند است؛ عددها را همین‌جا می‌بینی، نه با شعار.

این پرونده سه خروجی می‌دهد:
  • کسر کِلی (اندازهٔ درست هر معامله) و نسخهٔ محافظه‌کارانهٔ نصف‌کِلی.
  • شبیه‌سازی ۲۰٬۰۰۰ مسیر (Monte Carlo) با کارمزد واقعی: احتمال نیم‌شدن حساب، احتمال سود،
    میانهٔ دارایی در پایان، و بازهٔ ۱۰٪ تا ۹۰٪.
  • مسیر رشد: با این مزیت و این اندازه، چند معامله/چند ماه تا هدف.

هیچ‌جا «تضمین» نیست؛ اگر عددها بد باشند، همان‌طور نشان داده می‌شوند. برای اینکه شبیه‌سازی
تقلب نکند: کارمزد از هر معامله کسر می‌شود و دانهٔ تصادفی (seed) ثابت است تا نتیجه بازتولیدپذیر باشد.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

import investor_test as inv  # noqa: E402
import reportkit as rk  # noqa: E402

VERSION = "0.1.0"
DATA = BASE / "data"
REPORT_HTML = DATA / "bankroll.html"
REPORT_MD = DATA / "bankroll.md"
REPORT_JSON = DATA / "bankroll.json"

RUIN_LEVEL = 0.50          # «نیم‌شدن حساب» = ورشکستگی عملی برای سرمایهٔ کوچک
DEFAULT_TRIALS = 20_000
DEFAULT_SEED = 7
STOCK_ROUND_TRIP_PCT = round((0.00464 + 0.00964) * 100, 4)   # خرید+فروش سهم
OPTION_ROUND_TRIP_PCT = round((0.00103 * 2) * 100, 4)         # خرید+فروش اختیار


def kelly(win_prob: float, win_pct: float, loss_pct: float) -> dict:
    """اندازهٔ درست هر معامله: f = (p·b − q) ÷ b که b = سودبرد÷زیان‌باخت.

    خروجی هم کسر کِلی است، هم نصف‌کِلی (محافظه‌کارانه) — چون فرض‌های واقعی از این ساده‌ترند.
    """
    p = float(win_prob)
    q = 1 - p
    w = float(win_pct) / 100
    l = float(loss_pct) / 100
    if w <= 0 or l <= 0:
        return {"ok": False, "detail": "سود برد و زیان باخت باید مثبت باشند."}
    b = w / l
    f = (p * b - q) / b
    edge = p * w - q * l
    return {
        "ok": True, "win_prob": p, "win_pct": win_pct, "loss_pct": loss_pct,
        "edge_pct_per_trade": round(edge * 100, 4),
        "kelly_fraction": round(max(0.0, f), 4),
        "half_kelly_fraction": round(max(0.0, f) / 2, 4),
        "positive_edge": edge > 0,
        "detail": ("مزیت مثبت است؛ اندازهٔ پیشنهادی = " + f"{max(0.0, f) * 100:.2f}٪ سرمایه در هر "
                   "معامله و نسخهٔ محافظه‌کارانه نصف آن." if edge > 0 else
                   "مزیت منفی یا صفر است: با این فرض‌ها معامله‌کردن، پول‌سوزی است. اول مزیت را "
                   "درست کن، بعد اندازه را."),
    }


def breakeven_win_rate(win_pct: float, loss_pct: float, fee_pct: float = 0.0) -> dict:
    """کم‌ترین نرخ برد برای اینکه بازی سر به سر شود (بعد از کارمزد)."""
    w = float(win_pct) / 100
    l = float(loss_pct) / 100
    f = float(fee_pct) / 100
    if w + l <= 0:
        return {"ok": False, "detail": "سود و زیان باید مثبت باشند."}
    p = (l + f) / (w + l)
    return {"ok": True, "breakeven_win_prob": round(p, 4), "breakeven_win_pct": round(p * 100, 2),
            "detail": (f"با سود برد {win_pct:.1f}٪ و زیان باخت {loss_pct:.1f}٪ و کارمزد رفت‌وبرگشت "
                       f"{fee_pct:.3f}٪، کم‌ترین نرخ برد لازم {p * 100:.2f}٪ است. زیر آن، هر "
                       f"استراتژی‌ای بازنده است — ریاضی، نه نظر.")}


def simulate(*, capital: float = 100_000_000.0, win_prob: float = 0.55, win_pct: float = 8.0,
             loss_pct: float = 5.0, risk_fraction: float = 0.10, trades: int = 48,
             fee_pct: float = STOCK_ROUND_TRIP_PCT, trials: int = DEFAULT_TRIALS,
             seed: int = DEFAULT_SEED, ruin_level: float = RUIN_LEVEL,
             notional_ratio: float = 1.0) -> dict:
    """Monte Carlo: هزاران مسیر ممکن با همان مزیت و همان کارمزد.

    فرض صریح کارمزد: کارمزد رفت‌وبرگشت روی **ارزش معامله** بسته می‌شود
    (`notional_ratio` برابر ارزش معامله ÷ سرمایهٔ حساب). با `notional_ratio=1` یعنی هر معامله
    به اندازهٔ کل حساب است — همان فرضی که برای معامله‌گر خرد واقع‌بینانه است و عدد را بدبینانه،
    نه خوش‌بینانه، نشان می‌دهد.
    """
    rng = random.Random(seed)
    finals: list[float] = []
    ruin = 0
    reached_double = 0
    best, worst = 0.0, float("inf")
    for _ in range(trials):
        eq = capital
        ruined = False
        for _t in range(trades):
            fee_cost = notional_ratio * fee_pct / 100
            if rng.random() < win_prob:
                eq *= (1 + risk_fraction * win_pct / 100 - fee_cost)
            else:
                eq *= (1 - risk_fraction * loss_pct / 100 - fee_cost)
            if eq <= capital * ruin_level:
                ruined = True
                break
        if ruined:
            ruin += 1
        if eq >= capital * 2:
            reached_double += 1
        finals.append(eq)
        best = max(best, eq)
        worst = min(worst, eq)
    finals.sort()

    def pct_at(p: float) -> float:
        idx = min(len(finals) - 1, max(0, int(p * len(finals))))
        return finals[idx]

    median = pct_at(0.50)
    return {
        "ok": True, "capital": capital, "trials": trials, "trades": trades, "seed": seed,
        "risk_fraction": risk_fraction, "fee_pct": fee_pct, "notional_ratio": notional_ratio,
        "ruin_prob": round(ruin / trials, 4), "double_prob": round(reached_double / trials, 4),
        "profit_prob": round(sum(1 for f in finals if f > capital) / trials, 4),
        "median_final": round(median, 2),
        "median_multiple": round(median / capital, 3),
        "p10_final": round(pct_at(0.10), 2), "p90_final": round(pct_at(0.90), 2),
        "best_final": round(best, 2), "worst_final": round(worst, 2),
        "ruin_level": ruin_level,
        "detail": (f"در {trials:,} مسیر فرضی با نرخ برد {win_prob * 100:.0f}٪ و اندازهٔ "
                   f"{risk_fraction * 100:.0f}٪ در هر معامله و کارمزد {fee_pct:.3f}٪ روی ارزش "
                   f"معامله: احتمال نیم‌شدن حساب {ruin / trials * 100:.2f}٪ · احتمال دوبرابر‌شدن "
                   f"{reached_double / trials * 100:.2f}٪ · میانهٔ پایان {median / capital:.2f} "
                   f"برابر شروع."),
    }


def path(*, capital: float, monthly_return_pct: float, target: float,
         fee_drag_pct_month: float = 0.0) -> dict:
    """چند ماه تا هدف، با رشد مرکب و کسر کارمزد ماهانه (بدون شعار، فقط لگاریتم)."""
    net = monthly_return_pct - fee_drag_pct_month
    if target <= capital:
        return {"ok": False, "detail": "هدف باید بزرگ‌تر از سرمایهٔ فعلی باشد."}
    if net <= 0:
        return {"ok": True, "months": None, "years": None, "net_monthly_pct": round(net, 4),
                "detail": ("با این بازده و این کارمزد، رشد صفر یا منفی است؛ هدف با هیچ زمانی "
                           "به‌دست نمی‌آید. اول مزیت را مثبت کن، بعد به زمان فکر کن.")}
    months = math.log(target / capital) / math.log(1 + net / 100)
    return {"ok": True, "months": round(months, 1), "years": round(months / 12, 1),
            "net_monthly_pct": round(net, 4),
            "needed_multiple": round(target / capital, 3),
            "detail": (f"با {net:.2f}٪ رشد خالص ماهانه، از {capital:,.0f} به {target:,.0f} "
                       f"می‌رسد در حدود {months:.1f} ماه ({months / 12:.1f} سال) — به‌شرط اینکه "
                       f"رشد مثبت بماند و هیچ ماه بحرانی حساب را نصف نکند.")}


def strategy_path(*, capital: float, annualized_pct: float, target: float,
                  churn_per_year: float = 1.0,
                  fee_pct_round_trip: float = STOCK_ROUND_TRIP_PCT) -> dict:
    """مسیر رشد با «عدد راهبرد» و «تعداد چرخش در سال».

    برخلاف کِلی که فرض‌های احتمالاتی دارد، این‌جا عدد راهبرد (همان که پلهٔ تصمیم می‌دهد) می‌آید،
    چرخش سالانه و کارمزد کسر می‌شود، و بعد زمان رسیدن به هدف حساب می‌شود.
    """
    fee_drag_pp = churn_per_year * fee_pct_round_trip
    net_annual = float(annualized_pct) - fee_drag_pp
    if net_annual <= 0:
        return {"ok": True, "net_annual_pct": round(net_annual, 3), "months": None, "years": None,
                "churn_per_year": churn_per_year, "fee_drag_pp": round(fee_drag_pp, 3),
                "detail": (f"با {churn_per_year:g} چرخش در سال، کارمزد {fee_drag_pp:.2f} واحد درصد "
                           f"از بازده کم می‌کند و بازده خالص {net_annual:.2f}٪ می‌شود؛ یعنی منفی. "
                           f"یا مزیت باید بزرگ‌تر شود یا چرخش کمتر.")}
    monthly = (1 + net_annual / 100) ** (1 / 12) - 1
    months = math.log(target / capital) / math.log(1 + monthly) if target > capital else 0.0
    return {"ok": True, "net_annual_pct": round(net_annual, 3), "monthly_pct": round(monthly * 100, 4),
            "months": round(months, 1), "years": round(months / 12, 1),
            "churn_per_year": churn_per_year, "fee_drag_pp": round(fee_drag_pp, 3),
            "detail": (f"راهبرد سالانه {annualized_pct:.2f}٪ می‌دهد؛ با {churn_per_year:g} چرخش در "
                       f"سال و کارمزد {fee_pct_round_trip:.3f}٪، خالص {net_annual:.2f}٪ می‌شود. "
                       f"با همین رشد مرکب، {target / capital:.1f} برابر شدن حدود {months:.1f} ماه "
                       f"({months / 12:.1f} سال) طول می‌کشد.")}


def honesty_checks(capital: float = 100_000_000.0) -> list[dict]:
    """سه آزمون صادقانه: کارمزد، نرخ برد، و اندازهٔ موقعیت — که هرکدام می‌تواند بازی را ببندد."""
    be = breakeven_win_rate(win_pct=8.0, loss_pct=5.0, fee_pct=STOCK_ROUND_TRIP_PCT)
    small = simulate(capital=capital, risk_fraction=0.05, trials=6000)
    big = simulate(capital=capital, risk_fraction=0.40, trials=6000)
    return [
        {"title": "کارمزد رفت‌وبرگشت سهم چقدر است؟",
         "value": f"{STOCK_ROUND_TRIP_PCT}٪ (سهم) · {OPTION_ROUND_TRIP_PCT}٪ (اختیار)",
         "why": "روزی دو رفت‌وبرگشت با سرمایهٔ کوچک، سالانه بیش از ۳۰٪ سرمایه را کارمزد می‌دهد؛ "
                "همین یک عدد، بیشتر معامله‌گران روزانه را بازنده می‌کند.",
         "verdict": "پس: چرخش کم، نگه‌داشتن تا سررسید، و پرهیز از معاملهٔ بی‌مزیت."},
        {"title": "کم‌ترین نرخ برد لازم", "value": f"{be['breakeven_win_pct']}٪",
         "why": be["detail"],
         "verdict": "نرخ برد خودت را از دفتر حساب کن (نه از حافظه) و با این عدد بسنج."},
        {"title": "اندازهٔ موقعیت: ۵٪ در برابر ۴۰٪",
         "value": f"نیم‌شدن حساب: {small['ruin_prob'] * 100:.2f}٪ در برابر {big['ruin_prob'] * 100:.2f}٪",
         "why": ("با اندازهٔ کوچک‌تر، احتمال دوبرابر‌شدن کمتر ولی احتمال ورشکستگی بسیار کمتر است؛ "
                 "با اندازهٔ درشت، همان مزیت به ورشکستگی می‌رسد."),
         "verdict": "برای سرمایهٔ کوچک، بقا مهم‌تر از سرعت است: اندازهٔ کوچک، عمر طولانی."},
    ]


def build(*, capital: float = 100_000_000.0, target: float | None = None,
          win_prob: float = 0.55, win_pct: float = 8.0, loss_pct: float = 5.0,
          trades: int = 48, trials: int = DEFAULT_TRIALS, strategy_annualized_pct: float = 68.482,
          churn_per_year: float = 1.0, write: bool = True, html: Path | str | None = None,
          md: Path | str | None = None, jsonf: Path | str | None = None) -> dict:
    tgt = float(target or capital * 4)
    k = kelly(win_prob, win_pct, loss_pct)
    frac = k["half_kelly_fraction"] if k.get("ok") and k["half_kelly_fraction"] else 0.10
    sim = simulate(capital=capital, win_prob=win_prob, win_pct=win_pct, loss_pct=loss_pct,
                   risk_fraction=frac, trades=trades, trials=trials)
    spath = strategy_path(capital=capital, annualized_pct=strategy_annualized_pct, target=tgt,
                          churn_per_year=churn_per_year)
    trades_per_month = 2
    per_month_pct = (k["edge_pct_per_trade"] * frac * trades_per_month) if k.get("ok") else 0.0
    fee_drag = STOCK_ROUND_TRIP_PCT * frac * trades_per_month
    plan = path(capital=capital, monthly_return_pct=per_month_pct, target=tgt,
                fee_drag_pct_month=fee_drag)
    doc = {
        "version": VERSION, "capital": capital, "target": tgt,
        "kelly": k, "used_risk_fraction": frac, "sim": sim, "path": plan, "strategy_path": spath,
        "strategy_annualized_pct": strategy_annualized_pct, "churn_per_year": churn_per_year,
        "breakeven": breakeven_win_rate(win_pct=win_pct, loss_pct=loss_pct,
                                        fee_pct=STOCK_ROUND_TRIP_PCT),
        "checks": honesty_checks(capital), "trades_per_month": trades_per_month,
        "engine_fees_pct": {"stock_round_trip": STOCK_ROUND_TRIP_PCT,
                            "option_round_trip": OPTION_ROUND_TRIP_PCT},
        "honesty": ("هیچ‌کدام از این عددها وعدهٔ سود نیست. شبیه‌سازی با فرض‌های خودتان اجرا "
                    "می‌شود؛ اگر نرخ برد واقعی شما کمتر از عدد سر‌به‌سر باشد، همین جدول "
                    "«زیان» نشان می‌دهد. دانهٔ تصادفی ثابت است تا نتیجه بازتولیدپذیر باشد."),
    }
    doc["md_text"] = to_md(doc)
    if write:
        body = ['<div class="honest"><b>این پرونده وعدهٔ سود نیست؛ ریاضیِ بقا و رشد است.</b> '
                'می‌گوید با این مزیت و این کارمزد، هزاران مسیر ممکن چه شکلی دارند و کدام‌شان '
                'حساب را نصف می‌کنند. عددها با فرض‌های خودتان بازتولیدپذیرند.</div>',
                f'<p class="sub">{rk.esc(doc["honesty"])}</p>',
                "<h2>۱. اندازهٔ درست هر معامله (کِلی)</h2>",
                f'<p><b>مزیت هر معامله:</b> {k.get("edge_pct_per_trade")}٪ · '
                f'<b>کسر کِلی:</b> {k.get("kelly_fraction")} · '
                f'<b>نصف‌کِلی (محافظه‌کارانه، همان چیزی که این‌جا استفاده شد):</b> '
                f'{doc["used_risk_fraction"]}</p>',
                f'<p class="note">{rk.esc(k.get("detail", ""))}</p>',
                "<h2>۲. کم‌ترین نرخ برد لازم</h2>",
                f'<p>{rk.esc(doc["breakeven"]["detail"])}</p>',
                "<h2>۳. شبیه‌سازی مسیرها</h2>",
                '<table><tbody>',
                f'<tr><td>احتمال نیم‌شدن حساب</td><td class="num">{sim["ruin_prob"] * 100:.2f}٪</td></tr>',
                f'<tr><td>احتمال دوبرابر‌شدن</td><td class="num">{sim["double_prob"] * 100:.2f}٪</td></tr>',
                f'<tr><td>احتمال سود</td><td class="num">{sim["profit_prob"] * 100:.2f}٪</td></tr>',
                f'<tr><td>میانهٔ پایان</td><td class="num">{rk.num(sim["median_final"])} '
                f'({sim["median_multiple"]}× شروع)</td></tr>',
                f'<tr><td>بازهٔ ۱۰٪ تا ۹۰٪</td><td class="num">{rk.num(sim["p10_final"])} تا '
                f'{rk.num(sim["p90_final"])}</td></tr>',
                '</tbody></table>',
                f'<p class="note">{rk.esc(sim["detail"])}</p>',
                "<h2>۴. چند وقت تا هدف</h2>",
                f'<p><b>مسیر کِلی (مدل فرضی، کارمزد روی مبلغ ریسک):</b> {rk.esc(plan.get("detail", ""))}</p>',
                f'<p><b>مسیر راهبرد (با عدد واقعی برنامه):</b> {rk.esc(spath.get("detail", ""))}</p>',
                f'<p class="sub">عدد راهبرد = {strategy_annualized_pct:.3f}٪ سالانه (میان بر: همبسته '
                f'با «مبنا»ی اسنپ‌شات) · چرخش سالانه {churn_per_year:g} بار · کارمزد رفت‌وبرگشت '
                f'{STOCK_ROUND_TRIP_PCT}٪ (سهم). اگر راهبرد را تا سررسید نگه دارید و سالی یک بار '
                f'بچرخانید، کارمزد کوچک و بازده تقریباً دست‌نخورده می‌ماند؛ اگر ماهی چند بار '
                f'بچرخانید، کارمزد مزیت را می‌خورد.</p>',
                "<h2>۵. سه آزمون صادقانه</h2>"]
        for c in doc["checks"]:
            body.append(f'<p><b>{rk.esc(c["title"])}</b> — {rk.esc(str(c["value"]))}<br>'
                        f'<span class="hint">{rk.esc(c["why"])}</span><br>'
                        f'<span class="ok">{rk.esc(c["verdict"])}</span></p>')
        body.append('<p class="sub">✍️ تهیه‌کنندهٔ جزوات: <b>Masoud Mojarabian</b> · 📱 +989126630554 · '
                    '✈️ <a href="https://t.me/Mojarabian">Telegram: Mojarabian</a> · '
                    '📸 <a href="https://instagram.com/Mojarabian.Art">Instagram: Mojarabian.Art</a></p>')
        hp = Path(html or REPORT_HTML)
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(rk.page("ریاضیِ پول — بقا، اندازهٔ موقعیت و مسیر رشد", "".join(body),
                              subtitle=f"سرمایه {rk.num(capital)} · هدف {rk.num(tgt)} · "
                                       f"{sim['trials']:,} مسیر"),
                      encoding="utf-8")
        Path(md or REPORT_MD).write_text(doc["md_text"], encoding="utf-8")
        Path(jsonf or REPORT_JSON).write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
        doc.update({"html": str(hp), "md": str(md or REPORT_MD), "json": str(jsonf or REPORT_JSON)})
    return doc


def to_md(doc: dict) -> str:
    k, sim, plan = doc["kelly"], doc["sim"], doc["path"]
    L = [f"# ریاضیِ پول — نسخهٔ {VERSION}", "",
         f"سرمایه: {doc['capital']:,.0f} · هدف: {doc['target']:,.0f} · "
         f"معامله در ماه (فرض): {doc['trades_per_month']}", "",
         f"> {doc['honesty']}", "",
         "## ۱. اندازهٔ درست هر معامله", "",
         f"- مزیت هر معامله: {k.get('edge_pct_per_trade')}٪",
         f"- کسر کِلی: {k.get('kelly_fraction')} · نصف‌کِلی: {k.get('half_kelly_fraction')}",
         f"- اندازهٔ استفاده‌شده در شبیه‌سازی: {doc['used_risk_fraction']}",
         f"- {k.get('detail', '')}", "",
         "## ۲. کم‌ترین نرخ برد لازم", "",
         f"- {doc['breakeven']['detail']}", "",
         "## ۳. شبیه‌سازی مسیرها", "",
         f"- احتمال نیم‌شدن حساب: {sim['ruin_prob'] * 100:.2f}٪",
         f"- احتمال دوبرابر‌شدن: {sim['double_prob'] * 100:.2f}٪",
         f"- احتمال سود: {sim['profit_prob'] * 100:.2f}٪",
         f"- میانهٔ پایان: {sim['median_final']:,.0f} ({sim['median_multiple']}× شروع)",
         f"- بازهٔ ۱۰٪ تا ۹۰٪: {sim['p10_final']:,.0f} تا {sim['p90_final']:,.0f}",
         f"- بدترین مسیر: {sim['worst_final']:,.0f} · بهترین مسیر: {sim['best_final']:,.0f}", "",
         "## ۴. چند وقت تا هدف", "",
         f"- مسیر کِلی (مدل فرضی، کارمزد روی مبلغ ریسک): {plan.get('detail', '')}",
         f"- مسیر راهبرد (عدد واقعی برنامه {doc['strategy_annualized_pct']:.3f}٪ سالانه، "
         f"{doc['churn_per_year']:g} چرخش در سال): {doc['strategy_path'].get('detail', '')}", "",
         "## ۵. سه آزمون صادقانه", ""]
    for c in doc["checks"]:
        L += [f"### {c['title']}", f"- عدد: {c['value']}", f"- چرا: {c['why']}",
              f"- نتیجه: {c['verdict']}", ""]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ریاضیِ پول: کِلی، ورشکستگی، مسیر رشد")
    ap.add_argument("--capital", type=float, default=100_000_000.0, help="سرمایه (ریال)")
    ap.add_argument("--target", type=float, default=None)
    ap.add_argument("--win-prob", type=float, default=0.55)
    ap.add_argument("--win", type=float, default=8.0, help="درصد سود برد")
    ap.add_argument("--loss", type=float, default=5.0, help="درصد زیان باخت")
    ap.add_argument("--trades", type=int, default=48)
    ap.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    ap.add_argument("--strategy", type=float, default=68.482, help="بازده سالانهٔ راهبرد (٪)")
    ap.add_argument("--churn", type=float, default=1.0, help="چند بار در سال می‌چرخانید")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    doc = build(capital=a.capital, target=a.target, win_prob=a.win_prob, win_pct=a.win,
                loss_pct=a.loss, trades=a.trades, trials=a.trials,
                strategy_annualized_pct=a.strategy, churn_per_year=a.churn,
                write=not a.no_write)
    if a.json:
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 0
    k, sim, plan = doc["kelly"], doc["sim"], doc["path"]
    print(f"ریاضیِ پول — سرمایه {a.capital:,.0f} · هدف {doc['target']:,.0f}")
    print(f"  مزیت هر معامله: {k.get('edge_pct_per_trade')}٪ · کسر کِلی {k.get('kelly_fraction')} · "
          f"نصف‌کِلی {k.get('half_kelly_fraction')}")
    print(f"  کم‌ترین نرخ برد لازم: {doc['breakeven']['breakeven_win_pct']}٪")
    print(f"  شبیه‌سازی {sim['trials']:,} مسیر: نیم‌شدن {sim['ruin_prob'] * 100:.2f}٪ · "
          f"دوبرابر‌شدن {sim['double_prob'] * 100:.2f}٪ · میانه {sim['median_multiple']}× ")
    print(f"  مسیر کِلی: {plan.get('detail')}")
    print(f"  مسیر راهبرد: {doc['strategy_path'].get('detail')}")
    for c in doc["checks"]:
        print(f"  · {c['title']}: {c['value']} → {c['verdict']}")
    if doc.get("html"):
        print("  برگه:", doc["html"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
