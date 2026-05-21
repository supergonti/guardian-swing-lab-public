from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from tools.public_ui import scan_public_html


class PublicHtmlScanTest(unittest.TestCase):
    def test_scan_passes_clean_html(self) -> None:
        with tempfile.TemporaryDirectory(dir=scan_public_html.ROOT / "reports" / "github_pages") as tmp:
            path = Path(tmp) / "index.html"
            path.write_text(
                '<html><head><meta name="robots" content="noindex,nofollow"></head><body>公開情報</body></html>',
                encoding="utf-8",
            )
            self.assertEqual([], scan_public_html.scan_html(path))

    def test_scan_rejects_local_link(self) -> None:
        with tempfile.TemporaryDirectory(dir=scan_public_html.ROOT / "reports" / "github_pages") as tmp:
            path = Path(tmp) / "index.html"
            path.write_text(
                '<html><head><meta name="robots" content="noindex,nofollow"></head><body>http://127.0.0.1:8787/</body></html>',
                encoding="utf-8",
            )
            self.assertIn(r"127\.0\.0\.1", scan_public_html.scan_html(path))


if __name__ == "__main__":
    unittest.main()
