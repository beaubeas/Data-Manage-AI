import pytest
import json
import os
from pprint import pprint

from fastapi.testclient import TestClient

from supercog.shared.models import CredentialBase, ToolBase
from supercog.shared.credentials import secrets_service

from supercog.engine.main import app
from supercog.engine.db import Credential
from supercog.engine.tools.rest_tool_v2 import RESTAPIToolV2

@pytest.fixture
def tool():
    return RESTAPIToolV2()

@pytest.mark.asyncio
async def test_quickchart(tool):
    request = tool.prepare_request_variable("https://api.github.com", auth_type="none")
    print(request)

    res = await tool.get_resource("/repos/supercog-ai/community/stargazers", request_variable=request)
    print(res)
