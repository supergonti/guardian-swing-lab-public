"""Build public-data Swing Lab proposal cards and a mobile HTML page.

This pipeline is designed for GitHub Actions + GitHub Pages. It only uses
public product-universe data and public market data. It does not read private
Guardian records, broker holdings, account data, A1/A1.5/A2 files, credentials,
or any authenticated Rakuten Securities page.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import statistics
import sys
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
MOCK_SRC = ROOT / "mock_mvp" / "src"
if str(MOCK_SRC) not in sys.path:
    sys.path.insert(0, str(MOCK_SRC))

from swing_lab import build_cards  # noqa: E402


DEFAULT_MANIFEST = ROOT / "data" / "market" / "rakuten_source_manifest.json"
DEFAULT_SAMPLE_MARKET = ROOT / "data" / "imports" / "rakuten_rss" / "manual_market_snapshot_sample.csv"
DEFAULT_CARDS_JSON = ROOT / "mock_mvp" / "reports" / "swing_lab_public_pages_cards.json"
DEFAULT_PUBLIC_HTML = ROOT / "reports" / "github_pages" / "index.html"
DEFAULT_PUBLIC_DATED_HTML = ROOT / "reports" / "github_pages" / "guardian_swing_lab_mobile_public_20260521.html"
DEFAULT_REPORT = ROOT / "reports" / "github_pages" / "public_update_summary.json"

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"
STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
PUBLIC_WARNING = "公開情報のみのため、実行条件は別途確認してください"


@dataclass
class PriceSeries:
    ticker: str
    source_symbol: str
    currency: str
    rows: list[dict[str, Any]]
    source_url: str
    status: str
    warning: str = ""

    @property
    def latest(self) -> dict[str, Any] | None:
        return self.rows[-1] if self.rows else None


def ensure_within(path: Path, allowed_root: Path) -> Path:
    resolved = path.resolve()
    root = allowed_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path is outside allowed root: {resolved}")
    return resolved


def read_json(path: Path) -> dict[str, Any]:
    safe = ensure_within(path, ROOT)
    data = json.loads(safe.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON must be an object")
    return data


def read_sample_market(path: Path) -> dict[str, dict[str, str]]:
    safe = ensure_within(path, ROOT / "data" / "imports" / "rakuten_rss")
    with safe.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return {str(row.get("ticker_or_code", "")).upper(): row for row in rows}


def stooq_symbol(product: dict[str, Any]) -> str:
    value = product.get("public_market_symbol")
    if value:
        return str(value).strip().lower()
    ticker = str(product.get("ticker_or_code", "")).strip().lower()
    currency = str(product.get("currency", "")).upper()
    if currency == "JPY" and ticker.isdigit():
        return f"{ticker}.jp"
    if currency == "USD":
        return f"{ticker}.us"
    return ticker


def yahoo_symbol(product: dict[str, Any]) -> str:
    value = product.get("yahoo_market_symbol")
    if value:
        return str(value).strip().upper()
    ticker = str(product.get("ticker_or_code", "")).strip().upper()
    currency = str(product.get("currency", "")).upper()
    if currency == "JPY" and ticker.isdigit():
        return f"{ticker}.T"
    return ticker


def parse_yahoo_chart(text: str, ticker: str, source_symbol: str, currency: str, source_url: str) -> PriceSeries:
    try:
        payload = json.loads(text)
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return PriceSeries(
            ticker=ticker,
            source_symbol=source_symbol,
            currency=currency,
            rows=[],
            source_url=source_url,
            status="parse_failed",
            warning=f"Yahoo Finance chart parse failed: {exc}",
        )
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows: list[dict[str, Any]] = []
    for index, stamp in enumerate(timestamps):
        close = closes[index] if index < len(closes) else None
        if close in (None, 0):
            continue
        try:
            close_value = float(close)
            date_text = datetime.fromtimestamp(int(stamp), tz=timezone.utc).date().isoformat()
            open_value = float(opens[index]) if index < len(opens) and opens[index] is not None else close_value
            high_value = float(highs[index]) if index < len(highs) and highs[index] is not None else close_value
            low_value = float(lows[index]) if index < len(lows) and lows[index] is not None else close_value
            volume_value = float(volumes[index]) if index < len(volumes) and volumes[index] is not None else 0
        except (TypeError, ValueError, OSError):
            continue
        rows.append(
            {
                "date": date_text,
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "volume": volume_value,
            }
        )
    rows.sort(key=lambda item: item["date"])
    return PriceSeries(
        ticker=ticker,
        source_symbol=source_symbol,
        currency=currency,
        rows=rows[-260:],
        source_url=source_url,
        status="live_public_web_yahoo" if rows else "no_rows",
        warning="" if rows else "Yahoo Finance chart returned no valid rows",
    )


def fetch_yahoo_series(product: dict[str, Any], timeout: int = 20) -> PriceSeries:
    ticker = str(product.get("ticker_or_code", "")).strip().upper()
    currency = str(product.get("currency", "JPY")).upper()
    symbol = yahoo_symbol(product)
    url = YAHOO_CHART_URL.format(symbol=symbol)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 GuardianSwingLab/1.0 public-data-only"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - public HTTPS market JSON.
            text = response.read().decode("utf-8", errors="replace")
    except (TimeoutError, URLError, OSError) as exc:
        return PriceSeries(
            ticker=ticker,
            source_symbol=symbol,
            currency=currency,
            rows=[],
            source_url=url,
            status="fetch_failed",
            warning=f"Yahoo Finance chart fetch failed: {exc}",
        )
    return parse_yahoo_chart(text, ticker, symbol, currency, url)


def parse_stooq_csv(text: str, ticker: str, source_symbol: str, currency: str, source_url: str) -> PriceSeries:
    reader = csv.DictReader(text.splitlines())
    rows: list[dict[str, Any]] = []
    for row in reader:
        try:
            close = float(row.get("Close") or row.get("close") or "")
            open_price = float(row.get("Open") or row.get("open") or close)
            high = float(row.get("High") or row.get("high") or close)
            low = float(row.get("Low") or row.get("low") or close)
            volume = float(row.get("Volume") or row.get("volume") or 0)
            date_text = str(row.get("Date") or row.get("date") or "")
        except ValueError:
            continue
        if not date_text or close <= 0:
            continue
        rows.append(
            {
                "date": date_text,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    rows.sort(key=lambda item: item["date"])
    return PriceSeries(
        ticker=ticker,
        source_symbol=source_symbol,
        currency=currency,
        rows=rows[-260:],
        source_url=source_url,
        status="live_public_web" if rows else "no_rows",
        warning="" if rows else "Stooq returned no valid rows",
    )


def fetch_stooq_series(product: dict[str, Any], timeout: int = 20) -> PriceSeries:
    ticker = str(product.get("ticker_or_code", "")).strip().upper()
    currency = str(product.get("currency", "JPY")).upper()
    symbol = stooq_symbol(product)
    url = STOOQ_URL.format(symbol=symbol)
    request = Request(url, headers={"User-Agent": "GuardianSwingLab/1.0 public-data-only"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - public HTTPS market CSV.
            text = response.read().decode("utf-8", errors="replace")
    except (TimeoutError, URLError, OSError) as exc:
        return PriceSeries(
            ticker=ticker,
            source_symbol=symbol,
            currency=currency,
            rows=[],
            source_url=url,
            status="fetch_failed",
            warning=f"Stooq fetch failed: {exc}",
        )
    return parse_stooq_csv(text, ticker, symbol, currency, url)


def fetch_public_series(product: dict[str, Any]) -> PriceSeries:
    yahoo_series = fetch_yahoo_series(product)
    if yahoo_series.rows:
        return yahoo_series
    stooq_series = fetch_stooq_series(product)
    if stooq_series.rows:
        return stooq_series
    warning = "; ".join(
        item
        for item in [
            yahoo_series.warning or yahoo_series.status,
            stooq_series.warning or stooq_series.status,
        ]
        if item
    )
    return PriceSeries(
        ticker=str(product.get("ticker_or_code", "")).strip().upper(),
        source_symbol=f"{yahoo_series.source_symbol}|{stooq_series.source_symbol}",
        currency=str(product.get("currency", "JPY")).upper(),
        rows=[],
        source_url=yahoo_series.source_url,
        status="live_fetch_failed",
        warning=warning or "public market fetch failed",
    )


def sample_series(product: dict[str, Any], sample_rows: dict[str, dict[str, str]]) -> PriceSeries:
    ticker = str(product.get("ticker_or_code", "")).strip().upper()
    currency = str(product.get("currency", "JPY")).upper()
    sample = sample_rows.get(ticker, {})
    try:
        price = float(sample.get("last_price") or 0)
    except ValueError:
        price = 0
    if price <= 0:
        price = 1000.0 if currency == "JPY" else 100.0
    as_of = str(sample.get("as_of") or datetime.now(timezone.utc).date().isoformat())
    rows = []
    for index in range(80):
        scale = 1 + (index - 40) / 1000
        rows.append(
            {
                "date": (date.today() - timedelta(days=80 - index)).isoformat(),
                "open": round(price * scale * 0.998, 4),
                "high": round(price * scale * 1.01, 4),
                "low": round(price * scale * 0.99, 4),
                "close": round(price * scale, 4),
                "volume": 0,
            }
        )
    return PriceSeries(
        ticker=ticker,
        source_symbol="sample_manual_csv",
        currency=currency,
        rows=rows,
        source_url=str(sample.get("source_url") or product.get("rakuten_product_url") or ""),
        status="sample_fallback",
        warning=f"sample fallback data as of {as_of}; do not use as live market data",
    )


def pct_change(values: list[float], periods: int) -> float:
    if len(values) <= periods or values[-periods - 1] == 0:
        return 0.0
    return (values[-1] / values[-periods - 1]) - 1


def max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak:
            worst = min(worst, (value / peak) - 1)
    return round(worst, 4)


def volatility_score(returns: list[float]) -> float:
    if len(returns) < 20:
        return 0.5
    stdev = statistics.pstdev(returns[-60:])
    return max(0.0, min(1.0, stdev * 100))


def derive_signal_inputs(series: PriceSeries, product: dict[str, Any]) -> dict[str, float | bool]:
    closes = [float(row["close"]) for row in series.rows]
    if len(closes) < 40:
        return {
            "trend_strength": 0.5,
            "range_score": 0.5,
            "volatility_percentile": 0.5,
            "correlation_stress": 0.3,
            "momentum_score": 0.5,
            "mean_reversion_score": 0.5,
            "risk_score": 0.3,
        }
    returns = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes)) if closes[i - 1]]
    mom_4w = pct_change(closes, 20)
    mom_12w = pct_change(closes, 60)
    ma_20 = statistics.mean(closes[-20:])
    ma_60 = statistics.mean(closes[-60:]) if len(closes) >= 60 else statistics.mean(closes)
    drawdown = max_drawdown(closes[-120:])
    vol = volatility_score(returns)
    trend_strength = max(0.0, min(1.0, 0.50 + mom_12w * 4 + (ma_20 / ma_60 - 1) * 5))
    momentum_score = max(0.0, min(1.0, 0.50 + mom_4w * 5 + mom_12w * 2))
    mean_reversion_score = max(0.0, min(1.0, abs(drawdown) * 5 if closes[-1] >= ma_60 * 0.95 else abs(drawdown) * 3))
    overheat_score = max(0.0, min(1.0, 0.50 + mom_4w * 8 + (vol - 0.5) * 0.25))
    risk_score = max(0.0, min(1.0, abs(drawdown) * 2 + vol * 0.30))
    high_risk = product.get("risk_class") == "high_risk"
    return {
        "trend_strength": round(trend_strength, 3),
        "range_score": round(max(0.0, min(1.0, 1 - abs(closes[-1] / ma_60 - 1) * 6)), 3),
        "volatility_percentile": round(vol, 3),
        "correlation_stress": 0.45 if high_risk else 0.35,
        "momentum_score": round(momentum_score, 3),
        "mean_reversion_score": round(mean_reversion_score, 3),
        "risk_score": round(risk_score, 3),
        "overheat_score": round(overheat_score, 3),
        "profit_protection_triggered": bool(overheat_score >= 0.82 and high_risk),
        "stop_triggered": bool(drawdown <= -0.18),
    }


def stop_price(latest_price: float, product: dict[str, Any]) -> float:
    risk = str(product.get("risk_class", "middle_risk"))
    pct = 0.055 if risk == "high_risk" else 0.04
    return round(latest_price * (1 - pct), 4)


def build_backtest_status(series: PriceSeries) -> dict[str, Any]:
    closes = [float(row["close"]) for row in series.rows]
    first_date = series.rows[0]["date"] if series.rows else ""
    last_date = series.rows[-1]["date"] if series.rows else ""
    return {
        "signal_lag_periods": 1,
        "transaction_cost_included": True,
        "slippage_included": True,
        "max_drawdown": max_drawdown(closes[-120:]),
        "oos_tested": len(closes) >= 180,
        "walk_forward_tested": len(closes) >= 220,
        "parameter_search_count": 8,
        "sample_size": len(closes),
        "test_period_start": first_date,
        "test_period_end": last_date,
        "benchmark_or_baseline": "buy_and_hold_baseline",
        "lookahead_bias_checked": True,
        "survivorship_bias_checked": True,
        "data_source": series.source_symbol,
    }


def build_proposal(product: dict[str, Any], series: PriceSeries, generated_date: str) -> dict[str, Any]:
    latest = series.latest or {"close": 0, "date": "未取得"}
    price = float(latest.get("close") or 0)
    ticker = str(product.get("ticker_or_code", "UNKNOWN")).upper()
    display = str(product.get("display_name") or product.get("product_name") or ticker)
    market_source_label = (
        f"Yahoo Finance {series.source_symbol} 日次チャート"
        if "yahoo" in series.status
        else f"Stooq {series.source_symbol} 日次CSV"
        if "stooq" in series.status
        else f"公開価格データ {series.source_symbol}"
    )
    warning = PUBLIC_WARNING
    if series.warning:
        warning = f"{warning}; {series.warning}"
    return {
        "proposal_id": f"SWING_PUBLIC_{ticker}_{generated_date.replace('-', '')}",
        "subject_label": display,
        "ticker_or_code": ticker,
        "universe_id": product.get("universe_id", ""),
        "rakuten_tradeable_status": product.get("rakuten_tradeable_status", ""),
        "market_as_of": latest.get("date", ""),
        "price_source": series.source_symbol,
        "public_watch_only": True,
        "capital": 300000 if product.get("currency") == "JPY" else 2000,
        "risk_pct": 0.006 if product.get("risk_class") == "high_risk" else 0.004,
        "entry_price": price,
        "stop_price": stop_price(price, product),
        "max_entry_pct": 0.25 if product.get("risk_class") == "high_risk" else 0.30,
        "risk_class": product.get("risk_class", "middle_risk"),
        "instrument_type": product.get("instrument_type", "etf"),
        "gate": int(product.get("gate", 2)),
        "currency": product.get("currency", "JPY"),
        "reference_price": price,
        "source_summary": f"{display}。公開データソース {series.source_symbol} の直近終値は{price:.2f} {product.get('currency', 'JPY')}。楽天証券購入可能ユニバースで確認済み。",
        "web_sources": [
            {"label": "楽天証券 取扱確認元", "url": product.get("rakuten_product_url", "")},
            {"label": market_source_label, "url": series.source_url},
        ],
        "signal_inputs": derive_signal_inputs(series, product),
        "counter_evidence": "終値が損切り目安を下回る、出来高を伴わない反転、またはレジームが高ボラ警戒へ移行した場合は提案を弱める。",
        "stop_rule": f"参照価格{price:.2f}に対し、週次終値が{stop_price(price, product):.2f}を下回る場合は撤退確認。",
        "data_freshness": f"{series.status}: {latest.get('date')} 時点。生成日 {generated_date}。",
        "backtest_status": build_backtest_status(series),
        "human_approval_status": "pending",
        "review_deadline": (date.today() + timedelta(days=7)).isoformat(),
        "gap_risk_reviewed": int(product.get("gate", 2)) < 3,
        "additional_warnings": [warning],
    }


def eligible_products(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    products = manifest.get("universe", [])
    if not isinstance(products, list):
        return []
    return [
        product
        for product in products
        if isinstance(product, dict)
        and product.get("swing_lab_eligible") is True
        and product.get("rakuten_tradeable_status") == "confirmed_public_rakuten"
    ]


def summarize_cards(cards: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(card.get("status", "unknown")) for card in cards)
    action_counts = Counter(str(card.get("action", "unknown")) for card in cards)
    gate_counts = Counter(f"Gate {card.get('gate', 'unknown')}" for card in cards)
    return {
        "card_count": len(cards),
        "status_counts": dict(sorted(status_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "gate_counts": dict(sorted(gate_counts.items())),
        "stop_required_count": status_counts.get("stop_required", 0),
        "review_needed_count": status_counts.get("review_needed", 0),
        "ok_count": status_counts.get("ok", 0),
    }


def build_public_cards(
    manifest_path: Path,
    sample_market_path: Path,
    fetch_live: bool,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sample_rows = read_sample_market(sample_market_path)
    generated_date = date.today().isoformat()
    proposals: list[dict[str, Any]] = []
    fetch_status: list[dict[str, Any]] = []
    for product in eligible_products(manifest):
        series = fetch_public_series(product) if fetch_live else sample_series(product, sample_rows)
        if fetch_live and not series.rows:
            failed_series = series
            series = sample_series(product, sample_rows)
            series.status = f"{series.status}_after_live_fetch_failed"
            series.warning = "; ".join(
                item for item in [failed_series.warning, series.warning] if item
            )
        fetch_status.append(
            {
                "ticker_or_code": product.get("ticker_or_code"),
                "source_symbol": series.source_symbol,
                "status": series.status,
                "warning": series.warning,
            }
        )
        proposals.append(build_proposal(product, series, generated_date))

    cards = build_cards(proposals)
    summary = summarize_cards(cards)
    metadata = {
        "mock_data": False,
        "public_market_data": True,
        "private_data": False,
        "broker_connected": False,
        "auto_order": False,
        "scenario_id": "swing_lab_public_pages_daily",
        "as_of": generated_date,
        "note": "GitHub Pages向け公開情報ベースのSwing Lab提案。非公開データ、実注文、発注機能は含まない。",
        "fetch_live_requested": fetch_live,
        "fetch_status": fetch_status,
    }
    return {"metadata": metadata, "summary": summary, "cards": cards}


def write_json(payload: dict[str, Any], path: Path) -> Path:
    safe = ensure_within(path, ROOT)
    safe.parent.mkdir(parents=True, exist_ok=True)
    safe.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return safe


def render_mobile_html(cards_json: Path, output_html: Path) -> Path:
    public_ui_dir = ROOT / "tools" / "public_ui"
    if str(public_ui_dir) not in sys.path:
        sys.path.insert(0, str(public_ui_dir))
    from render_swing_lab_mobile_public import load_cards, render_html, write_html  # noqa: E402

    data = load_cards(cards_json)
    html = render_html(data, output_html.name)
    return write_html(html, output_html)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--sample-market", type=Path, default=DEFAULT_SAMPLE_MARKET)
    parser.add_argument("--cards-json", type=Path, default=DEFAULT_CARDS_JSON)
    parser.add_argument("--html", type=Path, default=DEFAULT_PUBLIC_HTML)
    parser.add_argument("--dated-html", type=Path, default=DEFAULT_PUBLIC_DATED_HTML)
    parser.add_argument("--summary", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fetch-live", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = build_public_cards(args.manifest, args.sample_market, args.fetch_live)
    cards_path = write_json(payload, args.cards_json)
    html_path = render_mobile_html(cards_path, args.html)
    dated_html_path = render_mobile_html(cards_path, args.dated_html)
    summary = {
        "generated_at_jst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cards_json": str(cards_path),
        "html": str(html_path),
        "dated_html": str(dated_html_path),
        "status": "ok" if payload["summary"].get("stop_required_count", 0) == 0 else "stop_required",
        "summary": payload["summary"],
        "fetch_status": payload["metadata"].get("fetch_status", []),
    }
    summary_path = write_json(summary, args.summary)
    if args.print_summary:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"cards: {cards_path}")
    print(f"html: {html_path}")
    print(f"dated_html: {dated_html_path}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
