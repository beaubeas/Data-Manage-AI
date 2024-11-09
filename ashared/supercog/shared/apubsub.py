from enum import StrEnum, IntEnum
import asyncio
import json
import redis.asyncio as redis
from typing import AsyncIterator, Optional, Any, Callable, Dict, Type, Literal, TypeVar, Generic

from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder

from supercog.shared.services import config
from supercog.shared.models import RunLogBase

AGENT_EVENTS_CHANNEL = "agent_events"
REDIS_HOST = "localhost"
REDIS_PORT = 6379

SubscribeCallback = Callable[[str, dict], Any]

T = TypeVar('T', bound='AgentEvent')

class EventRegistry(Generic[T]):
    _registry: Dict[str, Type['AgentEvent']] = {}

    @classmethod
    def register(cls, event_class: Type['AgentEvent']):
        if hasattr(event_class, 'model_fields'):
            fattr = 'model_fields' # pydantic 2.0
        else:
            fattr = '__fields__'   # pydantic 1.x
        cls._registry[str(getattr(event_class, fattr)['type'].default)] = event_class
        return event_class

    @classmethod
    def get(cls, event_type: str) -> Type['AgentEvent']:
        return cls._registry.get(event_type, AgentEvent)

    @classmethod
    def deserialize_event(cls, json_str: str) -> T:
        data = json.loads(json_str)
        event_type = data.get('type')
        event_class = EventRegistry.get(event_type)
        return event_class(**data)
    
    @classmethod
    def get_event(cls, runlog: RunLogBase) -> Optional[T]:
        #print("REGISTRY, deserializing '", runlog.content, "'")
        try:
            return cls.deserialize_event(runlog.content)
        except Exception as e:
            print("Error deserializing event: ", e)
            return None

    @classmethod
    def reconstruct_event(cls, agevent_dict: dict) -> Optional[T]:
        event_type = agevent_dict.get('type')
        event_class = EventRegistry.get(event_type)
        return event_class(**agevent_dict)

class AgentLogEventTypes(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    END = "end"
    TOOL = "tool" # A tool invocation by the agent
    ERROR = "error"
    TOOL_LOG = "tool_log" # Need to migrate from 'subagent_output'
    TOOL_RESULT = "tool_result"
    TOOL_END = "tool_end" # Used to use 'SUBAGENT_END' but that was confusing
    SUBAGENT_OUTPUT = "sub_output"
    SUBAGENT_ERROR = "sub_error"
    SUBAGENT_TOOL = "sub_tool" # A tool invocation inside the call to a sub-agent
    SUBAGENT_END = "sub_end"
    RUN_CREATED = "run_created"
    RUN_UPDATED = "run_updated"
    AGENT_SAVED = "agent_saved"
    TOKEN_USAGE = "token_usage"
    REQUEST_VARS_EVENT = "request_vars"
    ENABLE_TOOL_EVENT = "enable_tool"
    CHAT_MODEL_END = "chat_model_end"
    ADD_MEMORY_EVENT = "agent_memory"
    AUDIO_STREAM_EVENT = "audio_stream"
    CHANGE_STATE_EVENT = "change_state"
    ASSET_CREATED = "asset_created"

class AgentEvent(BaseModel):
    type: Optional[str] = ""
    agent_id: str
    user_id: str
    run_id: Optional[str] = None
    lc_run_id: Optional[str] = None
    live: bool = True

    class Config:
        allow_arbitrary_types = True

    def json(self):
        return json.dumps(self.model_dump())
    
@EventRegistry.register
class AgentErrorEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.ERROR)
    message: str

@EventRegistry.register
class AgentEndEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.END)

@EventRegistry.register
class AgentOutputEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.OUTPUT)
    str_result: str
    object_result: Optional[Any] = None

    @staticmethod
    def coalese_output_events(events: list["AgentOutputEvent"]) -> list[AgentEvent]:
        res = []
        content = ""
        last_str_event = None
        for event in events:
            if event.object_result:
                # Keep all object results
                res.append(event)
            elif event.str_result:
                # coalesce string results
                content += event.str_result
                last_str_event = event

        if content:
            last_str_event.str_result = content
            res.append(last_str_event)
        return res

@EventRegistry.register
class AgentSavedEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.AGENT_SAVED)

@EventRegistry.register
class RunCreatedEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.RUN_CREATED)

@EventRegistry.register
class RunUpdatedEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.RUN_UPDATED)

@EventRegistry.register
class AgentInputEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.INPUT)
    prompt: str

@EventRegistry.register
class ToolEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.TOOL)
    name: str
    tool_params: dict

