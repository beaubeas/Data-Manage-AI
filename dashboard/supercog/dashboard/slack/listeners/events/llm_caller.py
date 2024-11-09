import os
import re
from typing import List, Dict, Generator

import openai

DEFAULT_SYSTEM_CONTENT = """
You're an assistant in a Slack workspace.
Users in the workspace will ask you to help them write something or to think better about a specific topic.
You'll respond to those questions in a professional way.
When you include markdown text, convert them to Slack compatible ones.
When a prompt has Slack's special syntax like <@USER_ID> or <#CHANNEL_ID>, you must keep them as-is in your response.
"""

async def call_llm(messages_in_thread: List[Dict[str, str]], system_content: str = DEFAULT_SYSTEM_CONTENT) -> Generator[str, None, None]:
    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages = [{"role": "system", "content": system_content}]
    messages.extend(messages_in_thread)
    
    stream = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0,
        max_tokens=16384,
        stream=True,
    )
    
    batch_size = 100
    accumulated_content = ""
    for chunk in stream:
        if chunk.choices[0].delta.content is not None:
            accumulated_content += chunk.choices[0].delta.content
            if len(accumulated_content) >= batch_size:
                yield markdown_to_slack(accumulated_content)
                accumulated_content = ""
    
    # Yield any remaining content
    if accumulated_content:
        yield markdown_to_slack(accumulated_content)
        

async def single_call_llm(messages_in_thread: List[Dict[str, str]], system_content: str = DEFAULT_SYSTEM_CONTENT) -> str:
    openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    messages = [{"role": "system", "content": system_content}]
    messages.extend(messages_in_thread)
    
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        n=1,
        messages=messages,
        temperature=0,
        max_tokens=16384,
    )

    return markdown_to_slack(response.choices[0].message.content or "")

# Conversion from OpenAI markdown to Slack mrkdwn
# See also: https://api.slack.com/reference/surfaces/formatting#basics
def markdown_to_slack(content: str) -> str:
    # Split the input string into parts based on code blocks and inline code
    parts = re.split(r"(?s)(```.+?```|`[^`\n]+?`)", content)

    # Apply the bold, italic, and strikethrough formatting to text not within code
    result = ""
    for part in parts:
        if part.startswith("```") or part.startswith("`"):
            result += part
        else:
            for o, n in [
                (
                    r"\*\*\*(?!\s)([^\*\n]+?)(?<!\s)\*\*\*",
                    r"_*\1*_",
                ),  # ***bold italic*** to *_bold italic_*
                (
                    r"(?<![\*_])\*(?!\s)([^\*\n]+?)(?<!\s)\*(?![\*_])",
                    r"_\1_",
                ),  # *italic* to _italic_
                (r"\*\*(?!\s)([^\*\n]+?)(?<!\s)\*\*", r"*\1*"),  # **bold** to *bold*
                (r"__(?!\s)([^_\n]+?)(?<!\s)__", r"*\1*"),  # __bold__ to *bold*
                (r"~~(?!\s)([^~\n]+?)(?<!\s)~~", r"~\1~"),  # ~~strike~~ to ~strike~
                (r"\!?\[([^\]]+)\]\(([^\)]+)\)", r"<\2|\1>"), # [text](link) to <link|text>
            ]:
                part = re.sub(o, n, part)
            result += part
    return result
