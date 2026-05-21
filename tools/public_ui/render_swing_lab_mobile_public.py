"""Render a GitHub-uploadable mobile Swing Lab proposal view.

The output is a static public-check HTML. It intentionally excludes Guardian
operational cockpit data, local Data Editor links, private holdings, execution
records, and any broker login/order function.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from html import escape
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "mock_mvp" / "reports" / "swing_lab_public_web_etf_proposals_20260521_cards.json"
DEFAULT_OUTPUT = ROOT / "reports" / "github_pages" / "guardian_swing_lab_mobile_public_20260521.html"

ACTION_CLASS = {
    "buy_proposal": "buy",
    "sell_proposal": "sell",
    "reduce_proposal": "reduce",
    "exit_proposal": "exit",
    "no_trade": "skip",
}
ACTION_LABEL = {
    "buy_proposal": "買い提案",
    "sell_proposal": "売り提案",
    "reduce_proposal": "縮小提案",
    "exit_proposal": "撤退提案",
    "no_trade": "見送り",
}
RISK_LABEL = {
    "middle_risk": "中リスク",
    "high_risk": "高リスク",
    "experimental": "実験枠",
}
INSTRUMENT_LABEL = {
    "cash_equity": "現物株",
    "etf": "ETF",
    "leveraged_etf": "レバレッジETF",
    "margin_short": "信用・空売り",
    "option": "オプション",
    "pair_trade": "ペアトレード",
}
REGIME_LABEL = {
    "trend": "トレンド",
    "range": "レンジ",
    "neutral": "中立",
    "high_vol_stress": "高ボラ警戒",
}
WARNING_LABEL = {
    "公開Web情報であり、個人口座・税務・為替条件は未反映です": "公開情報のみのため、実行条件は別途確認してください",
    "human approval is not approved yet": "人間確認が未完了です",
    "OOS test is not confirmed": "アウト・オブ・サンプル検証が未確認です",
    "walk-forward test is not confirmed": "ウォークフォワード検証が未確認です",
    "Gate 3+ requires high-volatility and gap-risk review": "高ボラティリティと週明けギャップの確認が必要です",
    "Gate 4+ requires broker rule confirmation": "証券会社ルール確認が必要です",
    "Gate 4+ requires margin confirmation": "証拠金条件の確認が必要です",
    "Gate 4+ requires forced liquidation risk review": "強制決済リスクの確認が必要です",
    "Gate 5 requires defined maximum loss confirmation": "最大損失の明確な確認が必要です",
    "backtest sample size is small": "検証サンプル数が少ないため注意してください",
    "backtest period start is not documented": "検証開始日が未記録です",
    "backtest period end is not documented": "検証終了日が未記録です",
    "benchmark or baseline is not documented": "比較基準が未記録です",
    "lookahead bias check is not confirmed": "未来情報混入チェックが未確認です",
    "survivorship bias check is not confirmed": "生存者バイアス確認が未確認です",
    "backtest data source is not documented": "検証データソースが未記録です",
    "sell-side proposal requires local holding confirmation before execution": "売り側の実行前にローカルGuardianで保有確認が必要です",
    "sell-side max loss requires local holding confirmation": "売り側の損失上限はローカルGuardianで保有状況を確認してから確定します",
    "sell-side ownership confirmation is not enforced in this run": "売り側の保有確認はこの公開画面では強制していません",
    "buy-side proposal may be an add-on; confirm current holding locally": "買い増しになる可能性があるため、保有状況はローカルで確認してください",
    "ownership confirmation required for sell-side proposal": "売り側提案には保有確認が必要です",
    "sell-side proposal requires a confirmed positive holding": "売り側提案には保有中である確認が必要です",
    "holding verification timestamp is not documented": "保有確認時刻が未記録です",
}


def ensure_within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    allowed = root.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise ValueError(f"path is outside allowed root: {resolved}")
    return resolved


def load_cards(path: Path) -> dict[str, Any]:
    safe_path = ensure_within(path, ROOT)
    with safe_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("cards JSON must be an object")
    if not isinstance(data.get("cards"), list):
        raise ValueError("cards JSON must contain cards list")
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("cards JSON must contain metadata object")
    if metadata.get("private_data") is not False:
        raise ValueError("public mobile UI requires metadata.private_data=false")
    if metadata.get("broker_connected") is not False:
        raise ValueError("public mobile UI requires metadata.broker_connected=false")
    if metadata.get("auto_order") is not False:
        raise ValueError("public mobile UI requires metadata.auto_order=false")
    return data


def money(value: Any, currency: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return f"未指定 {currency}"
    return f"{number:,.2f} {currency}"


def label(mapping: dict[str, str], value: Any) -> str:
    text = str(value or "")
    return mapping.get(text, text or "未指定")


def render_list(items: list[Any]) -> str:
    if not items:
        return '<p class="muted">なし</p>'
    rows = []
    for item in items:
        text = WARNING_LABEL.get(str(item), str(item))
        rows.append(f"<li>{escape(text)}</li>")
    return "<ul>" + "".join(rows) + "</ul>"


def render_sources(sources: list[Any]) -> str:
    if not sources:
        return '<p class="muted">公開参照元なし</p>'
    rows = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", "")).strip()
        source_label = str(source.get("label", "参照元")).strip()
        if not url.startswith(("https://", "http://")):
            rows.append(f"<li>{escape(source_label)}</li>")
        else:
            rows.append(
                f'<li><a href="{escape(url)}" rel="noopener noreferrer" target="_blank">{escape(source_label)}</a></li>'
            )
    return "<ul>" + "".join(rows) + "</ul>"


def render_card(card: dict[str, Any]) -> str:
    action = str(card.get("action", ""))
    action_class = ACTION_CLASS.get(action, "skip")
    action_text = str(card.get("action_label") or ACTION_LABEL.get(action, action or "未指定"))
    currency = str(card.get("currency", "JPY"))
    regime = card.get("regime") if isinstance(card.get("regime"), dict) else {}
    regime_text = label(REGIME_LABEL, regime.get("label"))
    confidence = regime.get("confidence")
    confidence_text = f" / 確信度 {float(confidence):.2f}" if isinstance(confidence, (int, float)) else ""
    signals = []
    for item in card.get("signal_basis", []):
        signals.append(str(item).replace("momentum:", "モメンタム:").replace("mean_reversion:", "平均回帰:").replace("regime:", "レジーム:").replace("risk:", "リスク:"))

    backtest = card.get("backtest_status") if isinstance(card.get("backtest_status"), dict) else {}
    backtest_summary = [
        f"シグナル遅延: {escape(str(backtest.get('signal_lag_periods', '未指定')))}期",
        f"取引コスト: {'含む' if backtest.get('transaction_cost_included') else '未確認'}",
        f"スリッページ: {'含む' if backtest.get('slippage_included') else '未確認'}",
        f"最大DD: {escape(str(backtest.get('max_drawdown', '未指定')))}",
        f"OOS: {'確認済み' if backtest.get('oos_tested') else '未確認'}",
        f"WF: {'確認済み' if backtest.get('walk_forward_tested') else '未確認'}",
    ]

    return f"""
