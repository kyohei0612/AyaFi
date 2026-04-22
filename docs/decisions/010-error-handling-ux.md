# ADR-010: エラーハンドリング UX

- **日付**: 2026-04-22
- **ステータス**: 提案中 (承認待ち)
- **決定者**: kyohei
- **関連**: [ADR-001](001-initial-architecture.md), [ADR-003](003-ipc-protocol.md), [ADR-008](008-logging-strategy.md)

---

## Context (問題)

ADR-001 で sidecar の自動再試行 (tenacity 3 回) は定めたが、**画面上でどう見えるか**が未定。
妻 (非エンジニア) は赤いエラーダイアログが出ただけでパニックになる可能性がある。

エラーには大きく 3 種類ある:
- **Transient** (一時的): レート制限、短時間の API ダウン、再試行で直る
- **Permanent** (恒久的): API キー不正、ネット切断長時間、再試行しても直らない
- **User-fault** (ユーザー起因): 画像が大きすぎ、文字数超過、設定ミス

それぞれの見せ方を統一し、**妻がパニックにならない UX ルール**を確定する。
Stage 3 (SNS 実投稿) + Stage 5 (永続化 + 履歴) 実装時に使う。

## Decision (結論)

### エラー重要度と表示方法 3 段階

| 重要度 | 表示方法 | 例 |
|---|---|---|
| **info** | ステータスバー (画面下、小) に薄色で一瞬 | 「再接続中…」「下書き保存しました」 |
| **warning** | トースト (画面右下、黄色、4-6 秒で消える) | 「Threads の文字数が 500 に近い」「rate limit まで 20 秒待機」 |
| **error** | モーダル (中央、赤、明示閉じ操作で消える) + ログフォルダ導線 | 「sidecar 停止」「API キー無効」「ネット切断」 |

### エラー種類別マトリクス

| 種類 | 再試行 | 表示 | ユーザー行動提示 |
|---|---|---|---|
| Transient (Sidecar 1-3 回目クラッシュ) | 自動 (tenacity) | ステータスバー info「再接続中…」 | なし (ユーザー継続操作可能) |
| Transient (Sidecar 4 回目失敗) | なし (閾値到達) | モーダル error「sidecar が応答しません」 | [再試行] [ログ送付] [閉じる] |
| Transient (API レート制限) | 自動バックオフ | トースト warning「◯秒後に再試行」 | なし (表示のみ) |
| Permanent (API キー無効) | なし | モーダル error「◯◯の API キーが無効です」 | [設定を開く] [ログ] [閉じる] |
| Permanent (ネット切断 30 秒以上) | なし | モーダル error「ネットワークに接続できません」 | [再接続] [閉じる] |
| Permanent (LLM 無料枠超過) | なし | モーダル error + reset 時刻表示 | [閉じる] (明日朝再開) |
| User-fault (画像サイズ超過) | なし | インライン (入力欄下に赤字) | [画像を選び直す] |
| User-fault (文字数超過 warning) | なし | インライン (文字数カウンタが赤) | なし (ソフト警告) |

### Sidecar ライフサイクル UI (最重要)

ADR-001 の再試行戦略を視覚化:

```
[Tauri 起動]
  ↓
[Python sidecar spawn]
  ├─ 成功 → ステータスバー「接続済」(緑点)
  │        通常操作可能
  │
  └─ 失敗 1 回目 → tenacity 待機 1 秒
                 → ステータスバー info「再接続中… (1/3)」
                 ↓
     失敗 2 回目 → tenacity 待機 2 秒
                 → ステータスバー info「再接続中… (2/3)」
                 ↓
     失敗 3 回目 → tenacity 待機 4 秒
                 → ステータスバー info「再接続中… (3/3)」
                 ↓
     失敗 4 回目 → **モーダル error** 表示
                  「aya-afi の内部処理が応答しません」
                  ボタン: [再試行] [ログフォルダを開く] [閉じる]
                  (妻が「閉じる」後もアプリは動く = 下書き保存はできる状態)
```

### 「緊急脱出口」

メニューバー or 設定画面に常に**「sidecar を再起動」**コマンドを配置。
トラブル時に妻が自分で押せる。UI 凍結しないため、sidecar とは別スレッドで動く。

### エラーメッセージの言葉遣い

- **NG**: 「Error: 500 Internal Server Error」「Exception: ConnectionRefused」
- **OK**: 「Threads への投稿に失敗しました。ネットが不安定かもしれません」
- ルール:
  - 技術用語 (Exception / Traceback / HTTP 500 等) を見せない
  - 原因仮説を 1 つ、妻の行動を 1 つ、具体的に
  - 「何が起きたか」「なぜか」「どうすれば直るか」の 3 要素

### エラーメッセージ雛形 (i18n 省略、日本語固定)

```typescript
// ui/src/errors/messages.ts
export const ERROR_MESSAGES: Record<string, ErrorDisplay> = {
  "sidecar.crashed": {
    severity: "error",
    title: "内部処理が応答しません",
    body: "aya-afi の裏で動いている処理が止まってしまいました。"
        + "ほとんどの場合、もう一度押せば動きます。",
    actions: ["retry", "open_logs", "close"],
  },
  "llm.quota_exceeded": {
    severity: "error",
    title: "今日の文章生成の上限に達しました",
    body: "Gemini の無料枠は 1 日 1500 回までです。"
        + "{reset_time} にリセットされます。",
    actions: ["close"],
  },
  "sns.rate_limited": {
    severity: "warning",
    title: "少し待ってから再試行します",
    body: "{sns} のレート制限です。{retry_in_sec} 秒後に自動で再送信します。",
    actions: [],
  },
  // ... 全 25-30 パターン想定
};
```

