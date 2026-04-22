"""Action handlers registered with ``IpcServer``.

Kept separate from the server class so each handler can be unit-tested in
isolation with a mock LLM or other test double.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from aya_afi.affiliate.factory import create_provider_for_url
from aya_afi.config.settings import Settings
from aya_afi.ipc.protocol import (
    SCHEMA_VERSION,
    FetchProductParams,
    FetchProductResult,
    GeneratePostParams,
    GeneratePostResult,
    Request,
    ValidateContentParams,
    ValidateContentResult,
    ValidationIssueDto,
)
from aya_afi.llm.base import GenerationRequest, LLMProvider
from aya_afi.sns_engine.base import PostMode, SnsKind
from aya_afi.sns_engine.validators import validate_threads_post

HandlerFn = Callable[[Request], Awaitable[dict[str, object]]]


async def handle_ping(req: Request) -> dict[str, object]:
    """Cheap echo used by UI + tests to prove the IPC round trip works."""
    return {"pong": True, "echo": req.params.get("message")}


async def handle_health_check(_req: Request) -> dict[str, object]:
    return {"status": "ok", "protocol_version": SCHEMA_VERSION}


def make_fetch_product_handler(settings: Settings) -> HandlerFn:
    """Return a handler closure that resolves a product URL via the affiliate factory."""

    async def handle(req: Request) -> dict[str, object]:
        params = FetchProductParams.model_validate(req.params)
        provider = create_provider_for_url(params.url, settings)
        info = await provider.fetch(params.url)
        result = FetchProductResult(
            url=info.url,
            source=info.source.value,
            affiliate_url=info.affiliate_url,
            title=info.title,
            price_yen=info.price_yen,
            description=info.description,
            image_urls=info.image_urls,
            shop_name=info.shop_name,
            category=info.category,
        )
        return result.model_dump()

    return handle


async def handle_validate_content(req: Request) -> dict[str, object]:
    """Validate generated content against SNS-specific rules (Stage 4.a)."""
    params = ValidateContentParams.model_validate(req.params)
    sns = SnsKind(params.sns)
    mode = PostMode(params.mode)

    if sns == SnsKind.threads:
        report = validate_threads_post(params.body, mode)
    else:
        # Bluesky / note validators land in Stage 4.b. For now, return a
        # minimal report so the UI can show "validator not yet available".
        from aya_afi.sns_engine.base import ValidationReport

        report = ValidationReport(sns=sns, mode=mode, char_count=len(params.body), issues=[])

    result = ValidateContentResult(
        sns=sns.value,
        mode=mode.value,
        char_count=report.char_count,
        error_count=report.error_count,
        warning_count=report.warning_count,
        issues=[
            ValidationIssueDto(
                severity=i.severity.value,
                rule_id=i.rule_id,
                message=i.message,
                field=i.field,
            )
            for i in report.issues
        ],
    )
    return result.model_dump()


def make_generate_post_handler(llm: LLMProvider) -> HandlerFn:
    """Return a handler closure that forwards to the given LLM provider."""

    async def handle(req: Request) -> dict[str, object]:
        params = GeneratePostParams.model_validate(req.params)
        llm_req = GenerationRequest(
            system_prompt=params.system_prompt,
            user_prompt=params.user_prompt,
            temperature=params.temperature,
            max_output_tokens=params.max_output_tokens,
        )
        llm_resp = await llm.generate(llm_req)
        result = GeneratePostResult(
            text=llm_resp.text,
            model=llm_resp.model,
            provider=llm_resp.provider,
            tokens_in=llm_resp.tokens_in,
            tokens_out=llm_resp.tokens_out,
            duration_ms=llm_resp.duration_ms,
        )
        return result.model_dump()

    return handle
