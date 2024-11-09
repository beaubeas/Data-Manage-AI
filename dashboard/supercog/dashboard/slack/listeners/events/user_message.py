import re
import logging
from logging import Logger

from slack_sdk.web.async_client import AsyncWebClient
from slack_bolt.async_app import AsyncBoltContext

from .thread_context_store import has_bot_posted_in_thread
from .slack_ui import markdown_to_slack_rich_text

import reflex as rx

from supercog.shared.apubsub import (
    AgentOutputEvent,
    EnableToolEvent,
)
from supercog.dashboard.models import Agent, Tool
from supercog.dashboard.slack.utils.convo_utils import (
    get_channel_info, 
    msg_accessory,
    post_link_to_reply_in_channel,
    SlackUploadedFile,
    upload_files_to_slack, 
)
from .chat_manager import ChatManager

slack_logger = logging.getLogger("slack_app")

# ChatManager handles all the interaction with supercog agents. It maintains a map of
# conversations -> EngineClient+Agent Run instances.
chat_manager = ChatManager()

async def respond_to_direct_message(
    payload: dict,
    body: dict,
    client: AsyncWebClient,
    context: AsyncBoltContext,
    logger: Logger,
):
    slack_logger.debug("Here is the DIRECT user message:", payload)
    text = payload["text"]
    text = re.sub(r"^\<@\w+>", "", text)
    payload["text"] = text

    await respond_to_user_message(payload, body, client, context, logger, True)

async def respond_to_user_message(
    payload: dict,
    body: dict,
    client: AsyncWebClient,
    context: AsyncBoltContext,
    logger: Logger,
    force_message: bool = False
):
    try:
        channel_id = payload["channel"]
        user_id = payload["user"]
        team_id = body["team_id"]
        user_message = payload["text"]
        files = payload.get("files", [])
        thread_ts = payload.get("thread_ts")
        message_ts = payload["ts"]
        ts = thread_ts or message_ts
        # get channel name and determine if its a public channel (got the code from Claude!)
        channel_info = get_channel_info(payload, team_id)

        # Only respond if this is a bot thread
        if not force_message:
            is_bot_thread = await has_bot_posted_in_thread(
                context=context,
                client=client,
                channel_id=channel_id,
                thread_ts=thread_ts,
            )
            if not is_bot_thread:
                return
            
        # Set to thinking
        await client.assistant_threads_setStatus(
            channel_id=channel_id,
            thread_ts=ts,
            status="is thinking...",
        )

        slack_logger.debug("Calling the agent and waiting for reply")
        full_reply = ""
        batch = ""
        uploaded_files = []
        message_ts = ""
        async for agevent in chat_manager.call_agent_and_wait(
            logger, 
            client, 
            channel_info, 
            ts, 
            user_id, 
            team_id, 
            user_message, 
            files,
        ):
            if isinstance(agevent, AgentOutputEvent):
                reply = ""
                if agevent.str_result or agevent.object_result:
                    reply = agevent.str_result or str(agevent.object_result)
                batch += reply
                if len(batch) > 100:
                    full_reply += batch
                    message_ts = await update_response(
                        client=client,
                        logger=logger,
                        uploaded_files=uploaded_files,
                        content=full_reply,
                        channel_id=channel_id,
                        thread_ts=ts,
                        message_ts=message_ts,
                    )
                    batch = ""
            elif isinstance(agevent, EnableToolEvent):
                pass
                # Don't do anything Dashboard side with tool events. Leave those local to the Run. 
                # with rx.session() as session:
                #     agent = session.get(Agent, agevent.agent_id)
                #     if agent:
                #         if len([t for t in agent.tools if t.tool_factory_id == agevent.tool_factory_id]) == 0:
                #             # safe to add Tool
                #             tool = Tool(
                #                 agent_id=agent.id,
                #                 tool_name = agevent.name,
                #                 tool_factory_id=agevent.tool_factory_id,
                #                 credential_id = agevent.credential_id,
                #             )
                #             session.add(tool)
                #             session.commit()

        if len(batch) > 0:
            full_reply += batch

        if not chat_manager.sent_ephemeral_message:
            message_ts = await update_response(
                client=client,
                logger=logger,
                uploaded_files=uploaded_files,
                content=full_reply,
                channel_id=channel_id,
                thread_ts=ts,
                message_ts=message_ts,
                is_final=True,
            )

            # Post the preview if in a public channel
            if channel_info.is_public:
                await post_link_to_reply_in_channel(
                    client=client,
                    context=context,
                    channel_id=channel_id,
                    logger=logger,
                    thread_ts=ts,
                    message_ts=message_ts,
                )

        slack_logger.debug("Done waiting for the agent reply")
    except Exception as e:
        logger.exception(f"Failed to handle a user message event: {e}")
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=ts,
            text=f":warning: Something went wrong posting to Slack. Please try again!",
        )

    await client.assistant_threads_setStatus(
        channel_id=channel_id,
        thread_ts=ts,
        status="",
    )

async def update_response(
        client: AsyncWebClient,
        logger: Logger,
        uploaded_files: list[SlackUploadedFile],
        content: str,
        channel_id: str,
        thread_ts: str,
        message_ts: str,
        is_final: bool = False,
    ) -> str:
    # First add any files to slack
    content = await upload_files_to_slack(
        client=client,
        logger=logger,
        uploaded_files=uploaded_files,
        markdown_content=content,
        channel_id=channel_id,
        thread_ts=thread_ts
    )

    blocks = markdown_to_slack_rich_text(content or "Supercog was unable to respond")

    # Comment out for now, does nothing
    # if is_final:
    #     blocks[0] |= msg_accessory

    if message_ts:
        await client.chat_update(
            channel=channel_id,
            ts=message_ts,
            text=content,
            blocks=blocks,
            replace_original=True,
        )
        return message_ts
    else:
        result = await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=content,
            blocks=blocks,
        )
        return result.get("ts")
