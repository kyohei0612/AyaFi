"""One-off: verify Threads posting works end-to-end.

Posts a single harmless test message to the authenticated Threads profile via
the 2-step create→publish flow. Nothing else — no retries, no images, no
reply. Useful right after token setup to confirm `threads_content_publish`
actually functions before investing in the full poster implementation.

Usage:
    .venv/Scripts/python scripts/test_threads_post.py [body]

Reads THREADS_USER_ID and THREADS_ACCESS_TOKEN from secrets/.env. Prints the
resulting post URL on success.

Docs: https://developers.facebook.com/docs/threads/posts
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from aya_afi.config.settings import Settings

GRAPH_BASE = "https://graph.threads.net/v1.0"
DEFAULT_BODY = "AyaFi 接続テスト (開発用・数分後に削除予定)"


def main() -> int:
    body = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BODY

    env_path = Path(__file__).resolve().parent.parent / "secrets" / ".env"
    load_dotenv(env_path)
    settings = Settings()

    if not (settings.threads_access_token and settings.threads_user_id):
        print("THREADS_ACCESS_TOKEN / THREADS_USER_ID missing in .env", file=sys.stderr)
        return 2

    token = settings.threads_access_token
    user_id = settings.threads_user_id

    with httpx.Client(timeout=30.0) as client:
        # Step 1: create media container
        container = client.post(
            f"{GRAPH_BASE}/{user_id}/threads",
            params={
                "media_type": "TEXT",
                "text": body,
                "access_token": token,
            },
        )
        if container.status_code != 200:
            print(f"container create failed: {container.status_code} {container.text}",
                  file=sys.stderr)
            return 1
        container_id = container.json()["id"]
        print(f"[1/2] container id : {container_id}")

        # Step 2: publish
        publish = client.post(
            f"{GRAPH_BASE}/{user_id}/threads_publish",
            params={"creation_id": container_id, "access_token": token},
        )
        if publish.status_code != 200:
            print(f"publish failed: {publish.status_code} {publish.text}", file=sys.stderr)
            return 1
        post_id = publish.json()["id"]
        print(f"[2/2] post id      : {post_id}")

        # Fetch permalink so we can open it in the browser
        meta = client.get(
            f"{GRAPH_BASE}/{post_id}",
            params={"fields": "id,permalink,text", "access_token": token},
        )
        if meta.status_code == 200:
            permalink = meta.json().get("permalink")
            print(f"permalink          : {permalink}")

    print("=" * 70)
    print("Threads post SUCCESS - verify on threads.net and delete if desired.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
