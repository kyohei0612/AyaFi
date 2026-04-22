"""Threads post validator (2026 algorithm-aware rules).

Rules derived from ADR-012: parent post must not contain URLs, hashtag count
<= 1, question-style close, 500-char limit, #PR only on affiliate posts.

Each rule has a stable ``rule_id`` so the UI / future analytics can reference
findings without parsing message text.
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

THREADS_MAX_CHARS = 500

# Matches hashtags with ASCII, hiragana, katakana, kanji. Avoids matching
# stray '#' inside URLs by requiring whitespace / start-of-string before it.
_HASHTAG_RE = re.compile(
    r"(?:^|\s)#[\w\u3040-\u30ff\u4e00-\u9fff\u30fc\u30fb]+",
    re.UNICODE,
)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# Last-line / last-sentence question indicators (Japanese or ASCII mark).
_QUESTION_TAIL_RE = re.compile(r"[?？][^\n]{0,20}$", re.MULTILINE)

_PR_TAG_VARIANTS = ("#PR", "#pr", "#広告", "#ad")


def validate_threads_post(body: str, mode: PostMode) -> ValidationReport:
    """Run all Threads rules over ``body`` under the given mode."""
    issues: list[ValidationIssue] = []
    char_count = len(body)

    # Rule: character count
    if char_count > THREADS_MAX_CHARS:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.error,
                rule_id="threads.too_long",
                message=(
                    f"文字数が {char_count} 字で、上限 {THREADS_MAX_CHARS} 字を超えています。"
                    f"{char_count - THREADS_MAX_CHARS} 字ほど削ってください。"
                ),
                field="body",
            )
        )

    # Rule: hashtag count. Threads は 1 投稿 1 タグが最適 (ADR-012 §4)。
    hashtags = _HASHTAG_RE.findall(body)
    if len(hashtags) > 1:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.error,
                rule_id="threads.too_many_hashtags",
                message=(
                    f"ハッシュタグが {len(hashtags)} 個あります。"
                    "Threads では 1 個までに絞ってください (多いとスパム扱い)。"
                ),
                field="tags",
            )
        )

    # Rule: parent post must not contain URLs (ADR-012 §2 — 致命的ペナルティ)。
    urls = _URL_RE.findall(body)
    if urls:
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.error,
                rule_id="threads.url_in_parent",
                message=(
                    "本文に URL が含まれています。Threads は親ポストに URL があると "
                    "初期 15 分で露出が 80% カットされます。URL はアプリがリプ側に "
                    "自動配置するので、本文からは削除してください。"
                ),
                field="body",
            )
        )

    # Rule: conversation-inducing question at end (ADR-012 §1 — S 級シグナル)。
    if not _QUESTION_TAIL_RE.search(body):
        issues.append(
            ValidationIssue(
                severity=ValidationSeverity.warning,
                rule_id="threads.missing_question",
                message=(
                    "末尾に問いかけ (「?」「？」) が見当たりません。"
                    "返信が生まれる投稿ほどアルゴリズムに拾われやすいので、"
                    "会話誘発の一文で締めるのが推奨です。"
                ),
                field="body",
            )
        )

    # Mode-specific rules
    has_pr_tag = any(tag in body for tag in _PR_TAG_VARIANTS)
    if mode == PostMode.affiliate:
        if not has_pr_tag:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.error,
                    rule_id="threads.missing_pr_tag",
                    message=(
                        "アフィ投稿には #PR または #広告 タグが必要です "
                        "(消費者庁ステマ規制、2023/10 施行)。"
                    ),
                    field="tags",
                )
            )
    else:  # PostMode.preparation
        if has_pr_tag:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.warning,
                    rule_id="threads.pr_tag_in_preparation",
                    message=(
                        "準備期間モードで #PR / #広告 タグが含まれています。"
                        "準備期間は信用貯金フェーズなので、アフィ表記は避けるのが安全です。"
                    ),
                    field="tags",
                )
            )

    return ValidationReport(
        sns=SnsKind.threads,
        mode=mode,
        char_count=char_count,
        issues=issues,
    )
