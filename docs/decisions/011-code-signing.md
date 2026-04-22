# ADR-011: 配布署名戦略

- **日付**: 2026-04-22
- **ステータス**: 提案中 (承認待ち)
- **決定者**: kyohei
- **関連**: [ADR-002 X07](002-mvp-scope.md), [ADR-007](001-initial-architecture.md)

---

## Context (問題)

Windows で署名なしの .exe / .msi を配布すると、ダウンロード実行時に
**SmartScreen / Windows Defender の警告**が出る:

> 「WindowsによってPCが保護されました」
> → [詳細情報] → [実行] と 2 クリック必要

妻が毎回この操作に戸惑う可能性がある (初回のみではなく、アップデートごとに出る)。

Stage 6 (exe ビルド) 着手前に署名方針を確定する。

## Decision (結論)

### 段階的導入 (v0.1 → v1.0 へ進化)

| バージョン | 署名 | SmartScreen 挙動 | コスト |
|---|---|---|---|
| **v0.1** | **無署名** | 赤「認識されないアプリ」警告 (2 クリックで実行可) | ¥0 |
| v0.2 | **自己署名証明書** | 「発行元: kyohei (self-signed)」警告 (信頼しづらいが認識される) | ¥0 |
| v0.3 以降 | **OV code signing cert** (DigiCert / SSL.com 等) | 初回は警告、使用実績積むと警告消失 | ¥6,000-15,000/年 |
| v1.0 以降 (任意) | EV code signing cert (USB トークン必須) | **即時信頼**、警告一切なし | ¥30,000-60,000/年 |

### v0.1 確定方針

- **署名なしで出す**
- README に手順を明記 + スクリーンショット添付:
  1. `aya-afi-setup-0.1.0.exe` をダウンロード
  2. ダブルクリック
  3. 「Windows によって PC が保護されました」が出たら **[詳細情報]** をクリック
  4. **[実行]** をクリック
  5. インストール完了
- 妻 PC にインストール済になれば 2 回目以降は警告なし
- 更新時は手動上書き or アンインストール → 再インストール (v0.1 範囲内)

### v0.2 で導入予定: 自己署名証明書

```powershell
# 証明書生成 (CI で 1 回、または開発 PC で)
New-SelfSignedCertificate `
  -Subject "CN=kyohei, O=aya-afi, C=JP" `
  -Type CodeSigningCert `
  -KeyExportPolicy Exportable `
  -KeyUsage DigitalSignature `
  -KeyLength 2048 `
  -HashAlgorithm SHA256 `
  -CertStoreLocation Cert:\CurrentUser\My `
  -NotAfter (Get-Date).AddYears(5)

# signtool.exe (Windows SDK 同梱) で署名
signtool sign /f cert.pfx /p <password> /t http://timestamp.digicert.com /fd SHA256 aya-afi.exe
```

- メリット: 警告文言に「発行元: kyohei」が出る → 信頼感増 (少しだけ)
- デメリット: SmartScreen 的には「不明な発行元」のまま扱われる (実質効果薄)
- 妻 PC に証明書をインポートしておけば警告消失 (手動設定必要)

### v0.3 で検討: OV code signing cert

- **DigiCert / SSL.com / Sectigo / GlobalSign** 等のベンダーから購入
- 価格帯: 年 ¥6,000-15,000 (3 年契約で割引)
- 購入プロセス: 組織情報確認 (個人発行も可) + 本人確認書類 → 発行まで 1-3 週間
- 初回使用時は警告だがダウンロード実績 (Reputation) 積むと警告消失
- 「おすすめ」される頃は年 100 ダウンロード程度必要 → 個人利用なら永久に警告消えない可能性

### 検討却下: EV code signing cert

- 価格帯: 年 ¥30,000-60,000 (USB ハードウェアトークン付き)
- メリット: SmartScreen **即信頼** (Reputation 不要)
- デメリット:
  - 個人では取得困難な場合あり (組織名義推奨)
  - USB トークンを紛失すると再発行に数万円
  - CI での自動署名が難しい (トークンが物理デバイス)
