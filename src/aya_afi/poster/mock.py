"""Deterministic mock Poster for tests + keyless dev flows."""

from __future__ import annotations

from aya_afi.poster.base import PostRequest, PostResult


class MockPoster:
    name = "mock"

    def __init__(self, *, fail: bool = False, fail_type: str = "mock_failure") -> None:
        self._fail = fail
        self._fail_type = fail_type

    async def publish(self, req: PostRequest) -> PostResult:
        if self._fail:
            return PostResult(
                success=False,
                sns=req.sns,
                error_type=self._fail_type,
                error_message=f"mock poster configured to fail for {req.sns.value}",
            )
        post_id = f"mock-{req.idempotency_key[:8]}"
        reply_id = f"{post_id}-reply" if req.reply_body else None
        return PostResult(
            success=True,
            sns=req.sns,
            sns_post_id=post_id,
            sns_post_url=f"https://mock.example.test/posts/{post_id}",
            reply_post_id=reply_id,
        )