### ログフォルダ導線 (ADR-008 連動)

モーダル error には**必ず**「ログフォルダを開く」ボタンを置く。
妻が kyohei さんにログを送るフローを UX レベルで支援:

1. モーダル上の [ログフォルダを開く] を押す
2. エクスプローラが `%APPDATA%\aya-afi\logs\` を開く
3. 妻が `app.log` + `tauri.log` を選択して LINE or メール添付
4. kyohei さんが原因解析

### ボタン disable / lock (二重投稿防止 = プロジェクト追加ルール 19)

- 「投稿」ボタン: 押下直後に disable、sidecar からレスポンス or timeout まで解除しない
- 投稿中は別商品の投稿画面に移動しても現在の投稿が完了するまで他の「投稿」は受け付けない (キュー管理)
- **例外**: 「sidecar 再起動」だけはいつでも押せる (緊急脱出口)

---

## Alternatives 検討

### 案 A (採用): 3 段階重要度 + エラーマトリクス + 雛形集中管理
- ✅ 一貫性、妻の学習コスト低い
- ✅ 新しいエラー追加時に雛形に 1 行足すだけ
- ⚠ 雛形カバレッジが不足すると中途半端なメッセージが出る → CI で全エラーコード網羅チェック

### 案 B: 毎回エラーメッセージをベタ書き
- ❌ 一貫性なし、妻が混乱
- ❌ 同じエラーでも文言が違って学習できない
- → 却下

### 案 C: 全エラーをモーダルで統一
- ❌ 情報過多、毎回「閉じる」が必要、UX 劣悪
- → 却下

### 案 D: 全エラーをトーストで統一
- ❌ 重要エラーが見逃される (トーストは数秒で消える)
- → 却下

---

## Failure Modes + 対処

| 失敗モード | 影響 | 対処 |
|---|---|---|
| 未登録エラーコード発生 | ユーザーに「error_unknown」が出る | fallback メッセージ「想定外のエラーです、ログを確認してください」+ ログフォルダ導線 + CI でカバレッジテスト |
| モーダル連続表示で妻が全部閉じる | エラー情報失失 | モーダルは 3 秒以内の連続発生 2 件以降は statusbar に集約 (Sentry 風) |
| ステータスバー info が気付かれない | 再接続失敗に気付かない | ステータスバーの色変化 (緑 → 黄) で視覚訴求、4 回目モーダル昇格で必ず気付く |
| ボタン disable が解除されない | 永続操作不能 | timeout (30 秒) で強制解除 + 「応答なし」エラー表示 |
| モーダル [再試行] 連打 | API スパム | 連打抑制 (前回押下から 2 秒以内は無視) + 内部で idempotency_key 維持 |

---

## ロールバック手順

1. 3 段階重要度が細かすぎる → info を廃止、warning/error 2 段階に簡略
2. モーダルが頻出しすぎる → 昇格閾値を上げる (4 回 → 6 回)
3. エラー雛形の保守コストが高い → 重要 10 パターンだけ個別対応、残りは fallback 統一

---

## 計測 (成功判定)

### Stage 3 DoD
- [ ] 主要エラー 10 パターンが雛形に定義済
- [ ] 各重要度 (info/warning/error) の表示コンポーネントが pytest / vitest でカバー
- [ ] sidecar 強制 kill → 4 回目でモーダル出現のシナリオテスト
- [ ] モーダルから [ログフォルダを開く] → エクスプローラ起動

### 運用後 (v0.1 リリース 1 ヶ月)
- 妻からの「よく分からないエラーが出た」報告件数: 許容範囲判定
- ログフォルダ導線の利用率: 5% 以上 (= エラー発生時にきちんと妻が送ってくれる)
- 「sidecar 再起動」緊急ボタンの押下回数: 1 回/月 以下 (= 自動再試行で十分)

---

## 影響範囲

- **ADR-001 (sidecar 再試行)**: 実装の UI 側を本 ADR で規定
- **ADR-003 (IPC)**: ErrorInfo の type 値は本 ADR の ERROR_MESSAGES キーと整合させる
- **ADR-008 (ロギング)**: 全エラーは構造化ログに残す (後で集計できるよう)
- **ADR-005 (投稿履歴)**: `post_targets.last_error_type` は本 ADR の type 体系を使用
- Stage 3 実装時に `ui/src/errors/` モジュールを新設

---

## 実装メモ (Stage 3 実装時に参照)

```typescript
// ui/src/errors/ErrorBoundary.tsx
export function useErrorHandler() {
  return (error: AppError) => {
    const display = ERROR_MESSAGES[error.type] ?? FALLBACK;
    switch (display.severity) {
      case "info":    statusBar.show(display.body); break;
      case "warning": toast.warning(display.title, display.body); break;
      case "error":   modal.show(display); break;
    }
    logError(error);  // send to backend for persistent log
  };
}
```