<article class="proposal-card {escape(action_class)}">
  <div class="card-topline">
    <div>
      <h2>{escape(str(card.get("subject_label", "未指定")))}</h2>
      <p class="idline">{escape(str(card.get("proposal_id", "ID未指定")))}</p>
    </div>
    <span class="action-badge {escape(action_class)}">{escape(action_text)}</span>
  </div>

  <div class="quick-grid">
    <section><span>リスク</span><b>{escape(label(RISK_LABEL, card.get("risk_class")))}</b></section>
    <section><span>商品</span><b>{escape(label(INSTRUMENT_LABEL, card.get("instrument_type")))}</b></section>
    <section><span>ゲート</span><b>{escape(str(card.get("gate", "未指定")))}</b></section>
    <section><span>参照価格</span><b>{escape(money(card.get("reference_price"), currency))}</b></section>
    <section><span>投入上限</span><b>{escape(money(card.get("max_entry_amount"), currency))}</b></section>
    <section><span>最大許容損失</span><b>{escape(money(card.get("max_loss_amount"), currency))}</b></section>
  </div>

  <section class="statement">
    <span>レジーム</span>
    <p>{escape(regime_text + confidence_text)}</p>
  </section>
  <section class="statement">
    <span>根拠シグナル</span>
    {render_list(signals)}
  </section>
  <section class="statement">
    <span>反証条件</span>
    <p>{escape(str(card.get("counter_evidence", "未指定")))}</p>
  </section>
  <section class="statement">
    <span>損切り・撤退条件</span>
    <p>{escape(str(card.get("stop_rule", "未指定")))}</p>
  </section>
  <section class="statement">
    <span>情報要約</span>
    <p>{escape(str(card.get("source_summary", "未指定")))}</p>
  </section>
  <section class="statement">
    <span>データ鮮度</span>
    <p>{escape(str(card.get("data_freshness", "未指定")))}</p>
  </section>
  <section class="statement">
    <span>バックテスト確認</span>
    {render_list(backtest_summary)}
  </section>
  <section class="statement">
    <span>警告</span>
    {render_list([str(item) for item in card.get("warnings", [])])}
  </section>
  <section class="statement">
    <span>公開Web参照元</span>
    {render_sources(card.get("web_sources", []))}
  </section>
