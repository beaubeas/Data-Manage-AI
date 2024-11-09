import pytest
import os

from fastapi.testclient import TestClient
import reflex as rx

from supercog.shared.services import db_connection_string
from supercog.dashboard.models import User, Agent, Tool, Credential

# Override the default
os.environ['DATABASE_NAME'] = "dashboard_test"

@pytest.fixture
def sess():
    with rx.session() as sess:
        yield sess

def test_tools(sess):
    agent = Agent(name="Test Agent", description="Test Description")
    sess.add(agent)
    sess.commit()
    sess.refresh(agent)
    tool = Tool(
        agent_id=agent.id, 
        tool_factory_id="JIRA"
    )
    sess.add(tool)
    sess.commit()
    sess.refresh(tool)

def test_credentials(sess):
    credential = Credential(
        name="My Slack Credential",
        tool_factory_id="Slack",
        scope="private",
    )
    sess.add(credential)
    sess.commit()
    sess.refresh(credential)

    user = User(gtoken_json="", gtoken_sub="", gtoken_email = "", gtoken_info_json="")
    sess.add(user)
    sess.commit()
    sess.refresh(user)

    credential.user = user
    sess.add(credential)
    sess.commit()
    sess.refresh(credential)

    cred = sess.get(Credential, credential.id)
    assert cred.id == credential.id
    assert cred.scope == credential.scope
    