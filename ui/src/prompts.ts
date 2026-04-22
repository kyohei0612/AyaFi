// プロンプトテンプレート (UI 側で組み立て、generate_post に送る)
// 本質ルールは config/sns/threads.md と config/prompts/soul_topics.md を参照。
// Stage 4 (ADR-009 SNS エンジン) で Python 側に移植予定。

export type PostMode = "preparation" | "affiliate";

// ---------------------------------------------------------------------------
// NG 条件 (禁止事項) — ayaさんがチェックした項目は system prompt に追記される。
// 一般的なコンプライアンス (景表法 / 薬機法) + 文体の好み + アフィ注意点。
// localStorage で永続化 (キー: "aya-afi.ngFlags")。
// ---------------------------------------------------------------------------

export type NGFlagId =
  | "no_emoji"
  | "limit_exclamation"
  | "tone_formal"
  | "tone_casual"
  | "one_tag_max"
  | "no_cliche"
  | "no_katakana_slang"
  | "no_decorative_marks"
  | "no_parenthetical_emote"
  | "compact_linebreaks";

/**
 * 文章の「見た目」に直接効く NG 集。ayaさんが気に入った「絵文字なし」と同じ
 * 軸。景表法 / 薬機法系の機能的 NG は Stage 4 で Validator 側に自動強制する
 * 方針にしたので、ここでは入れない。
 */
export const NG_OPTIONS: Record<
  NGFlagId,
  { label: string; hint: string; rule: string }
> = {
  no_emoji: {
    label: "絵文字を使わない",
    hint: "😊 💖 ✨ 等すべて",
    rule: "絵文字・顔文字を一切使用しないこと。装飾的な記号 (✨ / 💖 / 🌸 等) も含む。",
  },
  limit_exclamation: {
    label: "感嘆符 (!) 多用禁止",
    hint: "1 投稿 2 個まで",
    rule: "感嘆符 (「!」「！」) は 1 投稿につき合計 2 個まで。落ち着いた文体に。",
  },
  tone_formal: {
    label: "ですます調で統一",
    hint: "きちんとした印象",
    rule: "文末を「です」「ます」調で統一。「〜だよ」「〜ね」「〜じゃん」等のフランク口語を使わない。",
  },
  tone_casual: {
    label: "カジュアル口調で統一",
    hint: "親しみやすい印象",
    rule: "文末をカジュアルに (「〜だよ」「〜かも」「〜だね」)。「です」「ます」等のかしこまった敬語を使わない。",
  },
  one_tag_max: {
    label: "ハッシュタグ 1 個まで",
    hint: "末尾にジャンル 1 つ",
    rule: "ハッシュタグは本文末尾に 1 個まで。ゼロでも可。",
  },
  no_cliche: {
    label: "決まり文句禁止",
    hint: "神アイテム / 買ってよかった / マジで",
    rule: "「神アイテム」「買ってよかった」「マジで」「ガチで」「鬼〜」等、SNS で使い古された定型句を避け、自分の言葉で書くこと。",
  },
  no_katakana_slang: {
    label: "カタカナ若者語禁止",
    hint: "マジ / ガチ / ヤバ",
    rule: "「マジ」「ガチ」「ヤバい」「エグい」「サイコー」等、カタカナ若者語・スラングを使わないこと。",
  },
  no_decorative_marks: {
    label: "装飾記号禁止",
    hint: "★ ♡ → 〜 等の装飾",
    rule: "★ / ♡ / → / 〜♪ 等の装飾記号や全角矢印・波線装飾を使わないこと (必要な句読点のみ使用)。",
  },
  no_parenthetical_emote: {
    label: "括弧書き (笑)(泣) 禁止",
    hint: "感情を文で表現する",
    rule: "「(笑)」「(泣)」「(涙)」「(汗)」等の括弧付き感情表現を使わず、文で感情を描写すること。",
  },
  compact_linebreaks: {
    label: "改行しすぎない",
    hint: "縦長スクロールを避ける",
    rule: "空行を連続させない。段落区切りは空行 1 行まで。縦長に間延びさせず、読みやすくまとめる。",
  },
};

export type SoulTopicId =
  | "regret"
  | "surprise"
  | "small_hack"
  | "fail"
  | "seasonal";

export const SOUL_TOPICS: Record<
  SoulTopicId,
  { label: string; hint: string }
> = {
  regret: {
    label: "後悔",
    hint: "最近買って後悔したもの / やらなくてよかったこと",
  },
  surprise: {
    label: "驚き",
    hint: "意外と知らなかった発見 / 常識が覆った瞬間",
  },
  small_hack: {
    label: "日常の工夫",
    hint: "毎日の時短テク / 続けているルーティン",
  },
  fail: {
    label: "失敗談",
    hint: "笑える / 共感できる失敗、キッチンでの大惨事",
  },
  seasonal: {
    label: "季節もの",
    hint: "今の時期に感じること / やりたいこと",
  },
};

