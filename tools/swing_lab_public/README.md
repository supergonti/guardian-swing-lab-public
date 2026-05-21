# Swing Lab Public Pipeline

GitHub Actions + GitHub Pages向けに、公開情報だけでSwing Lab提案カードを生成するパイプラインです。

## 実行例

サンプルデータで生成:

```powershell
python -B tools\swing_lab_public\build_public_swing_lab.py --print-summary
```

公開Web取得を試す:

```powershell
python -B tools\swing_lab_public\build_public_swing_lab.py --fetch-live --print-summary
```

`--fetch-live` はYahoo Finance chart APIを優先し、取得できない場合はStooq、最後に手動CSVサンプルへfallbackします。

## 安全境界

- private vaultは読みません。
- A1/A1.5/A2は読みません。
- 保有数量、売買記録、資産集計は公開HTMLに入れません。
- 楽天証券ログイン、自動発注、ログイン後ページのスクレイピングはしません。