@EventRegistry.register
class ToolLogEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.TOOL_LOG)
    message: str

@EventRegistry.register
class ToolResultEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.TOOL_RESULT)
    output_object: Any

@EventRegistry.register
class ToolEndEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.TOOL_END)

@EventRegistry.register
class EnableToolEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.ENABLE_TOOL_EVENT)
    file_name: str = ""
    tool_factory_id: str = ""
    credential_id: str = ""
    name: str

    def __str__(self):
        return f"EnableToolEvent: {self.file_name}"

@EventRegistry.register
class RequestVarsEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.REQUEST_VARS_EVENT)
    var_names: list[str]

    def __str__(self):
        return f"RequestVarsEvent: {self.var_names}"

@EventRegistry.register
class TokenUsageEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.TOKEN_USAGE)
    usage_metadata: dict

@EventRegistry.register
class ChatModelEnd(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.CHAT_MODEL_END)

@EventRegistry.register
class AddMemoryEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.ADD_MEMORY_EVENT)
    fact: str

@EventRegistry.register
class AudioStreamEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.AUDIO_STREAM_EVENT)
    audio_format: str = ""
    audio_url:    str = ""
    
@EventRegistry.register
class ChangeStateEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.CHANGE_STATE_EVENT)
    state: str

class AssetTypeEnum(IntEnum):
    IMAGE = 1
    TABLE = 2
    DOC = 3
    CODE = 4

@EventRegistry.register
class AssetCreatedEvent(AgentEvent):
    type: str = Field(default=AgentLogEventTypes.ASSET_CREATED)
    asset_id: str
    asset_type: AssetTypeEnum
    asset_name: str
    asset_url: str


SUBSCRIBER_POOL: dict[str, redis.client.PubSub] = {}
class AsyncPubSub:
    def __init__(self):
        self._client: redis.Redis = None
        self.alive = True

    def stop(self):
        self.alive = False

    async def get_client(self) -> redis.Redis:
        if self._client is None:
            url = config.get_global("REDIS_URL", False)
            self._client = await redis.from_url(url or "redis://localhost", decode_responses=True)
        return self._client

    async def publish(self, channel: str, message: str|dict|AgentEvent):
        if isinstance(message, AgentEvent):
            message = message.json()
        elif isinstance(message, dict):
            message = json.dumps(jsonable_encoder(message))
        else:
            message = str(message)        
        client = await self.get_client()
        #print(f">> Publishing ({channel}): ", message)
        await client.publish(channel, message)

    async def subscribe(
            self, 
            channel: str, 
            callback: Optional[SubscribeCallback]=None) -> redis.client.PubSub:
        client = await self.get_client()
        pub = client.pubsub()
        await pub.psubscribe(channel)
        if callback:
            asyncio.create_task(self.reader(pub, channel, callback))
        return pub

    # Creates a subscriber keyed by the indicated ID, and maintains that object in a pool
    # The subscriber returned, but you can use ...
    async def create_subscriber(
            self,
            sub_id: str,
            channel: str,
            recreate: bool=True,
    ) -> redis.client.PubSub:
        if sub_id in SUBSCRIBER_POOL and not recreate:
            print("Returning existing channel for ", sub_id, " on topic ", channel)
            return SUBSCRIBER_POOL[sub_id]
        else:
            print("Subscribing channel for ", sub_id, " on topic ", channel)
            sub = await self.subscribe(channel)
            SUBSCRIBER_POOL[sub_id] = sub
            return sub
        
    async def cancel_subscriber(
            self,
            sub_id: str,
            channel: str,
    ):
        if sub_id in SUBSCRIBER_POOL:
            sub = SUBSCRIBER_POOL[sub_id]
            await sub.unsubscribe([channel])
            del SUBSCRIBER_POOL[sub_id]


    async def unsubscribe(
            self, 
            channel: str):
        client = await self.get_client()
        pub = client.pubsub()
        await pub.unsubscribe(channel)

    async def reader(self, pubsub, channel: str, callback: SubscribeCallback):
        while self.alive:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if message is not None:
                event = json.loads(message['data'])
                await callback(event['type'], event)
            else:
                await asyncio.sleep(0.1)

    async def set(self, key: str, value: str, ttl: Optional[int]=None):
        client = await self.get_client()
        await client.set(key, value)
        if ttl:
            await client.expire(key, ttl)

    async def get(self, key: str):
        client = await self.get_client()
        return await client.get(key)

    async def delete(self, key: str):
        client = await self.get_client()
        await client.delete(key)
                
pubsub  = AsyncPubSub()