const THREADS_ALGORITHM_RULES = `
【Threads アルゴリズムの鉄則 — 必ず守る】
1. 親ポストに URL を絶対に含めない (アフィリンクは別途リプ側で扱う)
2. ハッシュタグは 1 投稿に 1 つだけ
3. 必ず会話誘発の問いかけで締める (返信 = S 級シグナル)
4. 冒頭 2 行にキーワードを自然に埋め込む
5. 500 字以内
6. 絵文字は 3-5 個目安
7. コピペ調 / 定型文禁止、毎回違う導入
8. 誇大表現 / 実体験の捏造禁止
`.trim();

const PREPARATION_SYSTEM_PROMPT = `
あなたは日本語で Threads 投稿文を書く、30 代主婦「aya」のアシスタントです。
aya は 2 児の母で、時短と効率に興味があり、優しく率直な口調で書きます。

${THREADS_ALGORITHM_RULES}

【準備期間モード (この投稿は商品紹介ではない)】
- 商品名 / ブランド名 / アフィリンクを一切出さない
- 「魂の 5 大お題」のどれか 1 つで書く
- 実体験の感情 (後悔 / 驚き / 工夫 / 失敗 / 季節感) を具体描写
- 「#PR」は付けない
- 文字数 400-500 字
- ハッシュタグはジャンル系を 1 つだけ
`.trim();

const AFFILIATE_SYSTEM_PROMPT = `
あなたは日本語で Threads 投稿文を書く、30 代主婦「aya」のアシスタントです。
aya は 2 児の母で、時短と効率に興味があり、優しく率直な口調で書きます。

${THREADS_ALGORITHM_RULES}

【本投稿モード (商品紹介 + アフィリンク)】
- 商品の良さを具体的に紹介 (ベネフィット先出し、機能羅列は避ける)
- **親ポスト本文には URL を絶対に含めない** (アプリがリプ側に別途配置)
- 「#PR」タグを必ず末尾に含める
- 会話誘発の問いかけで締める
- 文字数 400-500 字
- ハッシュタグは「ジャンル系 1 つ + #PR」の 2 つまで
`.trim();

export function buildSystemPrompt(
  mode: PostMode,
  ngFlagIds: readonly NGFlagId[] = [],
): string {
  const base =
    mode === "preparation" ? PREPARATION_SYSTEM_PROMPT : AFFILIATE_SYSTEM_PROMPT;
  if (ngFlagIds.length === 0) return base;
  const rules = ngFlagIds
    .map((id) => NG_OPTIONS[id]?.rule)
    .filter((r): r is string => Boolean(r))
    .map((r) => `- ${r}`)
    .join("\n");
  if (!rules) return base;
  return (
    base +
    "\n\n【ayaさんが指定した追加の禁止事項 — 必ず守る】\n" +
    rules
  );
}

export function buildPreparationUserPrompt(
  topic: SoulTopicId,
  userInput: string,
): string {
  const t = SOUL_TOPICS[topic];
  return [
    `【お題】 ${t.label} (${t.hint})`,
    "",
    userInput.trim()
      ? `【ayaが書き留めたメモ】\n${userInput.trim()}`
      : "【ayaが書き留めたメモ】(未入力、お題に沿って全体を組み立てる)",
    "",
    "上記お題で Threads 投稿文 1 本を生成してください。" +
      "ayaの実体験の感情を中心に、最後は必ず会話誘発の問いかけで締めてください。" +
      "本文には URL や商品名を含めないこと。",
  ].join("\n");
}

export function buildAffiliateUserPrompt(params: {
  productTitle: string;
  productDescription: string;
  productShop: string | null;
  productPriceYen: number | null;
  productAffiliateUrl: string;
  userInput: string;
}): string {
  const {
    productTitle,
    productDescription,
    productShop,
    productPriceYen,
    productAffiliateUrl,
    userInput,
  } = params;
  const lines: string[] = ["【商品情報】"];
  if (productTitle) lines.push(`商品名: ${productTitle}`);
  if (productPriceYen !== null)
    lines.push(`価格: ¥${productPriceYen.toLocaleString()}`);
  if (productShop) lines.push(`ショップ: ${productShop}`);
  if (productDescription)
    lines.push(`説明 (抜粋): ${productDescription.slice(0, 200)}`);
  lines.push(`アフィリエイト URL: ${productAffiliateUrl}`);
  lines.push("");
  if (userInput.trim()) {
    lines.push("【ayaの補足メモ】");
    lines.push(userInput.trim());
    lines.push("");
  }
  lines.push(
    "上記商品を紹介する Threads 投稿文 1 本を生成してください。" +
      "本文に URL を含めないこと (アフィリンクはアプリが自動でリプ側に配置)。" +
      "#PR タグを必ず含め、会話誘発の問いかけで締めてください。",
  );
  return lines.join("\n");
}

export function suggestModeForDate(d: Date): PostMode {
  // JST 曜日: 0=Sun, 1=Mon, ..., 6=Sat. 月-木 = preparation, 金-日 = affiliate.
  const day = d.getDay();
  if (day >= 1 && day <= 4) return "preparation";
  return "affiliate";
}

export function pickRandomTopic(): SoulTopicId {
  const keys = Object.keys(SOUL_TOPICS) as SoulTopicId[];
  return keys[Math.floor(Math.random() * keys.length)]!;
}
