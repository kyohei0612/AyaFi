"""もしもアフィリエイト redirect URL builder (Amazon promotion).

もしもアフィリエイトには「商品情報を取得する公開 API」が無いため、この
プロバイダは**商品情報を取得せず、アフィ URL を構築するだけ**にする。
商品タイトル / 説明 / 画像は妻が手入力することを前提とした設計
(ADR-002: 妻は商品選びの一次情報を自分で入れる)。

Amazon PA-API を使わない理由: 過去 180 日以内に適格販売 3 件が必要で、
v0.1 時点では達成不能 (ADR-001 影響範囲)。

See: docs/decisions/002-mvp-scope.md (F02) and docs/decisions/001-initial-architecture.md.
"""

from __future__ import annotations

from urllib.parse import quote_plus, urlencode

from aya_afi.affiliate.base import ProductInfo, ProductSource
from aya_afi.affiliate.errors import AffiliateConfigError
from aya_afi.affiliate.urls import parse_amazon_asin

MOSHIMO_CLICK_BASE = "https://af.moshimo.com/af/c/click"
AMAZON_CANONICAL_URL_TEMPLATE = "https://www.amazon.co.jp/dp/{asin}"


class MoshimoAmazonProvider:
    """Routes Amazon URLs through a もしもアフィリエイト click redirect.

    ``a_id`` / ``p_id`` / ``pc_id`` / ``pl_id`` are all issued by もしも to the
    user after approving an application for the Amazon promotion. They can be
    copied from the もしも管理画面 once the partnership is active.
    """

    name = "moshimo_amazon"

    def __init__(self, a_id: str, p_id: str, pc_id: str, pl_id: str) -> None:
        if not a_id:
            raise AffiliateConfigError("MOSHIMO_A_ID is required")
        missing = [
            label
            for label, value in (
                ("MOSHIMO_AMAZON_P_ID", p_id),
                ("MOSHIMO_AMAZON_PC_ID", pc_id),
                ("MOSHIMO_AMAZON_PL_ID", pl_id),
            )
            if not value
        ]
        if missing:
            raise AffiliateConfigError(
                f"moshimo Amazon promotion needs {', '.join(missing)}; "
                "copy them from the もしも管理画面 after approval."
            )
        self._a_id = a_id
        self._p_id = p_id
        self._pc_id = pc_id
        self._pl_id = pl_id

    async def fetch(self, url: str) -> ProductInfo:
        asin = parse_amazon_asin(url)
        canonical = AMAZON_CANONICAL_URL_TEMPLATE.format(asin=asin)
        return ProductInfo(
            url=url,
            source=ProductSource.amazon,
            affiliate_url=self.build_click_url(canonical),
            title="",
            description="",
        )

    def build_click_url(self, target_url: str) -> str:
        ids = urlencode(
            {
                "a_id": self._a_id,
                "p_id": self._p_id,
                "pc_id": self._pc_id,
                "pl_id": self._pl_id,
            }
        )
        return f"{MOSHIMO_CLICK_BASE}?{ids}&url={quote_plus(target_url)}"
