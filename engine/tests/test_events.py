import pytest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from supercog.shared.services import db_connect
from supercog.shared.apubsub import AgentInputEvent, EventRegistry, RunCreatedEvent
from supercog.engine.main import app
from supercog.engine.db import RunLog

from supercog.engine.all_tools import TOOL_FACTORIES

@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client

@pytest.fixture
def session():
    engine = db_connect("engine")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

   
def test_agent_events(client, session: Session):
    runlog = RunLog(
        run_id="run1",
        agent_id="a1",
        user_id="u1",
        type="message",
    )
    session.add(runlog)
    session.commit()
    session.refresh(runlog)
    print("Runlog: ", runlog)

    agentInput = AgentInputEvent(
        run_id="run1",
        agent_id="a1",
        user_id="u1",
        prompt="This is the prompt",
    )
    runlog.content = agentInput.json()
    session.add(runlog)
    session.commit()
    session.refresh(runlog)
    rl2 = session.get(RunLog, runlog.id)
    if rl2:
        aiEvent = EventRegistry.get_event(rl2)
        print("Agent Input: ", aiEvent)

    rce = RunCreatedEvent(agent_id="a1", run_id=str(uuid4()), user_id="u1")
    nextlog = RunLog.from_agent_event(rce, run_id=rce.run_id)
    session.add(nextlog)
    session.commit()
    session.refresh(nextlog)
    print("Next log: ", nextlog)
    print("Next log event: ", EventRegistry.get_event(nextlog))

