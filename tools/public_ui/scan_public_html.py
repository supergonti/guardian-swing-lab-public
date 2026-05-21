"""Scan a public Swing Lab HTML file before GitHub Pages deployment."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HTML = ROOT / "reports" / "github_pages" / "index.html"

FORBIDDEN_PATTERNS = [
    r"guardian_operational_cockpit",
    r"127\.0\.0\.1",
    r"localhost",
    r"prefill_swing_lab_trade",
    r"private_vault",
    r"Data Editor",
    r"A1\.5",
    r"A1月次",
    r"A2資産",
    r"資産集計",
    r"保有数量",
    r"売買記録",
    r"口座番号",
    r"ログインID",
    r"パスワード",
    r"password",
    r"secret",
    r"token",
    r"api[_-]?key",
]


def ensure_within(path: Path, allowed_root: Path) -> Path:
    resolved = path.resolve()
    root = allowed_root.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"path is outside allowed root: {resolved}")
    return resolved


def scan_html(path: Path) -> list[str]:
    safe = ensure_within(path, ROOT)
    text = safe.read_text(encoding="utf-8")
    findings: list[str] = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            findings.append(pattern)
    if '<meta name="robots" content="noindex,nofollow">' not in text:
        findings.append("missing noindex,nofollow meta tag")
    return findings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", nargs="?", type=Path, default=DEFAULT_HTML)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    findings = scan_html(args.html)
    if findings:
        print("public HTML scan failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"public HTML scan OK: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
