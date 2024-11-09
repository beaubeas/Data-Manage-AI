import pytest
import json
import os
from pprint import pprint

from fastapi.testclient import TestClient

from supercog.shared.models import CredentialBase, ToolBase
from supercog.shared.credentials import secrets_service

from supercog.engine.main import app
from supercog.engine.db import Credential
from supercog.engine.tools.scaleserp_browser import ScaleSerpBrowserTool

@pytest.fixture
def tool():
    return ScaleSerpBrowserTool()

@pytest.mark.asyncio
async def test_web_browser(tool):
    res = await tool.browse_web_tool(page_url="tatari.tv")
    print("Tatari page results: ", res)

    res = await tool.browse_web_tool(search="tatari")
    print("Search results: \n", res)
