# Guardian Swing Lab Public

楽天証券で購入可能と公開情報で確認した商品だけを対象に、公開価格データからSwing Lab提案カードを生成し、GitHub Pagesでスマホ確認するための公開用repositoryです。

## 役割

- 公開情報ベースの提案カードを表示します。
- 自動発注は行いません。
- 楽天証券へのログイン、ログイン後ページのスクレイピング、口座操作は行いません。
- 実際の売買判断と発注は人間が楽天証券で行います。

## 公開しないもの

- 個人情報
- 口座情報
- 実際の保有内容
- 実際の売買記録
- A1/A1.5/A2のローカルGuardianデータ
- private vault
- ローカルData Editorリンク

## 更新

`.github/workflows/deploy_public_mobile.yml` が毎日 02:00 JST 相当に公開データ取得とHTML生成を行い、GitHub Pages artifactとして公開します。

手動実行:

```powershell
python -B tools\swing_lab_public\build_public_swing_lab.py --fetch-live --print-summary
```

公開HTMLチェック:

```powershell
python -B tools\public_ui\scan_public_html.py reports\github_pages\index.html
```
