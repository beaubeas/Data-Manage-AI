import pytest
import os

from supercog.engine.tools.slack_tool import SlackTool
from .test_helpers import run_context, config

@pytest.fixture
def tool(run_context):
    t = SlackTool()
    t.run_context = run_context
    # Won't fail if Env vars aren't set, but the tests will fail
    run_context.secrets = {
        "SLACK_BOT_TOKEN": config.get_global('SLACK_BOT_TOKEN', required=False),
        "SLACK_SIGNING_SECRET": config.get_global('SLACK_SIGNING_SECRET', required=False),
    }
    yield t

@pytest.mark.asyncio
async def test_send_slack_message(tool):
    # Make sure to use a channel that exists in your Slack workspace
    result = await tool.send_slack_message("random", "Hello, this is an integration test!")
    assert result["status"] == "success"
    assert result["message"] == "Message sent."

@pytest.mark.asyncio
async def test_send_slack_message_channel_not_found(tool):
    result = await tool.send_slack_message("non_existent_channel", "This should fail")
    assert result["status"] == "error"
    assert "not found" in result["message"]

@pytest.mark.asyncio
async def test_list_channels(tool):
    channels = tool.list_channels()
    assert isinstance(channels, list)
    assert len(channels) > 0
    assert all(isinstance(channel, dict) for channel in channels)
    assert all("name" in channel for channel in channels)

@pytest.mark.asyncio
async def test_fetch_recent_messages(tool):
    # Make sure to use a channel that exists in your Slack workspace and has messages
    messages = tool.fetch_recent_messages("general", count=5)
    assert isinstance(messages, list)
    assert len(messages) <= 5  # It might be less if the channel doesn't have 5 messages
    assert all(isinstance(message, dict) for message in messages)
    assert all("text" in message for message in messages)

@pytest.mark.asyncio
async def test_send_slack_message_with_audio(tool):
    # Make sure to use a channel that exists in your Slack workspace
    audio_url = "https://supercog-files-dev.s3.amazonaws.com/9d73a275-aad6-494c-ae25-a27726d648d8/18c137ae-8e5b-4de4-a0ef-7f38f89dd61b/audio/speech_nova_20240929_230801.mp3?AWSAccessKeyId=AKIAQS4JFK7EKYB4RDWC&Signature=1xXfstBiJ3OBVQyyZvf0DLttDTQ%3D&Expires=1727752082"
    result = await tool.send_slack_message("random", "Enjoy this audio", audio_link=audio_url)
    assert result["status"] == "success"
    assert result["message"] == "Message sent."