</article>
"""


def render_html(data: dict[str, Any], output_name: str) -> str:
    metadata = data.get("metadata", {})
    summary = data.get("summary", {})
    cards = [card for card in data.get("cards", []) if isinstance(card, dict)]
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    action_counts = summary.get("action_counts") if isinstance(summary.get("action_counts"), dict) else {}
    card_html = "\n".join(render_card(card) for card in cards)

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Guardian Swing Lab スマホ確認版 - {escape(output_name)}</title>
<style>
:root {{
  --bg: #f3f5f4;
  --panel: #ffffff;
  --ink: #101417;
  --muted: #637078;
  --line: #d8e0df;
  --green: #11724c;
  --amber: #a76608;
  --red: #b23535;
  --blue: #276b8d;
  --soft: #edf2f0;
}}
* {{ box-sizing: border-box; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Segoe UI", "Yu Gothic UI", Meiryo, sans-serif;
  line-height: 1.65;
  letter-spacing: 0;
}}
a {{ color: #075db3; overflow-wrap: anywhere; }}
header {{
  padding: 18px 16px 14px;
  background: #ffffff;
  border-bottom: 1px solid var(--line);
}}
h1 {{ margin: 0; font-size: 22px; line-height: 1.25; }}
h2 {{ margin: 0; font-size: 20px; line-height: 1.32; }}
p {{ margin: 0; }}
.file-name {{
  display: inline-flex;
  margin-top: 8px;
  padding: 4px 8px;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--muted);
  background: #fbfcfc;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
}}
.meta {{
  margin-top: 8px;
  color: var(--muted);
  font-size: 12px;
}}
.guardrails {{
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  margin-top: 14px;
}}
.guardrails span {{
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #f7faf9;
  font-size: 13px;
  font-weight: 800;
}}
main {{ padding: 14px; max-width: 980px; margin: 0 auto; }}
.summary {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}}
.metric {{
  min-height: 78px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}}
.metric span {{ display: block; color: var(--muted); font-size: 12px; }}
.metric b {{ display: block; margin-top: 3px; font-size: 24px; line-height: 1.2; }}
.notice {{
  padding: 13px;
  margin-bottom: 12px;
  border: 1px solid #d9c58d;
  border-radius: 8px;
  background: #fff8e6;
  color: #563d05;
  font-size: 13px;
}}
.proposal-list {{ display: grid; gap: 14px; }}
.proposal-card {{
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--panel);
  overflow: hidden;
}}
.proposal-card.buy {{ border-top: 5px solid var(--green); }}
.proposal-card.sell, .proposal-card.reduce {{ border-top: 5px solid var(--amber); }}
.proposal-card.exit {{ border-top: 5px solid var(--red); }}
.proposal-card.skip {{ border-top: 5px solid var(--muted); }}
.card-topline {{
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 10px;
  padding: 14px;
  border-bottom: 1px solid var(--line);
}}
.idline {{ margin-top: 4px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }}
.action-badge {{
  display: inline-flex;
  justify-content: center;
  align-items: center;
  width: fit-content;
  min-height: 34px;
  padding: 7px 12px;
  border-radius: 999px;
  color: #fff;
  font-size: 14px;
  font-weight: 900;
}}
.action-badge.buy {{ background: var(--green); }}
.action-badge.sell, .action-badge.reduce {{ background: var(--amber); }}
.action-badge.exit {{ background: var(--red); }}
.action-badge.skip {{ background: var(--muted); }}
.quick-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 12px;
  background: #fbfcfc;
  border-bottom: 1px solid var(--line);
}}
.quick-grid section {{
  min-height: 66px;
  padding: 9px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: #ffffff;
}}
.quick-grid span, .statement span {{
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 4px;
}}
.quick-grid b {{ font-size: 15px; overflow-wrap: anywhere; }}
.statement {{
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
}}
.statement:last-child {{ border-bottom: 0; }}
.statement p, .statement li {{ font-size: 15px; font-weight: 700; }}
.statement ul {{ margin: 0; padding-left: 20px; }}
.muted {{ color: var(--muted); font-weight: 500; }}
footer {{
  padding: 18px 14px 28px;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}}
@media (min-width: 720px) {{
  header {{ padding: 22px 24px 16px; }}
  h1 {{ font-size: 28px; }}
  main {{ padding: 18px 22px; }}
  .guardrails {{ grid-template-columns: repeat(4, max-content); }}
  .summary {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
  .card-topline {{ grid-template-columns: minmax(0, 1fr) max-content; align-items: start; }}
  .quick-grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
}}
</style>
</head>
<body>
<header>
  <h1>Guardian Swing Lab スマホ確認版</h1>
  <div class="file-name">{escape(output_name)}</div>
  <p class="meta">生成: {escape(generated)} / データ: {escape(str(metadata.get("as_of", "未指定")))} / 入力: {escape(str(metadata.get("scenario_id", "未指定")))}</p>
  <div class="guardrails" aria-label="安全条件">
    <span>個人情報なし</span>
    <span>保有情報なし</span>
    <span>自動発注なし</span>
    <span>公開確認用</span>
  </div>
</header>
<main>
  <section class="summary" aria-label="概要">
    <div class="metric"><span>提案カード</span><b>{escape(str(summary.get("card_count", len(cards))))}</b></div>
    <div class="metric"><span>買い提案</span><b>{escape(str(action_counts.get("buy_proposal", 0)))}</b></div>
    <div class="metric"><span>売り提案</span><b>{escape(str(action_counts.get("sell_proposal", 0)))}</b></div>
    <div class="metric"><span>停止必須</span><b>{escape(str(summary.get("stop_required_count", 0)))}</b></div>
  </section>
  <section class="notice">
    このページはスマホ確認用の静的HTMLです。公開情報ベースの提案カードだけを表示します。実行前には楽天証券画面とローカルGuardianで人間確認してください。
  </section>
  <section class="proposal-list" aria-label="提案カード">
    {card_html}
  </section>
</main>
<footer>
  Guardian Swing Lab public mobile view. Static HTML only.
</footer>
</body>
</html>
"""


def write_html(html: str, output_path: Path) -> Path:
    safe_output = ensure_within(output_path, ROOT)
    safe_output.parent.mkdir(parents=True, exist_ok=True)
    safe_output.write_text(html, encoding="utf-8")
    return safe_output


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    data = load_cards(args.input)
    html = render_html(data, args.output.name)
    output_path = write_html(html, args.output)
    print(f"rendered: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
