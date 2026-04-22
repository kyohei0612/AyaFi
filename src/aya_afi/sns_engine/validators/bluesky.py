"""Bluesky post validator (2026 algorithm-aware rules).

Rules derived from Bluesky's time-ordered + custom-feed culture. Key
differences from Threads (see validators/threads.py):
- URLs in parent post are FINE (no penalty) — opposite of Threads
- Hashtags are REQUIRED, not banned — opposite of Threads (feed pickup)
- Char limit is 300 (not 500)
- Alt text for images is socially expected (accessibility culture)

Rules have stable ``rule_id`` values so the UI / future analytics can
reference findings without parsing message text.
"""

from __future__ import annotations

import re

from aya_afi.sns_engine.base import (
    PostMode,
    SnsKind,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)

BLUESKY_MAX_CHARS = 300

_HASHTAG_RE = re.compile(
    r"(?:^|\s)#[\w\u3040-\u30ff\u4e00-\u9fff\u30fc\u30fb]+",
    re.UNICODE,
)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

_QUESTION_TAIL_RE = re.compile(r"[??][^\n]{0,30}$", re.MULTILINE)

_PR_TAG_VARIANTS = ("#PR", "#pr", "#広告", "#ad")

# A concrete number or spec helps Bluesky's engineer/creator audience trust
# the post. We detect any integer in the body as a weak signal.
_NUMBER_RE = re.compile(r"[0-9]+")


def validate_bluesky_post(body: str, mode: PostMode) -> ValidationReport:
    """Run Bluesky rules over ``body`` under the given mode."""
    issues: list[ValidationIssue] = []
    char_count = len(body)

    # Rule: character count
    if char_count > BLUESKY_MAX_CHARS:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.error,
                rule_id="bluesky.too_long",
                message=(
                    f"文字数が {char_count} 字で、上限 {BLUESKY_MAX_CHARS} 字を超えています。"
                    f"{char_count - BLUESKY_MAX_CHARS} 字ほど削ってください。"
                ),
                field="body",
            )
        )

    hashtags = _HASHTAG_RE.findall(body)
    has_pr_tag = any(tag in body for tag in _PR_TAG_VARIANTS)

    # Rule: must have at least 1 hashtag (custom feed pickup is Bluesky's
    # primary discovery mechanism, unlike Threads which prefers 0-1).
    if not hashtags:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.warning,
                rule_id="bluesky.no_hashtags",
                message=(
                    "ハッシュタグが 1 つもありません。Bluesky では"
                    "カスタムフィード拾いの要なので、ジャンル系タグ "
                    "(例: #時短家事 #子育て) を 2-3 個入れるのが推奨です。"
                ),
                field="tags",
            )
        )
    elif len(hashtags) > 5:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.warning,
                rule_id="bluesky.too_many_hashtags",
                message=(
                    f"ハッシュタグが {len(hashtags)} 個と多めです。"
                    "Bluesky では 2-5 個程度が最適 (それ以上はスパム印象)。"
                ),
                field="tags",
            )
        )

    # Rule: affiliate mode requires #PR / #広告 tag (景表法 + エンゲージ上
    # の信頼性)。
    if mode == PostMode.affiliate and not has_pr_tag:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.error,
                rule_id="bluesky.missing_pr_tag",
                message=(
                    "アフィ投稿には #PR または #広告 タグが必要です "
                    "(消費者庁ステマ規制、2023/10 施行)。"
                ),
                field="tags",
            )
        )
    elif mode == PostMode.preparation and has_pr_tag:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.warning,
                rule_id="bluesky.pr_tag_in_preparation",
                message=(
                    "準備期間モードで #PR / #広告 タグが含まれています。"
                    "準備期間は信用貯金フェーズなので、アフィ表記は避けましょう。"
                ),
                field="tags",
            )
        )

    # Rule: concrete number / spec is a trust signal on Bluesky (info-dense
    # audience). Missing numbers → recommend adding for affiliate posts.
    if mode == PostMode.affiliate and not _NUMBER_RE.search(body):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.info,
                rule_id="bluesky.no_concrete_spec",
                message=(
                    "具体的な数値 (重量 / 価格 / 時間 / 容量 等) が見当たりません。"
                    "Bluesky の読者層には具体スペックが信頼に直結します。"
                ),
                field="body",
            )
        )

    # Rule: URL count warning. Multiple URLs mean only the first gets an
    # OGP card (visual weight). For single-post style, 1 URL is ideal.
    urls = _URL_RE.findall(body)
    if len(urls) > 1:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.info,
                rule_id="bluesky.multiple_urls",
                message=(
                    f"URL が {len(urls)} 本含まれています。"
                    "Bluesky では OGP カードが出るのは最初の 1 本だけなので、"
                    "1 投稿 1 URL に絞るのが見栄えよいです。"
                ),
                field="body",
            )
        )

    return ValidationReport(
        sns=SnsKind.bluesky,
        mode=mode,
        char_count=char_count,
        issues=issues,
    )
