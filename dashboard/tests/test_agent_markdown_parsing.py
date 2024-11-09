import pytest
import os

from supercog.dashboard.import_export import parse_markdown, import_agent_template_from_markdown, NodeTypes
from supercog.dashboard.models import Tool

@pytest.fixture
def agent_markdown() -> str:
    return """
# Weather Agent

This is our demo Weather agent, meant to demonstrate Supercog agents in the most minimal
way.

## name: Weather Demo
## model: gpt-4o-mini
## image: https://open-access-dev-bucket.s3.amazonaws.com/supercog_square_logo.png
## max_chat_length: 2

## welcome:
This is demonstration of a basic Supercog agent. This agent can delivery weather reports.
It uses two tools: the Weather tool and the Image Generation tool.

Try it out by asking about the weather in your location.

## tools:
1. Weather
2. Image Generator
3. RAG Tool|SC Docs Index|embedding_index_name=sc_docs

## system instructions:
When the user asks for a weather report, get the weather data and then generate
an image which matches the weather report.
"""

def test_parse_markdown(agent_markdown):
    nodes = parse_markdown(agent_markdown)
    print("\n".join([str(n) for n in nodes]))
    assert any([n.tag == NodeTypes.HEADING1 for n in nodes])
    assert any([n.tag == NodeTypes.HEADING2 for n in nodes])
    assert any([n.tag == NodeTypes.PARAGRAPH for n in nodes])
    assert any([n.tag == NodeTypes.NUMBERED_ITEM for n in nodes])


def test_import_agent_from_markdown(agent_markdown):
    tools: list[Tool]
    template = import_agent_template_from_markdown(agent_markdown)

    if template:
        assert template.name == "Weather Demo"
        assert template.model == "gpt-4o-mini"
        assert template.avatar_url == "https://open-access-dev-bucket.s3.amazonaws.com/supercog_square_logo.png"
        assert "When the user asks for a weather report" in (template.system_prompt or "")
        assert template.max_chat_length == 2

    assert len(tools) == 3
    assert "Weather" in tools
    assert "Image Generator" in tools

def test_salesforce_agent_import():
    path = os.path.join(os.path.dirname(__file__), "../system_agents/load_leads_agent.md")
    content = open(path).read()
    nodes = parse_markdown(content)
    print("\n".join([str(n) for n in nodes]))

    agent = import_agent_template_from_markdown(content)
    assert "3. read 10 records" in agent.system_prompt
