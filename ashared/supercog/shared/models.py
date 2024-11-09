from click import Option
from pydantic import BaseModel
from sqlmodel import Field, Column, SQLModel, ARRAY, String, Integer
from uuid import UUID, uuid4
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import json
import re

from supercog.shared.utils import parse_markdown, NodeTypes

def get_uuid4():
    return str(uuid4())

class ToolBase(SQLModel):
    id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_factory_id: str
    description: Optional[str] = None
    agent_id: str
    credential_id: Optional[str] = None

# "enabled_indexes" on the Agent will be a JSON serialized array of these objects
class DocIndexReference(BaseModel):
    index_id: str
    name: str
    
    def json(self) -> str:
        return json.dumps({"index_id": self.index_id, "name": self.name})
    
    @classmethod
    def from_json(cls, json_str: str) -> "DocIndexReference":
        data = json.loads(json_str)
        return cls(index_id=data["index_id"], name=data["name"])


PERSONAL_INDEX_NAME = "personal"

# All Agents (Dashboard persisted model and Engine json-seralized version)
# share these base attributes. The different side versions differ on the 'tools'
# attribute being either a relation or a nested JSON blob.
class AgentCore(SQLModel):
    id: str
    name: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = ""
    input_mode: str = "fit"
    trigger: str = "Chat box"
    trigger_arg: Optional[str] = None
    welcome_message: Optional[str] = None
    agent_slug: Optional[str] = None
    temperature: Optional[float] = 0.0
    max_agent_time: Optional[int] = 600
    memories_json: Optional[str] = "" # JSON Array of memories [{ "memory" : "Before attempting an INSERT operation check DB.", "ts": "1718287315", "enabled": "True" }]
    implicit_tools: Optional[str] = None # comma separated list of tool ids
    enabled_indexes: Optional[str] = ""
    max_chat_length: int|None = None
    state: Optional[str] = None
    
    def has_database_tool(self):
        # FIXME: Re-implement
        return False

    def add_fact_as_memory(self, fact: str) -> list[dict]:
        new_memory = {
            "memory": fact,
            "enabled": True,
            "ts": int(datetime.now().timestamp())
        }
        if self.memories_json:
            mems = json.loads(self.memories_json)
        else:
            mems = []
        mems.append(new_memory)
        self.memories_json = json.dumps(mems)
        return mems

    def get_enabled_indexes(self) -> List[DocIndexReference]:
        refs: list = json.loads(self.enabled_indexes or "[]")
        return [DocIndexReference(**d) for d in refs]

    def enable_rag_index(self, name: str, index_id: str|None=None):
        refs = self.get_enabled_indexes()
        refs.append(DocIndexReference(index_id=index_id or "", name=name))
        try:
            self.enabled_indexes = json.dumps([r.model_dump() for r in refs])
        except AttributeError:
            self.enabled_indexes = json.dumps([r.dict() for r in refs])

class AgentBase(AgentCore):
    # Tools are a structured object, stored in the dashboard. I don't
    # want to have to store them separately so we are just serializing
    # them as JSON even though that is gross.
    tools: Optional[str] = None
    input_mode: str = "fit"
    trigger: str = "Chat box"
    welcome_message: Optional[str] = None

    @property
    def tool_list(self) -> list[ToolBase]:
        if self.tools:
            res = json.loads(self.tools)
            tools = []
            for t in res:
                try:
                    tools.append(ToolBase(**t))
                except Exception as e:
                    print(f"Error creating tool: {t}. Error: {e}")
            return tools
        else:
            return []
    
class RunBase(SQLModel):
    tenant_id: str
    user_id: str        # the user running the agent
    agent_id: str

class RunCreate(RunBase):
    id: Optional[UUID] = None
    input: Optional[str] = None
    input_mode: str = "truncate"
    turn_limit: int = 5
    timeout: int = 2000
    result_channel: Optional[str] = None
    logs_channel: Optional[str] = None
    conversation_id: Optional[str] = None
    scope: Optional[str] = "private"

class RunUpdate(RunBase):
    model: Optional[str] = None
    tools: List[dict] = []
    status: Optional[str] = None

# Agent events are modeled by the 'AgentEvent' class hierarchy. For persistent storage
# we wrap those events in RunLog objects.
#
# We serialize AgentEvents inside each RunLogBase object (in the 'content' field).
# To 'wrap' an agent event you can use RunLogBase.attach_event(agent_event). To get the
# agent event back, use `EventRegistry.get_event(run_log)` from supercog.shared.apubsub.
class RunLogBase(SQLModel):
    id: Optional[int] = None
    run_id: str
    lc_run_id: str|None = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None # The user who ran the agent.
    scope: Optional[str] = None # Shared if the agent as a Shared agent when it ran
    created_at: Optional[datetime] = None
    content: str = ""
    type: str
    role: str = "agent" # one of 'user' or 'agent'
    version: int = Field(default=2, sa_column=Column(Integer, server_default="2"))

# You get this back when querying existing runs. We don't use this
# model for anything but describing the output from Engine (it uses
# a separate SQLModel for persistence internally).
class RunOutput(RunBase):
    id: Optional[UUID]
    input: Optional[str] = None
    status: str
    created_at: datetime
    run_log: Optional[RunLogBase] = None

class CredentialBase(SQLModel):
    id: Optional[str] = None
    # We can default assign the name from the ToolFactory system name
    name: str

    user_id: str = Field(nullable=True, default=None)
    # Eventually migrate this to a real foreign key to the Tenant model
    tenant_id: str = Field(default="tenant1")

    # ID of the ToolFactory (exported by Engine service).
    tool_factory_id: str
    scope: str = "shared" # one of 'private' or 'shared'

    #The secrets inside the credential. Specific to the system type.
    # Stored as a JSON blob.
    secrets_json: Optional[str] = None 

class DocIndexBase(SQLModel):
    id: Optional[str] = None
    name: str
    scope: str = "private"
    index_type: str = "vector_store"
    tenant_id: str
    user_id: str

    source_ids: str = "" # janky comma separated list of DocSource ids
    folder_ids: str = "" # comma separated list of folder ids
    file_patterns: str = "" # comma separated list of file patterns

    @staticmethod
    def calc_user_personal_index_id(user_id: str, tenant_id: str) -> str:
        return f"personal_{user_id[0:13]}_{tenant_id[0:13]}"

class DocSourceConfigCreate(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = ""
    doc_index_id: str
    doc_source_factory_id: str
    provider_data: Optional[dict] = {}
    folder_ids: Optional[List[str]] = []
    file_patterns: Optional[List[str]] = []

    class Config:
        from_attributes = True
        
class Datum(SQLModel):
    category: str
    name: str
    mime_type: str
    url: Optional[str]=None
    is_directory: Optional[bool]=False
    