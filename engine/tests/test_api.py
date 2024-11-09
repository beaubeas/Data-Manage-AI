import pytest
import json
import os
from pprint import pprint

from fastapi.testclient import TestClient

from supercog.shared.models import CredentialBase, ToolBase
from supercog.shared.credentials import secrets_service

from supercog.engine.main import app
from supercog.engine.db import Credential
from supercog.engine.tools.slack_tool import SlackTool

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

def test_get_tools(client):
    response = client.get("/tool_factories")
    assert response.status_code == 200
    factories = response.json()
    assert isinstance(factories, list)
    assert "Slack" in [k["system_name"] for k in factories]
        
def test_get_models(client):
    response = client.get("/models")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_run(client):
    agent_id = "agent123"
    tools = [
        ToolBase(
            id="id1", 
            tool_factory_id="slack_connector", 
            description="Slack Connector",
            credential_id="cred1",
            agent_id=agent_id,
        ),
    ]
    agent = {
        "id": agent_id,
        "name" : "Test Agent",
        "tools": json.dumps([t.model_dump() for t in tools])
    }
    response = client.post("/agents", json=agent)
    assert response.status_code == 200

    run_data = {
        "agent_id": "this agent doesnt exist",
        "tenant_id": "t1",
        "user_id": "u1",
        "input": "Test Input",
        "input_mode": "text",
        "turn_limit": 5,
        "timeout": 60,
        "result_channel": "test_results",
        "logs_channel": "test_logs",
    }
    response = client.post("/runs", json=run_data)
    assert response.status_code == 404 #agent does not exist

    run_data["agent_id"] = agent['id']
    response = client.post("/runs", json=run_data)
    assert response.status_code == 200
    result = response.json()
    assert result.get("id") is not None
    # Store the run_id for use in further tests if needed
    global run_id
    run_id = result["id"]

def test_get_run(client):
    global run_id
    # Ensure you have created a run before this test
    response = client.get(f"/runs/{run_id}")
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == run_id

def test_update_run(client):
    global run_id
    updated_run_data = {
        "status": "running"
    }
    response = client.patch(f"/runs/{run_id}", json=updated_run_data)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "running"

def test_cancel_run(client):
    global run_id
    response = client.put(f"/runs/{run_id}/cancel")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "cancelled"

# The following test shows how to use Credentials. You post a full
# Credential record with plaintext auth config parameters. What comes
# back is a saved Credential record, but with auth parameters redacted.
# Someone needs to use 'retrieve_secrets' on the Credential to retrieve
# the plaintext secrets from the underlying SecretsService.
# The net result is:
#
#   You can store and lookup Credential objects for Tenant+User.
#   Those objects will store their secrets safely in the underlying
#   secret store.

def test_credentials(client):
    tenant_id = "t1"
    user_id = "u1"
    cred = "jira_token"
    value = "password"

    credential = CredentialBase(
        name="Jira credential",
        tenant_id=tenant_id,
        user_id=user_id,
        tool_factory_id="jira_connector",
        secrets_json=json.dumps({cred: value})
    )
    response = client.post(f"/tenant/{tenant_id}/credentials",
                           json=credential.model_dump(exclude={'id'}))
    assert response.status_code == 200
    credential = Credential.model_validate(response.json())
    assert credential.id is not None

    # secret value should have been redacted
    assert value not in json.dumps(response.json())

    credential.name = "Updated JIRA cred"
    response = client.patch(f"/tenant/{tenant_id}/credentials/{credential.id}",
                            json=credential.model_dump(exclude={'id'}))
    assert response.status_code == 200

    response = client.get(f"/tenant/{tenant_id}/credentials/{credential.id}?user_id=foo")
    # should fail because we didn't indicate the user_id
    assert response.status_code == 404

    response = client.get(f"/tenant/{tenant_id}/credentials/{credential.id}?user_id={user_id}")
    cred2 = Credential.model_validate(response.json())
    cred2.retrieve_secrets()
    assert value in (cred2.secrets_json or "")

    response = client.delete(f"/tenant/{tenant_id}/credentials/{cred2.id}?user_id={user_id}")
    assert response.status_code == 200

def test_use_tool_factory(client):
    # This shows how the dashboard will retrieve tool factories, and then post
    # Credentials that include the auth strategy config as specified by the tool.
    # The secrets are redacted in the Credential but retrievable from the secrets store.
    factories = client.get("/tool_factories").json()
    tool = SlackTool()

    for strategy in tool.auth_config.keys():
        if strategy == "strategy_token":
            secrets = {}
            for key in tool.auth_config[strategy]:
                secrets[key] = "shhhh..." + key

    tenant_id = "t1"
    user_id = "u1"

    credential = CredentialBase(
        name="Slack credential",
        tenant_id=tenant_id,
        user_id=user_id,
        tool_factory_id=tool.id,
        secrets_json=json.dumps(secrets)
    )
    response = client.post(f"/tenant/{tenant_id}/credentials",
                           json=credential.model_dump(exclude={'id'}))
    assert response.status_code == 200
    credential = Credential.model_validate(response.json())

    # Now verify that the underlying secrets were stored in the secret store
    for key, val in secrets.items():
        secret = secrets_service.get_credential(
            tenant_id=tenant_id,
            user_id=user_id,
            credential_id=credential._secret_key(key),
        )
        assert secret == val, f"Stored {secret} != {val} for {key}"

