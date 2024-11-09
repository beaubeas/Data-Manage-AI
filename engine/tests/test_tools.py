import pytest
import dotenv
import random

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel

from supercog.shared.services import db_connect
from supercog.engine.main import app

from supercog.engine.all_tools import TOOL_FACTORIES
from supercog.engine.run_context import RunContext

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

from .test_helpers import run_context
    
def test_basic_tool_factory(run_context: RunContext):
    print(TOOL_FACTORIES)

    for x in range(3):
        tool = random.choice(TOOL_FACTORIES)
        print(tool)
        tool_fact = tool.__class__()
        tool_fact.run_context = run_context
        print(tool.get_tools())
        print("------------------\n")


