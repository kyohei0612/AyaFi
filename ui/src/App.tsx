import { useEffect, useMemo, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { open as openFileDialog } from "@tauri-apps/plugin-dialog";

function pathToWebviewSrc(path: string): string {
  return convertFileSrc(path);
}

function basename(path: string): string {
  const m = path.replace(/\\/g, "/").match(/[^/]+$/);
  return m ? m[0] : path;
}

const MAX_IMAGES = 10;
import {
  NGFlagId,
  NG_OPTIONS,
  PostMode,
  SNS_LABELS,
  SOUL_TOPICS,
  SnsKind,
  SoulTopicId,
  buildAffiliateUserPrompt,
  buildPreparationUserPrompt,
  buildSystemPrompt,
  pickRandomTopic,
  suggestModeForDate,
} from "./prompts";

const NG_STORAGE_KEY = "aya-afi.ngFlags";
const PROFILE_STORAGE_KEY = "aya-afi.profile";

const PROFILE_PLACEHOLDER =
  "例:\n" +
  "- 30 代前半、都内在住\n" +
  "- 夫婦 2 人暮らし、子どもなし (将来も予定なし)\n" +
  "- フルタイムで事務職、通勤 1 時間\n" +
  "- 週末は夫と喫茶店めぐり、ミニマリスト志向\n" +
  "- 猫を飼っている (キジトラ、7 歳)";

function loadProfile(): string {
  try {
    return localStorage.getItem(PROFILE_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveProfile(value: string): void {
  try {
    localStorage.setItem(PROFILE_STORAGE_KEY, value);
  } catch {
    // localStorage full — non-fatal
  }
}

function loadNGFlags(): Set<NGFlagId> {
  try {
    const raw = localStorage.getItem(NG_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      const valid = parsed.filter(
        (v): v is NGFlagId =>
          typeof v === "string" && Object.hasOwn(NG_OPTIONS, v),
      );
      return new Set(valid);
    }
  } catch {
    // corrupt state — fall through to empty
  }
  return new Set();
}

function saveNGFlags(flags: Set<NGFlagId>): void {
  try {
    localStorage.setItem(NG_STORAGE_KEY, JSON.stringify([...flags]));
  } catch {
    // localStorage quota / private mode — silently ignore
  }
}

type SidecarResponse<T> = {
  schema_version: number;
  request_id: string;
  ok: boolean;
  data?: T;
  error?: { type: string; message: string; retry_after_sec?: number | null };
};

type PingData = { pong?: boolean; echo?: string };

type ProductData = {
  url: string;
  source: string;
  affiliate_url: string;
  title: string;
  price_yen: number | null;
  description: string;
  image_urls: string[];
  shop_name: string | null;
  category: string | null;
};

type GenerateData = {
  text: string;
  model: string;
  provider: string;
  tokens_in: number;
  tokens_out: number;
  duration_ms: number;
};

type ValidationIssue = {
  severity: "error" | "warning" | "info";
  rule_id: string;
  message: string;
  field?: string | null;
};

type ValidationData = {
  sns: string;
  mode: string;
  char_count: number;
  error_count: number;
  warning_count: number;
  issues: ValidationIssue[];
};

type PublishData = {
  success: boolean;
  sns: string;
  sns_post_id: string | null;
  sns_post_url: string | null;
  reply_post_id: string | null;
  error_type: string | null;
  error_message: string | null;
};

const WEEKDAY_JA = ["日", "月", "火", "水", "木", "金", "土"] as const;

function buildGreeting(now: Date, suggestedMode: PostMode): {
  greeting: string;
  dateLabel: string;
  modeLabel: string;
} {
  const h = now.getHours();
  const greeting =
    h < 5
      ? "おつかれさま、ayaさん"
      : h < 10
        ? "おはようございます、ayaさん"
        : h < 17
          ? "こんにちは、ayaさん"
          : "こんばんは、ayaさん";
  const dateLabel = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 (${WEEKDAY_JA[now.getDay()]})`;
  const modeLabel =
    suggestedMode === "preparation" ? "準備期間モード推奨" : "本投稿モード推奨";
  return { greeting, dateLabel, modeLabel };
}

export default function App(): JSX.Element {
  const now = useMemo(() => new Date(), []);
  const suggestedMode = useMemo(() => suggestModeForDate(now), [now]);
  const hero = useMemo(() => buildGreeting(now, suggestedMode), [now, suggestedMode]);
  const [mode, setMode] = useState<PostMode>(suggestedMode);
  const [sns, setSns] = useState<SnsKind>("threads");
  const charLimit = SNS_LABELS[sns].charLimit;

  // Profile — ayaさんの具体プロフィール (family/age/job/location/lifestyle).
  // Feeds into every generation's system prompt so the LLM stops inventing
  // details like kids, jobs, or hobbies that don't apply.
  // Auto-saved to localStorage on every keystroke; the explicit "保存"
  // button is a UX reassurance (shows a transient confirmation message).
  const [profile, setProfileState] = useState<string>(() => loadProfile());
  const [profileSavedAt, setProfileSavedAt] = useState<string>("");
  const setProfile = (next: string): void => {
    setProfileState(next);
    saveProfile(next);
  };
  const handleProfileSaveClick = (): void => {
    saveProfile(profile);
    setProfileSavedAt("保存しました ✓");
    setTimeout(() => setProfileSavedAt(""), 2500);
  };

  // NG (禁止事項) selections — restored from localStorage on mount.
  const [ngFlags, setNgFlagsState] = useState<Set<NGFlagId>>(() => loadNGFlags());
  const setNgFlags = (updater: (prev: Set<NGFlagId>) => Set<NGFlagId>): void => {
    setNgFlagsState((prev) => {
      const next = updater(prev);
      saveNGFlags(next);
      return next;
    });
  };
  const toggleNg = (id: NGFlagId): void => {
    setNgFlags((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Preparation mode state
  const [soulTopic, setSoulTopic] = useState<SoulTopicId>(() =>
    pickRandomTopic(),
  );
  const [prepMemo, setPrepMemo] = useState<string>("");

  // Affiliate mode state
  const [productUrl, setProductUrl] = useState<string>("");
  const [fetching, setFetching] = useState<boolean>(false);
  const [product, setProduct] = useState<ProductData | null>(null);
  const [affMemo, setAffMemo] = useState<string>("");

  // Images (absolute filesystem paths from the Tauri file dialog). Actual
  // upload to the SNS happens in Stage 3.c.
  const [images, setImages] = useState<string[]>([]);
  const imageThumbs = useMemo(
    () => images.map((path) => ({ path, url: pathToWebviewSrc(path) })),
    [images],
  );

  // Common
  const [generating, setGenerating] = useState<boolean>(false);
  const [generated, setGenerated] = useState<GenerateData | null>(null);
  // Editable version of the generated text. Resets when ``generated`` changes.
  const [editedText, setEditedText] = useState<string>("");
  const [copyStatus, setCopyStatus] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [validation, setValidation] = useState<ValidationData | null>(null);
  const [publishing, setPublishing] = useState<boolean>(false);
  const [publishResult, setPublishResult] = useState<PublishData | null>(null);

  useEffect(() => {
    if (generated) {
      setEditedText(generated.text);
      setCopyStatus("");
      setPublishResult(null);
    }
  }, [generated]);

  // Auto-validate on text change (debounced). Threads + Bluesky supported.
  useEffect(() => {
    if (!editedText.trim()) {
      setValidation(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const resp = await invoke<SidecarResponse<ValidationData>>(
          "validate_content",
          { sns, mode, body: editedText },
        );
        if (resp.ok && resp.data) setValidation(resp.data);
      } catch {
        // Best-effort: a validation failure should not block the UI.
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [editedText, mode, sns]);

  const charCount = useMemo(
    () => [...editedText].length,
    [editedText],
  );
  const overLimit = charCount > charLimit;

  const handleCopy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(editedText);
      setCopyStatus("コピーしました ✓");
      setTimeout(() => setCopyStatus(""), 2500);
    } catch (e) {
      setCopyStatus(`コピー失敗: ${String(e)}`);
    }
  };

  const handleCopyAndOpenNote = async (): Promise<void> => {
    try {
      setError("");
      await navigator.clipboard.writeText(editedText);
      await invoke("open_note_compose");
      setCopyStatus("note を開きました、本文欄で Ctrl+V で貼り付け ✓");
      setTimeout(() => setCopyStatus(""), 5000);
    } catch (e) {
      setError(`note へのコピー失敗: ${String(e)}`);
    }
  };

  const handleResetText = (): void => {
    if (generated) setEditedText(generated.text);
  };

  const handleImagePick = async (): Promise<void> => {
    setError("");
    const remaining = MAX_IMAGES - images.length;
    if (remaining <= 0) return;
    try {
      const picked = await openFileDialog({
        multiple: true,
        directory: false,
        filters: [
          {
            name: "Images",
            extensions: ["jpg", "jpeg", "png", "webp"],
          },
        ],
      });
      if (!picked) return;
      const paths = Array.isArray(picked) ? picked : [picked];
      const next = [...images, ...paths.slice(0, remaining)];
      setImages(next);
    } catch (e) {
      setError(`画像選択エラー: ${String(e)}`);
    }
  };

  const handleImageRemove = (idx: number): void => {
    setImages(images.filter((_, i) => i !== idx));
  };

  const handleImageClear = (): void => {
    setImages([]);
  };

  // Ping (疎通確認)
  const [pong, setPong] = useState<string>("");
  const [sidecarPong, setSidecarPong] = useState<string>("");
  const [pingMessage, setPingMessage] = useState<string>("hello sidecar");

  const handlePing = async (): Promise<void> => {
    try {
      setError("");
      setPong(await invoke<string>("ping"));
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSidecarPing = async (): Promise<void> => {
    try {
      setError("");
      const resp = await invoke<SidecarResponse<PingData>>("sidecar_ping", {
        message: pingMessage,
      });
      if (resp.ok) {
        setSidecarPong(`echo=${resp.data?.echo ?? "(none)"}`);
      } else {
        setError(`sidecar error: ${resp.error?.type}: ${resp.error?.message}`);
      }
    } catch (e) {
      setError(String(e));
    }
  };

  const handleOpenLogs = async (): Promise<void> => {
    try {
      setError("");
      await invoke("open_logs_dir");
    } catch (e) {
      setError(String(e));
    }
  };

  const handleFetchProduct = async (): Promise<void> => {
    try {
      setError("");
      setProduct(null);
      setFetching(true);
      const resp = await invoke<SidecarResponse<ProductData>>("fetch_product", {
        url: productUrl,
      });
      if (resp.ok && resp.data) {
        setProduct(resp.data);
      } else {
        setError(`fetch error: ${resp.error?.type}: ${resp.error?.message}`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setFetching(false);
    }
  };

  const handlePublish = async (): Promise<void> => {
    // Threads affiliate mode: put the URL in a self-reply per ADR-012.
    const wantsReply =
      sns === "threads" && mode === "affiliate" && product !== null;
    const replyBody = wantsReply
      ? `詳細はこちら👇\n${product!.affiliate_url}`
      : undefined;

    // Threads API does not accept direct binary image upload (it requires a
    // publicly reachable URL). We send images only to Bluesky; for Threads the
    // user adds them manually after posting.
    const imagePaths = sns === "bluesky" ? images : [];

    const snsLabel = SNS_LABELS[sns].short;
    const previewLines = [
      `${snsLabel} に投稿します。内容を確認してください。`,
      "",
      editedText,
    ];
    if (replyBody) {
      previewLines.push("", "--- リプライ (アフィ URL) ---", replyBody);
    }
    if (imagePaths.length > 0) {
      previewLines.push("", `画像 ${imagePaths.length} 枚を添付`);
    } else if (sns === "threads" && images.length > 0) {
      previewLines.push(
        "",
        "⚠ Threads API は画像の直接アップロード非対応。投稿後に Threads アプリから追加してください。",
      );
    }
    previewLines.push("", `${charCount} / ${charLimit} 字`);
    const ok = window.confirm(previewLines.join("\n"));
    if (!ok) return;

    try {
      setError("");
      setPublishResult(null);
      setPublishing(true);
      const resp = await invoke<SidecarResponse<PublishData>>("publish_post", {
        sns,
        body: editedText,
        replyBody,
        imagePaths,
      });
      if (resp.ok && resp.data) {
        setPublishResult(resp.data);
      } else {
        setError(
          `publish error: ${resp.error?.type}: ${resp.error?.message}`,
        );
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setPublishing(false);
    }
  };

  const handleGenerate = async (): Promise<void> => {
    try {
      setError("");
      setGenerated(null);

      let systemPrompt = "";
      let userPrompt = "";
      const ngList = [...ngFlags];
      if (mode === "preparation") {
        systemPrompt = buildSystemPrompt(sns, "preparation", ngList, profile);
        userPrompt = buildPreparationUserPrompt(soulTopic, prepMemo, sns);
      } else {
        if (!product) {
          setError("本投稿モードでは、先に商品情報を取得してください。");
          return;
        }
        systemPrompt = buildSystemPrompt(sns, "affiliate", ngList, profile);
        userPrompt = buildAffiliateUserPrompt({
          productTitle: product.title,
          productDescription: product.description,
          productShop: product.shop_name,
          productPriceYen: product.price_yen,
          productAffiliateUrl: product.affiliate_url,
          userInput: affMemo,
          sns,
        });
      }

      setGenerating(true);
      const resp = await invoke<SidecarResponse<GenerateData>>(
        "generate_post",
        { systemPrompt, userPrompt },
      );
      if (resp.ok && resp.data) {
        setGenerated(resp.data);
      } else {
        setError(`generate error: ${resp.error?.type}: ${resp.error?.message}`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  };

  return (
    <main className="container">
      <header className="hero">
        <div className="hero-brand">
          <span className="brand-mark" aria-hidden="true">
            A
          </span>
          <h1>AyaFi</h1>
        </div>
        <p className="hero-subtitle">
          SNS アフィ投稿支援ツール · Threads アルゴリズム対応
        </p>
        <div className="hero-card">
          <p className="hero-greeting">{hero.greeting}。</p>
          <p className="hero-meta">
            {hero.dateLabel}
            <span className="hero-mode-pill">{hero.modeLabel}</span>
          </p>
        </div>
      </header>

      <section className="panel profile-panel">
        <details>
          <summary>
            <span className="ng-title">プロフィール設定</span>
            {profile.trim() ? (
              <span className="ng-badge">入力済み</span>
            ) : (
              <span className="ng-badge-empty">未入力</span>
            )}
            <span className="ng-caret" aria-hidden="true">
              ▾
            </span>
          </summary>
          <p className="ng-hint">
            家族構成・年齢・職業・ライフスタイルなどを書いておくと、LLM
            が的外れな属性 (子ども #育児 等) を混ぜないようになります。
            自動保存 (ブラウザ内)。
          </p>
          <label className="field">
            <textarea
              rows={6}
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              placeholder={PROFILE_PLACEHOLDER}
            />
          </label>
          <div className="row" style={{ marginTop: "0.5rem" }}>
            <button
              type="button"
              className="btn-primary"
              onClick={handleProfileSaveClick}
            >
              💾 保存
            </button>
            {profile.trim() && (
              <button
                type="button"
                onClick={() => {
                  if (window.confirm("プロフィールをクリアしますか？")) {
                    setProfile("");
                  }
                }}
              >
                クリア
              </button>
            )}
            {profileSavedAt && (
              <span className="copy-status">{profileSavedAt}</span>
            )}
          </div>
        </details>
      </section>

      <section className="panel ng-panel">
        <details>
          <summary>
            <span className="ng-title">NG 条件 (禁止事項)</span>
            {ngFlags.size > 0 ? (
              <span className="ng-badge">{ngFlags.size} 項目選択中</span>
            ) : (
              <span className="ng-badge-empty">未選択</span>
            )}
            <span className="ng-caret" aria-hidden="true">
              ▾
            </span>
          </summary>
          <p className="ng-hint">
            チェックした内容は LLM への指示に毎回追加されます。選択は自動保存 (ブラウザ内) されます。
          </p>
          <div className="ng-grid">
            {(Object.keys(NG_OPTIONS) as NGFlagId[]).map((id) => {
              const opt = NG_OPTIONS[id];
              const checked = ngFlags.has(id);
              return (
                <label
                  key={id}
                  className={checked ? "ng-item ng-item-on" : "ng-item"}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleNg(id)}
                  />
                  <span className="ng-item-body">
                    <span className="ng-item-label">{opt.label}</span>
                    <span className="ng-item-hint">{opt.hint}</span>
                  </span>
                </label>
              );
            })}
          </div>
          {ngFlags.size > 0 && (
            <div className="row" style={{ marginTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setNgFlags(() => new Set())}
              >
                すべて解除
              </button>
            </div>
          )}
        </details>
      </section>

      <section className="panel mode-panel">
        <h2>投稿先 SNS</h2>
        <div className="mode-toggle">
          {(Object.keys(SNS_LABELS) as SnsKind[]).map((k) => (
            <button
              key={k}
              type="button"
              className={sns === k ? "mode-active" : "mode-inactive"}
              onClick={() => setSns(k)}
            >
              {SNS_LABELS[k].label}
              <span className="sns-meta">
                {SNS_LABELS[k].charLimit}字 / {SNS_LABELS[k].tagLabel}
              </span>
            </button>
          ))}
        </div>
        <p className="mode-hint">
          {sns === "threads"
            ? "Threads: 親ポスト URL NG、タグ 1 個、会話誘発の質問で締める。リプライに URL を配置。"
            : "Bluesky: URL 本文 OK、タグ 2-4 個必須 (カスタムフィード拾い)、具体スペック入れると刺さる。"}
        </p>
      </section>

      <section className="panel mode-panel">
        <h2>投稿モード</h2>
        <div className="mode-toggle">
          <button
            type="button"
            className={mode === "preparation" ? "mode-active" : "mode-inactive"}
            onClick={() => setMode("preparation")}
          >
            準備期間 (月〜木)
          </button>
          <button
            type="button"
            className={mode === "affiliate" ? "mode-active" : "mode-inactive"}
            onClick={() => setMode("affiliate")}
          >
            本投稿 / アフィ (金〜日)
          </button>
        </div>
        <p className="mode-hint">
          {mode === "preparation"
            ? "信用貯金フェーズ。商品紹介なし、魂の 5 大お題から日常を書きます。"
            : "週末の買い物欲ピーク用。商品 URL 取得 → アフィ文生成。"}
          {" 推奨: "}
          {suggestedMode === mode ? "今日の推奨モードです ✓" : `今日は「${suggestedMode === "preparation" ? "準備期間" : "本投稿"}」が推奨`}
        </p>
      </section>

      {mode === "preparation" ? (
        <section className="panel">
          <h2>魂の 5 大お題</h2>
          <div className="mode-toggle topic-chips">
            {(Object.keys(SOUL_TOPICS) as SoulTopicId[]).map((k) => (
              <button
                key={k}
                type="button"
                className={soulTopic === k ? "mode-active" : "mode-inactive"}
                onClick={() => setSoulTopic(k)}
              >
                {SOUL_TOPICS[k].label}
              </button>
            ))}
            <button
              type="button"
              className="mode-inactive"
              onClick={() => setSoulTopic(pickRandomTopic())}
            >
              ランダム 🎲
            </button>
          </div>
          <p className="mode-hint">{SOUL_TOPICS[soulTopic].hint}</p>
          <label className="field">
            <span>ayaのメモ (具体シーン / 感情 / 失敗など、箇条書きで OK)</span>
            <textarea
              rows={4}
              value={prepMemo}
              onChange={(e) => setPrepMemo(e.target.value)}
              placeholder="例: 3000円で買った折りたたみ傘、結局 2 回使ってお蔵入り..."
            />
          </label>
        </section>
      ) : (
        <section className="panel">
          <h2>商品情報 (楽天 / Amazon)</h2>
          <label className="field">
            <span>商品 URL</span>
            <input
              type="text"
              value={productUrl}
              onChange={(e) => setProductUrl(e.target.value)}
              placeholder="https://item.rakuten.co.jp/... or https://amazon.co.jp/dp/..."
            />
          </label>
          <div className="row">
            <button
              type="button"
              onClick={handleFetchProduct}
              disabled={fetching || !productUrl}
            >
              {fetching ? "取得中…" : "商品情報を取得"}
            </button>
          </div>
          {product && (
            <div className="output">
              <div className="meta">
                source={product.source} · shop={product.shop_name ?? "-"}
              </div>
              <div className="product-title">
                {product.title || "(タイトル未取得 — メモで補足してください)"}
              </div>
              {product.price_yen !== null && (
                <div>¥{product.price_yen.toLocaleString()}</div>
              )}
              {product.description && (
                <div className="product-desc">
                  {product.description.slice(0, 200)}
                </div>
              )}
              <div className="product-link">
                アフィ URL (リプ側に配置):{" "}
                <button
                  type="button"
                  className="link-button"
                  onClick={async () => {
                    try {
                      await openUrl(product.affiliate_url);
                    } catch (e) {
                      setError(`ブラウザを開けません: ${String(e)}`);
                    }
                  }}
                  title="ブラウザで開く"
                >
                  {product.affiliate_url.length > 80
                    ? product.affiliate_url.slice(0, 77) + "…"
                    : product.affiliate_url}
                </button>
              </div>
            </div>
          )}
          <label className="field">
            <span>ayaの補足メモ (強調したい点 / 使用感 / NG など)</span>
            <textarea
              rows={3}
              value={affMemo}
              onChange={(e) => setAffMemo(e.target.value)}
              placeholder="例: 蓋が丸ごと外せて洗いやすいのが刺さった。買って 2 週間。"
            />
          </label>
        </section>
      )}

      <section className="panel image-panel">
        <h2>画像 (任意)</h2>
        <p className="image-hint">
          生活感のある写真は滞在時間 (A 級シグナル) を伸ばす重要要素。
          Bluesky は最大 4 枚 / 1 枚 976 KB まで実投稿に添付されます。
          <span className="image-note">
            ※ Threads API は画像の直接アップロード非対応のため、投稿後に Threads アプリから手動追加してください。
          </span>
        </p>
        <div className="row">
          <button
            type="button"
            onClick={handleImagePick}
            disabled={images.length >= MAX_IMAGES}
          >
            🖼 画像を選ぶ ({images.length}/{MAX_IMAGES})
          </button>
          {images.length > 0 && (
            <button type="button" onClick={handleImageClear}>
              すべて外す
            </button>
          )}
        </div>
        {imageThumbs.length > 0 && (
          <div className="image-grid">
            {imageThumbs.map(({ path, url }, idx) => {
              const name = basename(path);
              return (
                <div key={`${path}-${idx}`} className="image-thumb">
                  <img src={url} alt={name} />
                  <button
                    type="button"
                    className="image-remove"
                    onClick={() => handleImageRemove(idx)}
                    title="この画像を外す"
                    aria-label={`${name} を外す`}
                  >
                    ×
                  </button>
                  <div className="image-meta">
                    <span className="image-name" title={path}>
                      {name}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <section className="panel generate-section">
        <h2>文章生成 ({mode === "preparation" ? "準備期間" : "本投稿"}モード)</h2>
        <div className="row">
          <button
            type="button"
            className="btn-primary"
            onClick={handleGenerate}
            disabled={generating || (mode === "affiliate" && !product)}
          >
            {generating ? "生成中…" : "✨ 生成"}
          </button>
          {mode === "affiliate" && !product && (
            <span className="hint-inline">先に商品情報を取得してください</span>
          )}
        </div>
        {generated && (
          <div className="output">
            <div className="meta">
              provider={generated.provider} · model={generated.model} ·
              tokens in/out={generated.tokens_in}/{generated.tokens_out} ·
              {generated.duration_ms}ms
            </div>
            <textarea
              className="generated-edit"
              rows={10}
              value={editedText}
              onChange={(e) => setEditedText(e.target.value)}
              spellCheck={false}
            />
            <div className="row generated-toolbar">
              <button type="button" onClick={handleCopy}>
                📋 コピー
              </button>
              <button
                type="button"
                className="btn-note"
                onClick={handleCopyAndOpenNote}
                title="クリップボードにコピーしてから note 新規投稿ページを開きます"
              >
                📝 note にコピー & 開く
              </button>
              {(sns === "bluesky" || sns === "threads") && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={handlePublish}
                  disabled={
                    publishing ||
                    !editedText.trim() ||
                    overLimit ||
                    (validation?.error_count ?? 0) > 0 ||
                    (sns === "threads" && mode === "affiliate" && !product)
                  }
                  title={
                    sns === "threads" && mode === "affiliate"
                      ? "Threads に投稿 (本文 → 自動でアフィ URL をリプ投稿)"
                      : `${SNS_LABELS[sns].short} に直接投稿します`
                  }
                >
                  {publishing
                    ? "投稿中…"
                    : sns === "bluesky"
                      ? "🦋 Bluesky に投稿"
                      : "🧵 Threads に投稿"}
                </button>
              )}
              <button type="button" onClick={handleResetText}>
                ↺ 元に戻す
              </button>
              <span className={overLimit ? "char-count over" : "char-count"}>
                {charCount} / {charLimit} 字
                {overLimit && " — 超過！"}
              </span>
              {copyStatus && <span className="copy-status">{copyStatus}</span>}
            </div>
            {publishResult && publishResult.success && (
              <div className="output publish-success">
                <span className="val-check">✓</span> 投稿成功！
                {publishResult.sns_post_url && (
                  <>
                    {" "}
                    <button
                      type="button"
                      className="link-button"
                      onClick={async () => {
                        try {
                          await openUrl(publishResult.sns_post_url!);
                        } catch (e) {
                          setError(`ブラウザを開けません: ${String(e)}`);
                        }
                      }}
                    >
                      投稿を開く
                    </button>
                  </>
                )}
              </div>
            )}
            {validation && <ValidationPanel validation={validation} />}
            <div className="post-hint">
              {mode === "affiliate"
                ? "⚠ 親ポストに URL が混入していないか確認。投稿後 15 分以内に自己リプ返信しよう。"
                : "⚠ 商品名や URL が混入していないか確認 (準備期間は信用貯金フェーズ)。"}
            </div>
          </div>
        )}
      </section>

      {error && (
        <section className="panel error-panel">
          <p className="error">Error: {error}</p>
        </section>
      )}

      {/* Dev-only diagnostics — hidden in `pnpm tauri build` (production). */}
      {import.meta.env.DEV && (
        <section className="panel dev-panel">
          <h2>🔧 疎通確認 (開発用)</h2>
          <p className="dev-note">
            本番ビルドでは非表示。ayaさんには見えません。
          </p>
          <div className="row">
            <button type="button" onClick={handlePing}>
              Ping (Rust のみ)
            </button>
          </div>
          {pong && <p className="success">Rust Response: {pong}</p>}
          <div className="row" style={{ marginTop: "0.75rem" }}>
            <input
              type="text"
              value={pingMessage}
              onChange={(e) => setPingMessage(e.target.value)}
              placeholder="sidecar に送るメッセージ"
            />
            <button type="button" onClick={handleSidecarPing}>
              Ping (Rust → Python → Rust)
            </button>
          </div>
          {sidecarPong && (
            <p className="success">Sidecar Response: {sidecarPong}</p>
          )}
        </section>
      )}

      <footer className="page-footer">
        <button
          type="button"
          className="footer-link"
          onClick={handleOpenLogs}
          title="アプリの動作ログを保存しているフォルダを開きます"
        >
          うまく動かない時はこちら
        </button>
      </footer>
    </main>
  );
}

function ValidationPanel({
  validation,
}: {
  validation: ValidationData;
}): JSX.Element {
  const { issues, error_count, warning_count } = validation;
  if (issues.length === 0) {
    return (
      <div className="validation-panel validation-ok">
        <span className="val-check">✓</span> Threads ルールチェック通過
      </div>
    );
  }
  return (
    <div className="validation-panel">
      <div className="val-summary">
        {error_count > 0 && (
          <span className="val-sum val-sum-error">⛔ エラー {error_count}</span>
        )}
        {warning_count > 0 && (
          <span className="val-sum val-sum-warn">⚠ 注意 {warning_count}</span>
        )}
      </div>
      <ul className="val-issues">
        {issues.map((issue) => (
          <li key={issue.rule_id} className={`val-issue val-${issue.severity}`}>
            <span className="val-badge">
              {issue.severity === "error"
                ? "⛔"
                : issue.severity === "warning"
                  ? "⚠"
                  : "ℹ"}
            </span>
            <span className="val-message">{issue.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
