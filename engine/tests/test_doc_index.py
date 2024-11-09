import pytest
from sqlmodel import Session, SQLModel, create_engine
from uuid import UUID
from typing import List
import json

from supercog.shared.services import db_connect
from supercog.shared.models import DocIndexReference, AgentBase

# Import your models here
from supercog.engine.db import DocSourceConfig, DocIndex, Agent
from supercog.engine.all_tools import LocalFolderDocSource

@pytest.fixture(scope="module")
def engine():
    return db_connect("engine")

@pytest.fixture(scope="module")
def session(engine):
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

@pytest.fixture
def doc_source_factory_id():
    lfds = LocalFolderDocSource()
    return lfds.id

def test_doc_source_config_relationships(session, doc_source_factory_id):
    # Create a DocIndex
    doc_index = DocIndex(name="A big index", tenant_id="t1", user_id="u1")
    session.add(doc_index)
    session.commit()

    # Create a DocSourceConfig
    config = DocSourceConfig(
        doc_source_factory_id=doc_source_factory_id,
        doc_index_id=doc_index.id,
        folder_ids=["folder1", "folder2"],
        file_patterns=["*.txt", "*.pdf"]
    )
    session.add(config)
    session.commit()

    # Test relationships
    assert config.doc_index == doc_index
    assert config in doc_index.source_configs
    assert isinstance(config.folder_ids, List)
    assert isinstance(config.file_patterns, List)

def test_doc_source_config_methods(session, doc_source_factory_id):
    doc_index = DocIndex(name="Test Index", tenant_id="t1", user_id="u1")
    session.add(doc_index)
    session.commit()

    config = DocSourceConfig(
        doc_source_factory_id=doc_source_factory_id,
        doc_index_id=doc_index.id,
        provider_data={"key1": "value1"}
    )
    session.add(config)
    session.commit()

    # Test inherited methods if DocSourceConfig still inherits any base functionality
    assert config.provider_data == {"key1": "value1"}

def test_doc_index_relationships(session, doc_source_factory_id):
    doc_index = DocIndex(name="A big index", tenant_id="t1", user_id="u1")
    session.add(doc_index)
    session.commit()

    # Create multiple DocSourceConfigs
    configs = [
        DocSourceConfig(doc_index_id=doc_index.id, doc_source_factory_id=doc_source_factory_id),
        DocSourceConfig(doc_index_id=doc_index.id, doc_source_factory_id=doc_source_factory_id)
    ]
    session.add_all(configs)
    session.commit()

    # Test relationships
    assert len(doc_index.source_configs) == 2
    for config in configs:
        assert config in doc_index.source_configs
        assert isinstance(config.folder_ids, List)
        assert isinstance(config.file_patterns, List)

def test_agent_indexes(session):
    existing = session.get(Agent, "agent1")
    if existing:
        session.delete(existing)
        session.commit()

    agent = Agent(
        id="agent1",
        name="Test Agent",
        enabled_indexes=json.dumps([DocIndexReference(index_id="idx1", name="Personal Index").model_dump()])
    )
    session.add(agent)
    session.commit()
    session.refresh(agent)

    assert agent.get_enabled_indexes()[0].index_id == "idx1"
    assert agent.get_enabled_indexes()[0].name == "Personal Index"

    agent2 = Agent.model_validate({"id": "", "name": "agent2"})

    agent_base = AgentBase(**agent.model_dump())

