from typing import Dict, Any

from slack_bolt.async_app import AsyncApp, AsyncAck
from slack_bolt.request.payload_utils import is_event

from .assistant_thread_started import start_thread_with_suggested_prompts
from .asssistant_thread_context_changed import save_new_thread_context
from .user_message import respond_to_user_message, respond_to_direct_message
from .verify_url import respond_to_url_verification

def register(app: AsyncApp):
    app.event("assistant_thread_started")(start_thread_with_suggested_prompts)
    app.event("assistant_thread_context_changed")(save_new_thread_context)
    app.event("app_mention")(respond_to_direct_message)
    app.event("message", matchers=[is_thread])(respond_to_user_message)
    # Default case: not an assistant thread or channel thread
    app.event("message")(just_ack)
    app.event("url_verification")(respond_to_url_verification)
    app.action("install_supercog_slack_app")(just_ack)

async def is_thread(body: Dict[str, Any]) -> bool:
    print("Slack is thread test: ")
    if is_event(body):
        message_metadata = body.get("event")
        if message_metadata:
            return message_metadata.get("thread_ts") and (message_metadata.get("thread_ts") != message_metadata.get("ts"))
        
    return False

async def just_ack(ack: AsyncAck):
    print("Slack just_ask: ", ack)
    await ack()
    return
