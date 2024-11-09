from typing import List, Dict
from logging import Logger

from slack_sdk.web.async_client import AsyncWebClient

async def start_thread_with_suggested_prompts(
    payload: dict,
    client: AsyncWebClient,
    logger: Logger,
):
    thread = payload["assistant_thread"]
    channel_id, thread_ts = thread["channel_id"], thread["thread_ts"]
    try:
        thread_context = thread.get("context")
        message_metadata = (
            {
                "event_type": "assistant_thread_context",
                "event_payload": thread_context,
            }
            if bool(thread_context) is True  # the dict is not empty
            else None
        )
        print("Thread metadata:", message_metadata)
        await client.chat_postMessage(
            text="How can I help you?",
            channel=channel_id,
            thread_ts=thread_ts,
            metadata=message_metadata,
        )

        prompts: List[Dict[str, str]] = [
            {
                "title": "Prepare a meeting report",
                "message": """
When the user supplies an email address plus some other identifying information, follow these instructions carefully:
1. Perform extensive web research about the company the person works for and about the person themselves
2. Confirm that the research appears to match the identity of your original input.
3. Prepare a detailed "meeting prep" report based on the information you gather. 
4. Save the report as a PDF
                """,
            },
            {
                "title": "Answer questions from my knowledge base",
                "message": "When the user asks a question, retrieve info from the Personal Knowledgebase to inform your answer.",
            },
            {
                "title": "'Talk to my document'",
                "message": "Answer questions base ONLY on the uploaded document(s).",
            },
            {
                "title": "Show all the available tools and connections",
                "message": "List all of the available tools",
            },
        ]
        # if message_metadata is not None:
        #     prompts.append(
        #         {
        #             "title": "Summarize the referred channel",
        #             "message": "Can you generate a brief summary of the referred channel?",
        #         }
        #     )

        await client.assistant_threads_setSuggestedPrompts(
            channel_id=channel_id,
            thread_ts=thread_ts,
            prompts=prompts,
        )
    except Exception as e:
        logger.exception(f"Failed to handle an assistant_thread_started event: {e}", e)
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f":warning: Something went wrong! Please try again!",
        )
        