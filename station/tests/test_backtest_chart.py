# -*- coding: utf-8 -*-
"""بار ۳۰ — نمودار منحنی سرمایه در گزارش پس‌آزمایی (SVG خالص).

spec (vibefarsi chart):
  - SVG خالص بدون وابستگی جاوااسکریپتی
  - محور مقدار سمت راست
  - تیک‌های فارسی (ارقام فارسی، بدون رقم لاتین)
  - جهت زمان راست‌به‌چپ (راست = شروع) مطابق چیدمان RTL گزارش
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import backtest as bt  # noqa: E402

CURVE = [
    {"trade": 0, "date": "شروع", "equity": 20_000_000_000},
    {"trade": 1, "date": "1404/01/02", "equity": 20_500_000_000},
    {"trade": 2, "date": "1404/01/10", "equity": 19_800_000_000},
    {"trade": 3, "date": "1404/02/01", "equity": 22_000_000_000},
    {"trade": 4, "date": "1404/02/20", "equity": 25_000_000_000},
]
CAPITAL = 20_000_000_000


def _texts(svg):
    return re.findall(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>(.*?)</text>', svg)


def _line_xs(svg):
    m = re.search(r'<path class="line" d="([^"]+)"', svg)
    assert m, "مسیر خط پیدا نشد"
    coords = re.findall(r"[-\d.]+", m.group(1))
    return [float(coords[i]) for i in range(0, len(coords), 2)]


def test_to_fa_digits():
    expected = (chr(0x6F1) + "٬" + chr(0x6F2) + chr(0x6F3) + chr(0x6F4)
                + "٫" + chr(0x6F5))
    assert bt._tofa("1,234.5") == expected
    assert bt._tofa("0") == "۰"
    assert bt._tofa("متن") == "متن"


def test_chart_empty_is_empty_state():
    out = bt._equity_chart_svg([], CAPITAL)
    assert "<svg" not in out
    assert "chart-empty" in out
    assert "هنوز معامله‌ای" in out
    out2 = bt._equity_chart_svg([CURVE[0]], CAPITAL)
    assert "<svg" not in out2
    assert "chart-empty" in out2


def test_chart_svg_structure():
    svg = bt._equity_chart_svg(CURVE, CAPITAL)
    assert '<svg viewBox="0 0 760 300" role="img"' in svg
    assert "aria-label" in svg
    assert "<title>" in svg
    assert '<path class="line"' in svg
    assert '<path class="area"' in svg
    assert "<circle" in svg
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg


def test_value_axis_is_on_the_right():
    svg = bt._equity_chart_svg(CURVE, CAPITAL)
    texts = _texts(svg)
    # تیک‌های محور مقدار: ارقام فارسی، همه سمت راست (x >= 665)
    tick_labels = [(x, lab) for x, y, lab in texts
                if re.fullmatch(r"[\u06F0-\u06F9\u066B]+", lab) and 20 <= float(y) <= 260]
    assert len(tick_labels) >= 4, f"انتظار تیک‌های محور مقدار بود، شد {len(tick_labels)}"
    for x, _ in tick_labels:
        assert float(x) >= 665, f"تیک محور مقدار در x={x} (باید سمت راست باشد)"
    # عنوان واحد هم سمت راست است
    unit = [(x, lab) for x, y, lab in texts if "میلیارد" in lab]
    assert unit and float(unit[0][0]) >= 665


def test_time_flows_right_to_left():
    svg = bt._equity_chart_svg(CURVE, CAPITAL)
    xs = _line_xs(svg)
    assert xs[0] > xs[-1], f"زمان باید راست‌به‌چپ باشد؛ x شروع={xs[0]}، x پایان={xs[-1]}"
    # «شروع» روی محور x باید سمت‌راست‌ترین برچسب زمان باشد
    texts = _texts(svg)
    start = [x for x, y, lab in texts if lab == "شروع" and float(y) > 260]
    assert start and float(start[0]) >= 660


def test_ticks_are_persian_digits():
    svg = bt._equity_chart_svg(CURVE, CAPITAL)
    texts = _texts(svg)
    assert texts, "برچسب روی نمودار پیدا نشد"
    for x, y, lab in texts:
        assert not re.search(r"[0-9]", lab), f"رقم لاتین در برچسب: {lab}"
    # دست‌کم چند برچسب عددیِ فارسی باشد
    assert any(re.search(r"[۰-۹]", lab) for _, _, lab in texts)


def test_start_capital_reference_line():
    svg = bt._equity_chart_svg(CURVE, CAPITAL)
    assert 'class="ref"' in svg
    # اگر سرمایهٔ شروع بیرون از محدودهٔ منحنی باشد، خط مرجع نمی‌آید
    svg2 = bt._equity_chart_svg(CURVE, 1_000_000_000)
    assert 'class="ref"' not in svg2


def test_report_contains_chart(tmp_path):
    hist = BASE / "demo" / "history-demo.csv"
    assert hist.is_file(), f"پروندۀ تاریخ نمونه نیست: {hist}"
    res = bt.run_backtest(hist)
    assert len(res["equity_curve"]) >= 2
    out = bt.build_report(res, tmp_path / "bt.html")
    doc = out.read_text(encoding="utf-8")
    assert "منحنی سرمایه" in doc
    assert '<svg viewBox="0 0 760 300" role="img"' in doc
    assert "میلیارد ریال" in doc
    # برچسب‌های فارسی بدون رقم لاتین
    for x, y, lab in _texts(doc):
        assert not re.search(r"[0-9]", lab), f"رقم لاتین در برچسب نمودار: {lab}"


def test_report_empty_curve_shows_empty_state(tmp_path):
    s = {
        "file": "x.csv", "generated_at": "t", "rows": 0, "taken": 0, "skipped": 0,
        "hit_rate_pct": None, "false_positive_rate_pct": None,
        "missed_opportunity_rate_pct": None, "avg_expected_annualized_pct": None,
        "avg_realized_annualized_pct": None, "avg_forecast_error_pp": None,
        "final_equity": CAPITAL, "start_capital": CAPITAL, "equity_change_pct": 0.0,
        "rules": {"min_edge_arbitrage_pct": 3, "min_edge_leveraged_pct": 5,
                  "min_liquidity_contracts_per_day": 20, "position_weight": 0.25},
    }
    res = {"summary": s, "decisions": [], "equity_curve": [{"trade": 0, "date": "شروع", "equity": CAPITAL}],
           "best": [], "worst": [], "missed": [], "by_kind": {}}
    out = bt.build_report(res, tmp_path / "bt-empty.html")
    doc = out.read_text(encoding="utf-8")
    assert "<svg" not in doc
    assert "chart-empty" in doc
    assert "هنوز معامله‌ای" in doc
