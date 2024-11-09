import asyncio
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from supercog.engine.main import app
from supercog.shared.apubsub import AssetCreatedEvent, AssetTypeEnum, pubsub, AgentEvent, EventRegistry
from supercog.shared.models import ToolBase, RunLogBase

from .test_helpers import async_client

@pytest.mark.asyncio
async def test_post_agent_and_retrieve_asset(async_client):
    # Mock data for creating an agent
    agent_data = {
        "id" : "a1",
        "name": "Test Agent",
        "description": "A test agent",
        "tenant_id": "test_tenant",
        "user_id": "test_user",
        #"tools": [ ToolBase(id="t1", tool_factory_id="duckdb_tool", agent_id="a1").model_dump_json() ]
    }

    response = await async_client.post("/agents", json=agent_data)
    assert response.status_code == 200


    agent_done = False
    assets = []

    async def receive_message(event_type: str, event: dict):
        global agent_done
        log = RunLogBase.model_validate(event)
        agevent: AgentEvent = EventRegistry.get_event(log)
        if isinstance(agevent, AssetCreatedEvent):
            assets.append(agevent.asset_id)

        print("Received event: ", event)
        if event_type == "end":
            agent_done = True

    await pubsub.subscribe("logs*", receive_message)

    # post a Run
    run_data = {
        "tenant_id": "test_tenant",
        "user_id": "test_user",
        "agent_id": "a1",
        "input": "create some fake csv data and make a dataframe from it",
        "logs_channel": "logs",
    }
    response = await async_client.post("/runs", json=run_data, params={"user_email": "scottp@supercog.ai"})
    assert response.status_code == 200

    while not agent_done:
        await asyncio.sleep(0.1)

    # Verify that we can retrieve the asset    
    assert len(assets) > 0
    asset_id = assets[0]
    response = await async_client.get(f"/asset/{agent_data['tenant_id']}/{agent_data['user_id']}/{asset_id}")
    assert response.status_code == 200

    #assert response.content == asset_content
    #assert response.headers["content-type"] == asset_content_type

