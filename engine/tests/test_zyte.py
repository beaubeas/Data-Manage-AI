import pytest
import json
import os
from pprint import pprint

from fastapi.testclient import TestClient

from supercog.shared.credentials import secrets_service
from supercog.engine.tools.zyte import ZyteSearchTool

from .test_helpers import run_context

@pytest.fixture
def tool(run_context):
    tool = ZyteSearchTool()
    tool.run_context=run_context
    yield tool


@pytest.mark.asyncio
async def test_screenshot(tool):
    res = await tool.get_page_screenshot("https://tatari.tv")
    print("Tatari screenshot: ", res)

@pytest.mark.asyncio
async def test_content(tool):
    res = await tool.scrape_web_page("https://yahoo.com")
    assert "Yahoo" in res
