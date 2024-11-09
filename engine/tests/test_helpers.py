import pytest
import pytest_asyncio

from httpx import ASGITransport, AsyncClient

from supercog.shared.services import config

from supercog.engine.run_context import RunContext, ContextInit
from supercog.engine.triggerable import TRIGGER_PASSKEY

from fastapi.testclient import TestClient
from supercog.engine.main import app, lifespan_manager  # Replace with the actual import for your app

def log_msg(*args, **kwargs):
    print(args, kwargs)

@pytest.fixture
def run_context():
    yield RunContext(
        ContextInit(
            tenant_id="t1", 
            user_id="u1", 
            agent_id="a1", 
             agent_name="agent 1", 
            run_id="run1",
            logs_channel="logs",
            secrets={},
            enabled_tools=["zyte_search"],
            user_email="scottp@supercog.ai",
            run_scope="private",
            doc_indexes=[],
        )
    )

@pytest_asyncio.fixture
async def async_client():
    headers={"Authorization": f"Bearer {TRIGGER_PASSKEY}"}
    async with lifespan_manager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), 
            headers=headers, 
            base_url="http://test",
        ) as client:
            yield client

