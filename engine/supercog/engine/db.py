from hmac import new
import json
from contextlib import contextmanager
from fastapi import FastAPI
from sqlalchemy import Engine
from sqlmodel import SQLModel, Session, Field, select, Relationship
from sqlalchemy.orm import object_session
from sqlalchemy import Column, Integer, VARCHAR
from pydantic import BaseModel, computed_field, Json
from uuid import UUID, uuid4
from typing import Optional, Callable, AsyncIterator, List
from datetime import datetime
from sqlalchemy import JSON, Column


from fastapi_lifespan_manager import LifespanManager, State

lifespan_manager = LifespanManager()

from supercog.shared.services import config, db_connect
from supercog.shared.models import get_uuid4
from supercog.shared.credentials import secrets_service, reset_secrets_connection
from supercog.shared.logging import logger
from supercog.shared.apubsub import AgentEvent
from supercog.shared.models import (
    AgentBase, 
    RunCreate, 
    CredentialBase, 
    get_uuid4, 
    RunLogBase, 
    DocIndexBase, 
    ToolBase,
    DocIndexReference,
)

SERVICE_NAME = "engine"
engine: Engine =  None


class EmailMsgsProcessed(SQLModel, table=True):
    #    uid:  Optional[int] = Field(default=None, primary_key=True)          # the uid of a message
    uid: Optional[str] = Field(default=None, primary_key=True)  
    from_field: str           # save some info in case multiple mailboxes or servers where UIDs might overlap..
    to_field: str             #
    subject_field: str        #
    processed:  Optional[int] #
    agent_id: str             # Save the agent as another agen may want to see this message.

class RunLog(RunLogBase, table=True):
    __tablename__ = "run_logs"
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    # Event scheme versioning

    @classmethod
    def from_agent_event(cls, agent_event: AgentEvent, run_id: str|None=None, role: str|None="agent") -> "RunLog":
        return cls(
            agent_id=agent_event.agent_id, 
            run_id=agent_event.run_id or run_id or "",
            user_id=agent_event.user_id, 
            type=agent_event.type or "", 
            content=agent_event.json(),
            role=role or "agent",
        )

    def __str__(self) -> str:
        return f"[{self.type.upper()}] {self.content} run: {self.run_id}"
    
class Run(RunCreate, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)
    status: str = "pending"
    chatengine_id: Optional[UUID] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_interaction: datetime = Field(default_factory=datetime.utcnow)
    model: str = Field(default="", sa_column=Column(VARCHAR, server_default=""))

    # Accounting for the tokens used by this Run so far. Should total all TOKEN_USAGE type RunLog events.
    input_tokens: int = Field(default=0, sa_column=Column(Integer, server_default="0"))
    output_tokens: int = Field(default=0, sa_column=Column(Integer, server_default="0"))

    # We  let each Run specify a different set of tools, but initialize it from the Agent at start
    tools: List[dict] = Field(sa_column=Column(JSON), default=[])

    agent_id: str = Field(foreign_key="agents.id")
    # from the RunLog table
    @computed_field(return_type=Optional[RunLog])
    @property
    def run_log(self) -> Optional[RunLog]:
        if session := object_session(self):
            return (
                session.exec(
                    select(RunLog)
                    .where(RunLog.run_id == str(self.id))
                    .order_by(RunLog.created_at.asc())
                    .limit(1)
                ).first()
            )

    def update_tools(self, new_tools: list[ToolBase]):
        self.tools = [t.model_dump() for t in new_tools]

class Agent(AgentBase, table=True):
    """
        This is our copy of the Agent saved inside the Engine. This mostly mirrors
        the "Agent" model that the Dashboard stores, and in fact we expect the
        Dashboard to always provide the "id" - we will never create our own Agents
        with separate IDs. 

        One notable difference is that our "tools" are just a JSON blob rather
        than the separate models that the Dashboard keeps.

        We also keep enabled_indexes as a JSON blob. The only real reason to do this
        (versus just using a normal db relationship) is so that we can serialize an 
        agent on the Dashboard side into a singular file. If we only kept table IDs
        then we couldn't really export/import an agent and preserve index references.
    """
    __tablename__ = "agents"

    id: str = Field(primary_key=True)

    def get_agent_email_address(self) -> str:
        return f"{self.agent_slug}@mail.supercog.ai"

