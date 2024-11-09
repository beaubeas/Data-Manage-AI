from slack_sdk.web.async_client import AsyncWebClient
from slack_bolt.async_app import AsyncApp, AsyncBoltContext

from .thread_context_store import save_thread_context

async def save_new_thread_context(
    payload: dict,
    client: AsyncWebClient,
    context: AsyncBoltContext,
):
    thread = payload["assistant_thread"]
    await save_thread_context(
        context=context,
        client=client,
        channel_id=thread["channel_id"],
        thread_ts=thread["thread_ts"],
        new_context=thread.get("context"),
    )
