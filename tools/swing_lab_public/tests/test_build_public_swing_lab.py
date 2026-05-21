from __future__ import annotations

import json
import tempfile
from pathlib import Path
import unittest

from tools.swing_lab_public import build_public_swing_lab


class PublicSwingLabTest(unittest.TestCase):
    def test_sample_pipeline_filters_to_rakuten_eligible_products(self) -> None:
        payload = build_public_swing_lab.build_public_cards(
            build_public_swing_lab.DEFAULT_MANIFEST,
            build_public_swing_lab.DEFAULT_SAMPLE_MARKET,
            fetch_live=False,
        )
        tickers = {card["ticker_or_code"] for card in payload["cards"]}
        self.assertEqual({"1308", "1655", "2559", "2631"}, tickers)
        labels = [card["subject_label"] for card in payload["cards"]]
        self.assertFalse(any(label.startswith("SPY /") for label in labels))
        self.assertFalse(any(label.startswith("QQQ /") for label in labels))
        self.assertEqual(4, payload["summary"]["card_count"])
        self.assertFalse(payload["metadata"]["private_data"])
        self.assertFalse(payload["metadata"]["broker_connected"])
        self.assertFalse(payload["metadata"]["auto_order"])

    def test_render_mobile_html_excludes_local_links(self) -> None:
        payload = build_public_swing_lab.build_public_cards(
            build_public_swing_lab.DEFAULT_MANIFEST,
            build_public_swing_lab.DEFAULT_SAMPLE_MARKET,
            fetch_live=False,
        )
        with tempfile.TemporaryDirectory(dir=build_public_swing_lab.ROOT / "reports" / "github_pages") as tmp:
            cards_path = Path(tmp) / "cards.json"
            html_path = Path(tmp) / "index.html"
            cards_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            build_public_swing_lab.render_mobile_html(cards_path, html_path)
            html = html_path.read_text(encoding="utf-8")
        forbidden = [
            "guardian_operational_cockpit",
            "127.0.0.1",
            "localhost",
            "prefill_swing_lab_trade",
            "private_vault",
            "Data Editor",
            "A1.5",
            "A1月次",
            "A2資産",
            "保有数量",
            "売買記録",
        ]
        for word in forbidden:
            self.assertNotIn(word, html)


if __name__ == "__main__":
    unittest.main()