- **個人開発 + 妻 PC 1 台配布では過剰**。永続却下

---

## Alternatives 検討

### 案 A (採用): 段階的導入 (無署名 → 自己署名 → OV)
- ✅ v0.1 で余計なコストゼロ、まず動くものを出せる
- ✅ 実利用実績見ながら段階的に投資判断
- ⚠ 妻が警告操作に慣れる必要あり (初回のみ)

### 案 B: 最初から OV cert 購入
- ✅ 警告ゼロの体験
- ❌ v0.1 出す前に ¥6,000+ 投資、成果未確定の段階で浪費リスク
- → 却下

### 案 C: MSI でなく Portable (zip) 配布
- ✅ インストーラ不要、SmartScreen 警告回避
- ❌ 初回展開時に妻が Extract 操作必要、アップデート時に再展開必要
- ❌ ショートカット / タスクトレイ常駐が面倒
- → 却下

### 案 D: Microsoft Store 経由配布
- ✅ 署名不要 (MS が保証)、アップデート自動
- ❌ 審査あり (コンテンツガイドライン準拠必要)
- ❌ アフィ関連は審査で引っかかる可能性
- ❌ Dev 登録費 $19 (個人)、手間
- → 却下 (将来選択肢として残す)

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| 妻が警告で「実行しない」選択 | アプリ起動不能 | README にスクショ手順、kyohei が最初の 1 回は横で操作案内 |
| 自己署名 cert 期限切れ (v0.2) | インストール拒否 | 5 年期限で発行、ADR-007 CI で期限監視 |
| OV cert の Reputation 積まれない (v0.3) | 警告が消えない | 個人配布では仕方ない、諦めるか v1.0 で EV 検討 |
| 証明書秘密鍵の漏洩 | なりすまし署名される | パスワード保護 + パスワードは 1Password 管理、GitHub Secret 等に平文で置かない |
| タイムスタンプサーバーが応答しない | 署名失敗 | 複数のタイムスタンプ URL を fallback 設定 |

---

## ロールバック手順

1. **v0.2 の自己署名で逆に警告が増える**: v0.1 の無署名に戻す (署名なしは「不明な発行元」1 種類、自己署名は「未検証の発行元」で文言が怖くなる可能性)
2. **OV cert 購入 → Reputation 積まれず意味がない**: v0.2 の自己署名に戻す + cert 費用は「学習代」として諦め
3. **Microsoft Store 申請 → 審査落ち**: 配布経路から除外

---

## 計測 (成功判定)

### v0.1 リリース判定
- [ ] README に SmartScreen 警告の手順明記 + スクショ添付
- [ ] 妻 PC で実際にインストール完了 (1 回目は kyohei 同伴)
- [ ] インストール後の起動は警告なし

### v0.2 リリース判定 (自己署名導入時)
- [ ] CI で署名プロセス自動化 (GitHub Actions + Windows runner)
- [ ] 署名済 .exe のプロパティで発行元が表示される
- [ ] 妻 PC にルート証明書としてインポート → 警告消失確認

### v0.3 検討判定
- **次の指標で決定**:
  - v0.2 運用 3 ヶ月で妻が警告で困った回数 > 3 回 → v0.3 進行
  - 3 回未満 → 自己署名で十分と判断、投資なし

---

## 影響範囲

- **ADR-002 X07**: 本 ADR で具体化
- **ADR-007 (CI/CD)**: 将来の自動署名プロセスを組み込む
- **README.md**: 最初のインストール手順セクションを追加 (Stage 6 までに)
- 現時点の Tauri `tauri.conf.json`: `bundle.active: false` (Stage 0)、Stage 6 で有効化

---

## 参考リソース

- [Microsoft: Code signing](https://learn.microsoft.com/en-us/windows/win32/seccrypto/cryptography-tools#code-signing-tools)
- [Tauri: Windows code signing](https://v2.tauri.app/distribute/sign/windows/)
- [DigiCert OV code signing](https://www.digicert.com/signing/code-signing-certificates)