# CredentialBase is in shared so we can use it as our service contract
class Credential(CredentialBase, table=True):
    __tablename__ = "credentials"
    id: Optional[str] = Field(default_factory=get_uuid4, primary_key=True)

    def _secret_key(self, key):
        return ":".join([self.id, key])
    
    def stuff_secrets(self, payload_json: Optional[str]):
        if self.id is None:
            raise RuntimeError("Stuff secrets after you have saved the Credential")
        if payload_json:
            payload = json.loads(payload_json)
            redacted = {}
            for key, secret in payload.items():
                redacted[key] = "*" * len(secret)
                if not isinstance(secret, str):
                    secret = json.dumps(secret)
                secrets_service.set_credential(
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    credential_id=self._secret_key(key),
                    secret=secret,
                )
            self.secrets_json = json.dumps(redacted)

    def secret_keys(self) -> list[str]:
        return json.loads(self.secrets_json or "{}").keys()

    def delete_secrets(self):
        for secret in self.secret_keys():
            secrets_service.delete_credential(
                self.tenant_id, 
                self.user_id, 
                self._secret_key(secret)
            )            

    def retrieve_secrets(self) -> dict:
        retrieved = {
            key: secrets_service.get_credential(
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                credential_id=self._secret_key(key)
            ) for key in self.secret_keys()
        }
        self.secrets_json = json.dumps(retrieved)
        return retrieved

    @classmethod
    def _export_cred(cls, credential_id: str|None=None, name: str|None=None) -> tuple[dict, "Credential"]:
        global engine
        if engine is None:
            engine = db_connect(SERVICE_NAME)     
        with session_context() as sess:
            if name:
                cred = sess.exec(select(Credential).where(Credential.name == name)).first()
            else:
                cred = sess.get(Credential, credential_id)
            if cred:
                return cred.retrieve_secrets(), cred
            else:
                print("Credential not found")
        return {}, None

class CompressedHistoryMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    compressed_id: str = Field(index=True)  # The UUID used for retrieval
    original_content: str  # The full, uncompressed message content
    compressed_content: str  # The compressed version of the message
    message_type: str  # To distinguish between HumanMessage and AIMessage
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    

   
    # Metadata fields
    tokens_original: int  # Number of tokens in the original message
    tokens_compressed: int  # Number of tokens in the compressed message
    compression_ratio: float  # Calculated as tokens_compressed / tokens_original
    
    # If you're using a specific compression algorithm or model version, you might want to track that
    compression_algorithm: str = "gpt-4o-mini"  # Default to the model you're currently using

class DocSourceConfig(SQLModel, table=True):
    __tablename__ = "doc_source_configs"
    
    id: Optional[str] = Field(default_factory=get_uuid4, primary_key=True)
    name: Optional[str] = Field(default="")
    #doc_source_id: str = Field(foreign_key="doc_sources.id")
    doc_source_factory_id: Optional[str] = Field(default="")
    doc_index_id: str = Field(foreign_key="doc_indexes.id")
    folder_ids: List[str] = Field(sa_column=Column(JSON), default=[])
    file_patterns: List[str] = Field(sa_column=Column(JSON), default=[])
    provider_data: dict = Field(sa_column=Column(JSON), default={})

    #doc_source: "DocSource" = Relationship(back_populates="configs")
    doc_index: "DocIndex" = Relationship(back_populates="source_configs")

# # SQLAlchemy really didn't like me trying to subclass SQLModel twice. So instead
# # we just inherit from CredentialBase like Credential, and then copy methods to "duck type".
# class DocSource(CredentialBase, table=True):
#     __tablename__ = "doc_sources"
#     id: Optional[str] = Field(default_factory=get_uuid4, primary_key=True)
#     #configs: List["DocSourceConfig"] = [] # = Relationship(back_populates="doc_source")

#for m in ['_secret_key', 'stuff_secrets', 'secret_keys', 'delete_secrets', 'retrieve_secrets']:
#    setattr(DocSource, m, getattr(Credential, m))

class DocIndex(DocIndexBase, table=True):
    __tablename__ = "doc_indexes"
    id: Optional[str] = Field(default_factory=get_uuid4, primary_key=True)
    docs: list["IndexedDoc"] = Relationship(sa_relationship_kwargs={"lazy":"selectin"}, cascade_delete=True)
    source_description: Optional[str] = ""
    status: Optional[str] = Field(default="new")
    error_message: Optional[str] = Field(default="new")
    source_configs: List[DocSourceConfig] = Relationship(
        back_populates="doc_index",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"}
    )

# @cihan - not sure if we want to use this IndexedDoc model or if LlamaIndex has
# their own model we should use.
class IndexedDoc(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    index_id: str = Field(foreign_key="doc_indexes.id", ondelete="CASCADE")
    doc_id: str = ""
    name: str = ""

### END MODELS


@lifespan_manager.add
async def lifespan(app: FastAPI) -> AsyncIterator[State]:
    global engine #critical!
    print("ENGINE LIFES SPAN. RESET CREDS and ENGINE db connections")
    reset_secrets_connection() # make sure SecretsService re-connects to its db
    if engine is not None:
        engine.dispose()
    engine = db_connect(SERVICE_NAME)

    #@event.listens_for(engine, 'connect')
    #def receive_connect(dbapi_connection, connection_record):
    #    logger.info('############## !!!!!!!!!!! New database connection created')


    yield {"engine": engine}
    engine.dispose()

def reset_db_connections():
    global engine #critical!
    reset_secrets_connection() # make sure SecretsService re-connects to its db
    if engine is not None:
        engine.dispose()
    engine = db_connect(SERVICE_NAME)





def get_session():
    with Session(engine) as session:
        yield session

def get_noexpiry_session():
    with Session(engine, expire_on_commit=False) as session:
        yield session

@contextmanager
def session_context():
    with Session(engine) as session:
        yield session

