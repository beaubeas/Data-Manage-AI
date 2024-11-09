import pytest
import json
import os
from pprint import pprint

from fastapi.testclient import TestClient

from supercog.shared.models import CredentialBase, ToolBase
from supercog.shared.credentials import secrets_service

from supercog.engine.main import app
from supercog.engine.db import Credential
from supercog.engine.tools.auth_rest_api_tool import AuthorizedRESTAPITool
from .test_helpers import run_context


@pytest.fixture
def tool(run_context):
    t = AuthorizedRESTAPITool()
    t.run_context = run_context
    run_context.secrets = {"GH_TOKEN": os.environ['GH_TOKEN']}
    yield t

@pytest.mark.asyncio
async def test_github(tool):
    tool.credentials = {
        "bearer_token": "$GH_TOKEN"
    }

    res = await tool.get_resource("https://api.github.com/user")
    assert "scottpersinger" in str(res)

    res = await tool.get_resource("https://api.github.com/users/scottpersinger/repos")
    assert "full_name" in str(res)
