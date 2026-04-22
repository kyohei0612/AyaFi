import { useEffect, useMemo, useState } from "react";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { open as openFileDialog } from "@tauri-apps/plugin-dialog";
import { check as checkForUpdate } from "@tauri-apps/plugin-updater";
import { relaunch } from "@tauri-apps/plugin-process";

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

  // Generation + publication are now run in parallel for both SNS at once
  // (per user flow: "one generate button, one publish button, two edited
  // texts"). Each SNS has its own draft + validation so char limits and tag
  // conventions are enforced independently.
  const [generating, setGenerating] = useState<boolean>(false);
  const [publishing, setPublishing] = useState<boolean>(false);
  const [copyStatus, setCopyStatus] = useState<string>("");
  const [error, setError] = useState<string>("");

  const [threadsGenerated, setThreadsGenerated] = useState<GenerateData | null>(null);
  const [threadsText, setThreadsText] = useState<string>("");
  const [threadsValidation, setThreadsValidation] = useState<ValidationData | null>(null);
  const [threadsPublishResult, setThreadsPublishResult] = useState<PublishData | null>(null);

  useEffect(() => {
    if (threadsGenerated) {
      setThreadsText(threadsGenerated.text);
      setThreadsPublishResult(null);
    }
  }, [threadsGenerated]);

  // Check for app updates on startup (silent if no update / if endpoint
  // unreachable in dev). When `dialog: true` is set in tauri.conf.json, the
  // plugin shows a native confirmation dialog; if the user accepts, we
  // download, install, then relaunch the shell so the new version runs.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const update = await checkForUpdate();
        if (cancelled || !update) return;
        await update.downloadAndInstall();
        await relaunch();
      } catch {
        // Dev builds have no signed endpoint — this throwing is expected.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-validate the Threads draft on change (debounced).
  useEffect(() => {
    if (!threadsText.trim()) {
      setThreadsValidation(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const resp = await invoke<SidecarResponse<ValidationData>>(
          "validate_content",
          { sns: "threads", mode, body: threadsText },
        );
        if (resp.ok && resp.data) setThreadsValidation(resp.data);
      } catch {
        /* best-effort */
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [threadsText, mode]);

  const threadsCharCount = useMemo(() => [...threadsText].length, [threadsText]);
  const threadsOverLimit = threadsCharCount > SNS_LABELS.threads.charLimit;

  const handleCopy = async (text: string, label: string): Promise<void> => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus(`${label} をコピーしました ✓`);
      setTimeout(() => setCopyStatus(""), 2500);
    } catch (e) {
      setCopyStatus(`コピー失敗: ${String(e)}`);
    }
  };

  const handleCopyAndOpenNote = async (text: string): Promise<void> => {
    try {
      setError("");
      await navigator.clipboard.writeText(text);
      await invoke("open_note_compose");
      setCopyStatus("note を開きました、本文欄で Ctrl+V で貼り付け ✓");
      setTimeout(() => setCopyStatus(""), 5000);
    } catch (e) {
      setError(`note へのコピー失敗: ${String(e)}`);
    }
  };

  const handleResetThreads = (): void => {
    if (threadsGenerated) setThreadsText(threadsGenerated.text);
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

  const buildPromptsFor = (sns: SnsKind): { system: string; user: string } => {
    const ngList = [...ngFlags];
    if (mode === "preparation") {
      return {
        system: buildSystemPrompt(sns, "preparation", ngList, profile),
        user: buildPreparationUserPrompt(soulTopic, prepMemo, sns),
      };
    }
    if (!product) throw new Error("本投稿モードでは、先に商品情報を取得してください。");
    return {
      system: buildSystemPrompt(sns, "affiliate", ngList, profile),
      user: buildAffiliateUserPrompt({
        productTitle: product.title,
        productDescription: product.description,
        productShop: product.shop_name,
        productPriceYen: product.price_yen,
        productAffiliateUrl: product.affiliate_url,
        userInput: affMemo,
        sns,
      }),
    };
  };

  const generateOne = async (sns: SnsKind): Promise<GenerateData | null> => {
    const { system, user } = buildPromptsFor(sns);
    const resp = await invoke<SidecarResponse<GenerateData>>("generate_post", {
      systemPrompt: system,
      userPrompt: user,
    });
    if (resp.ok && resp.data) return resp.data;
    throw new Error(
      `${SNS_LABELS[sns].short}: ${resp.error?.type}: ${resp.error?.message}`,
    );
  };

  const handleGenerate = async (): Promise<void> => {
    setError("");
    if (mode === "affiliate" && !product) {
      setError("本投稿モードでは、先に商品情報を取得してください。");
      return;
    }
    setThreadsGenerated(null);
    setGenerating(true);
    try {
      const data = await generateOne("threads");
      if (data) setThreadsGenerated(data);
    } catch (e) {
      setError("generate error: " + String((e as Error)?.message ?? e));
    } finally {
      setGenerating(false);
    }
  };

  const handlePublish = async (): Promise<void> => {
    if (!threadsText.trim()) return;

    // Threads affiliate mode: put the URL in a self-reply per ADR-012.
    const replyBody =
      mode === "affiliate" && product !== null
        ? `詳細はこちら👇\n${product.affiliate_url}`
        : undefined;

    const previewLines: string[] = [
      "Threads に投稿します。内容を確認してください。",
      "",
      threadsText,
    ];
    if (replyBody) {
      previewLines.push("", "── リプライ (アフィ URL) ──", replyBody);
    }
    if (images.length > 0) {
      previewLines.push("", `画像 ${images.length} 枚を添付 (catbox.moe 経由)`);
    }
    previewLines.push("", `${threadsCharCount} / ${SNS_LABELS.threads.charLimit} 字`);
    if (!window.confirm(previewLines.join("\n"))) return;

    setError("");
    setThreadsPublishResult(null);
    setPublishing(true);
    try {
      const resp = await invoke<SidecarResponse<PublishData>>("publish_post", {
        sns: "threads",
        body: threadsText,
        replyBody,
        imagePaths: images,
      });
      if (resp.ok && resp.data) {
        setThreadsPublishResult(resp.data);
      } else {
        setError(`publish error: ${resp.error?.type}: ${resp.error?.message}`);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setPublishing(false);
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
          最大 {MAX_IMAGES} 枚 / 1 枚 8 MB まで。2 枚以上はカルーセル投稿になります。
          <span className="image-note">
            ※ Threads API の仕様上、画像は一時的に catbox.moe (匿名公開ホスト) 経由でアップされます。
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
        <h2>🪄 文章生成 ({mode === "preparation" ? "準備期間" : "本投稿"}モード)</h2>
        <div className="row">
          <button
            type="button"
            className="btn-primary"
            onClick={handleGenerate}
            disabled={generating || (mode === "affiliate" && !product)}
          >
            {generating ? "生成中…" : "✨ Threads 文章を生成"}
          </button>
          {mode === "affiliate" && !product && (
            <span className="hint-inline">先に商品情報を取得してください</span>
          )}
        </div>
        <p className="mode-hint">
          Threads アルゴリズム: 親 URL NG / タグ 1 / 500 字。アフィ URL はアプリが自動でリプ側に配置します。
        </p>
      </section>

      {threadsGenerated && (
        <DraftPanel
          sns="threads"
          generated={threadsGenerated}
          text={threadsText}
          setText={setThreadsText}
          charCount={threadsCharCount}
          overLimit={threadsOverLimit}
          validation={threadsValidation}
          onCopy={() => handleCopy(threadsText, "本文")}
          onCopyToNote={() => handleCopyAndOpenNote(threadsText)}
          onReset={handleResetThreads}
          mode={mode}
        />
      )}

      {threadsGenerated && (
        <section className="panel publish-section">
          <h2>🚀 投稿</h2>
          {copyStatus && (
            <div className="row">
              <span className="copy-status">{copyStatus}</span>
            </div>
          )}
          <div className="row">
            <button
              type="button"
              className="btn-primary"
              onClick={handlePublish}
              disabled={
                publishing ||
                !threadsText.trim() ||
                threadsOverLimit ||
                (threadsValidation?.error_count ?? 0) > 0
              }
              title="Threads に直接投稿します"
            >
              {publishing ? "投稿中…" : "🚀 Threads に投稿"}
            </button>
          </div>
          {threadsPublishResult && (
            <PublishResult
              label="🧵 Threads"
              result={threadsPublishResult}
              onError={setError}
            />
          )}
          <div className="post-hint">
            {mode === "affiliate"
              ? "⚠ 親ポストに URL が混入していないか確認。投稿後 15 分以内に自己リプ返信しよう。"
              : "⚠ 商品名や URL が混入していないか確認 (準備期間は信用貯金フェーズ)。"}
          </div>
        </section>
      )}

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

function DraftPanel(props: {
  sns: SnsKind;
  generated: GenerateData;
  text: string;
  setText: (s: string) => void;
  charCount: number;
  overLimit: boolean;
  validation: ValidationData | null;
  onCopy: () => void | Promise<void>;
  onCopyToNote?: () => void | Promise<void>;
  onReset: () => void;
  mode: PostMode;
}): JSX.Element {
  const label = SNS_LABELS[props.sns];
  const charLimit = label.charLimit;
  return (
    <section className={`panel draft-panel draft-${props.sns}`}>
      <h2>
        {label.label} 下書き ({charLimit} 字 / {label.tagLabel})
      </h2>
      <div className="meta">
        provider={props.generated.provider} · model={props.generated.model} ·
        tokens in/out={props.generated.tokens_in}/{props.generated.tokens_out}
        {" · "}
        {props.generated.duration_ms}ms
      </div>
      <textarea
        className="generated-edit"
        rows={props.sns === "threads" ? 12 : 8}
        value={props.text}
        onChange={(e) => props.setText(e.target.value)}
        spellCheck={false}
      />
      <div className="row generated-toolbar">
        <button type="button" onClick={() => void props.onCopy()}>
          📋 コピー
        </button>
        {props.onCopyToNote && (
          <button
            type="button"
            className="btn-note"
            onClick={() => void props.onCopyToNote!()}
            title="クリップボードにコピーしてから note 新規投稿ページを開きます"
          >
            📝 note にコピー & 開く
          </button>
        )}
        <button type="button" onClick={props.onReset}>
          ↺ 元に戻す
        </button>
        <span className={props.overLimit ? "char-count over" : "char-count"}>
          {props.charCount} / {charLimit} 字
          {props.overLimit && " — 超過！"}
        </span>
      </div>
      {props.validation && (
        <ValidationPanel sns={props.sns} validation={props.validation} />
      )}
    </section>
  );
}

function PublishResult(props: {
  label: string;
  result: PublishData;
  onError: (msg: string) => void;
}): JSX.Element {
  if (!props.result.success) {
    return (
      <div className="output publish-error">
        ⛔ {props.label} 投稿失敗: {props.result.error_type}:{" "}
        {props.result.error_message}
      </div>
    );
  }
  return (
    <div className="output publish-success">
      <span className="val-check">✓</span> {props.label} 投稿成功！
      {props.result.sns_post_url && (
        <>
          {" "}
          <button
            type="button"
            className="link-button"
            onClick={async () => {
              try {
                await openUrl(props.result.sns_post_url!);
              } catch (e) {
                props.onError(`ブラウザを開けません: ${String(e)}`);
              }
            }}
          >
            投稿を開く
          </button>
        </>
      )}
    </div>
  );
}

function ValidationPanel({
  sns,
  validation,
}: {
  sns: SnsKind;
  validation: ValidationData;
}): JSX.Element {
  const { issues, error_count, warning_count } = validation;
  if (issues.length === 0) {
    return (
      <div className="validation-panel validation-ok">
        <span className="val-check">✓</span> {SNS_LABELS[sns].short}{" "}
        ルールチェック通過
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
