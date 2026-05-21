# Public UI Tools

GitHubなどへアップロードできる、個人情報を含まない静的HTMLを作るための補助ツールです。

## Swing Lab スマホ確認版

```powershell
python -B tools\public_ui\render_swing_lab_mobile_public.py
```

出力:

```text
reports\github_pages\guardian_swing_lab_mobile_public_20260521.html
```

## 安全境界

- Guardian Swing Lab提案カードの公開確認情報だけを表示します。
- 個人口座、保有数量、売買記録、資産集計、ローカルData Editorリンクは含めません。
- 自動ログイン、自動発注、外部アップロードは行いません。
