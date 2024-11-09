from contextlib import contextmanager
import re
from typing import Optional, Any, Type
import traceback
from collections import namedtuple
from uuid import UUID
import os
import mimetypes
from collections import defaultdict

from sqlmodel import select, or_

from langchain.callbacks.manager import AsyncCallbackManager
from langchain_core.callbacks.manager import (
    adispatch_custom_event,
)

from supercog.shared.apubsub import (
    pubsub, 
    AgentEvent,
    AgentOutputEvent,
    AgentEndEvent,
    AgentLogEventTypes, 
    ToolLogEvent,
    ToolEvent,
    AssetCreatedEvent,
    AssetTypeEnum,
)
from supercog.shared.models import DocIndexReference

from .db import session_context, Agent, Run, DocIndex
from .jwt_auth import User as JWTUser
from .filesystem import get_user_directory

from supercog.shared.utils import (
    get_boto_client, 
    upload_file_to_s3, 
    create_presigned_url,
    upload_file_to_s3, 
)

from supercog.shared.services import config

ContextInit = namedtuple("ContextInit", [
    "tenant_id", 
    "user_id", 
    "agent_id", 
    "agent_name", 
    "run_id", 
    "logs_channel",
    "secrets",                # Use ENV VAR secrets
    "enabled_tools",          # Dict of factory_id>tool_names for tools enabled on the agent
    "user_email",
    "run_scope",
    "doc_indexes",
])

LangChainCallback = AsyncCallbackManager


class RunContext:
    """
       This object represents the context in which an agent is executing. It is mostly
       used by Tools to introspect the running state, and to do things like publish
       events which should be published as agent events.

       We want to be careful that this object may get serialized and it should do so safely.
    """

    def __init__(self, opts: ContextInit) -> None:
        self.tenant_id = opts.tenant_id
        self.user_id = opts.user_id
        self.agent_id = opts.agent_id
        self.agent_name = opts.agent_name
        self.run_id = opts.run_id
        self.logs_channel = opts.logs_channel
        self.secrets = opts.secrets
        self.enabled_toos = opts.enabled_tools
        self.user_email = opts.user_email
        # This is a cache of assets created while tools are running. Once the tool finishes
        # then ChatEngine will publish these events
        self.asset_events = []
        self.asset_contents = {}
        # The scope of this run, inherited from the agent, "private" or "shared"
        self.run_scope = opts.run_scope
        self.doc_indexes: list[DocIndexReference] = opts.doc_indexes

    @classmethod
    def create_squib_context(cls, tenant_id: str, user_id: str, secrets: dict):
        return RunContext(
            ContextInit(
                tenant_id=tenant_id, 
                user_id=user_id, 
                agent_id="", 
                agent_name="", 
                run_id="",
                logs_channel="",
                secrets=secrets,
                enabled_tools={},
                user_email="",
                run_scope="private",
                doc_indexes=[],
            )
        )

    def run_is_shared(self) -> bool:
        return self.run_scope == "shared"   

    # Set tools by mapping of tool.id to tool name
    def set_enabled_tools(self, tools: dict[str,str]):
        self.enabled_tools = tools

    def tool_is_enabled(self, tool_factory_id: str) -> bool:
        return tool_factory_id in self.enabled_tools
    
    def get_file_url(self, file_name, folder="") -> dict:
        s3 = get_boto_client('s3')
        bucket_name = config.get_global("S3_FILES_BUCKET_NAME") or ""

        if folder:
            s3_folder = f"{self.user_id}/{folder}"
        else:
            s3_folder = self.user_id
        object_name = f"{self.tenant_id}/{s3_folder}/{file_name}"
        print("get_file_url->",object_name)

        return create_presigned_url(s3, bucket_name, object_name, expiration=(60*60*24))
    
    def upload_user_file_to_s3(self, file_name, original_folder="", mime_type="", return_download_url=False) -> dict:
        bucket = config.get_global("S3_FILES_BUCKET_NAME")
        folder = f"{self.user_id}/{original_folder}"    
        if not folder.endswith("/"):
            folder = folder + "/"
        object_name = f"{self.tenant_id}/{folder}{file_name}"

        file_path = os.path.join(original_folder, file_name)

        if not mime_type:
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

        try:
            with open(file_path, 'rb') as file_obj:
                private_url = upload_file_to_s3(
                    file_obj, 
                    bucket, 
                    object_name,
                    mime_type,
                )
                if return_download_url:
                    return self.get_file_url(file_name, original_folder)
                else:
                    return {"url": private_url}
            
        except IOError as e:
            raise RuntimeError(f"Error opening file {file_path}: {e}")

    
    def set_extras(self, extras: dict) -> None:
        self._extras = extras

    def create_event(self, event_type: Type, callbacks, **fields) -> AgentEvent:
        return event_type(
            agent_id=self.agent_id,
            run_id=self.run_id,
            user_id=self.user_id,
            lc_run_id=str(getattr(callbacks, 'parent_run_id', '')),
            **fields
        )
    
    def calculate_cache_key(self, asset_id: str) -> str:
        return f"{self.tenant_id}/{self.user_id}/{asset_id}"

    def queue_asset_event(
            self, 
            asset_id: str, 
            asset_type: AssetTypeEnum, 
            asset_name: str,
            content: Optional[bytes] = None,
            content_type: Optional[str] = None) -> AgentEvent:
        
        cache_key = self.calculate_cache_key(asset_id)

        if content and content_type:
            self.asset_contents[cache_key] = [content, content_type]

        self.asset_events.append(
            self.create_asset_event(asset_id, asset_type, asset_name)
        )

    # Returns a Generator of AgentEvents
    async def get_queued_asset_events(self):
        while self.asset_events:
            agevent: AssetCreatedEvent = self.asset_events.pop(0)
            if agevent.asset_id in self.asset_contents:
                content, content_type = self.asset_contents[agevent.asset_id]
                cache_key = self.calculate_cache_key(agevent.asset_id)
                # keeping assets for 24 hours, but we should probably store them in a persistent store
                await pubsub.set(cache_key, content, ttl=60*60*24)
                await pubsub.set(cache_key + "/content_type", content_type, ttl=60*60*24)
            yield agevent

    @staticmethod
    async def get_asset(tenant_id: str, user_id: str, asset_id: str) -> tuple[bytes, str]:
        cache_key = f"{tenant_id}/{user_id}/{asset_id}"
        content = await pubsub.get(cache_key)
        content_type = await pubsub.get(cache_key + "/content_type")
        return content, content_type

    def create_asset_event(
            self, 
            asset_id: str, 
            asset_type: AssetTypeEnum, 
            asset_name: str) -> AgentEvent:

        asset_url = os.environ.get("ENGINE_URL", "") + f"/asset/{self.tenant_id}/{self.user_id}/{asset_id}"

        return self.create_event(
            AssetCreatedEvent,
            callbacks=None,
            asset_id=asset_id,
            asset_type=asset_type,
            asset_name=asset_name,
            asset_url=asset_url,
        )

    async def publish(self, agevent: AgentEvent):
        await adispatch_custom_event(
            agevent.type,
            agevent.model_dump(),
        )   

    def get_current_user_email(self) -> str:
        return self.user_email

    def get_user_rag_indices(self) -> list[str]:
        with session_context() as session:
            query = select(DocIndex).where(
                DocIndex.tenant_id == self.tenant_id, 
            )
            if self.run_scope == "shared":
                # in shared run you only get shared indexes
                query = query.where(DocIndex.scope == "shared")
            else:
                # in private run can use private or shared indexes
                query = query.where(
                    or_(
                        DocIndex.user_id == self.user_id,
                        DocIndex.scope == "shared",
                    )
                )
            res = session.exec(query)
            return [index.name for index in res.all()]

    def get_env_var(self, var_name: str) -> str:
        return self.secrets.get(var_name)

    def get_doc_indexes(self) -> list[DocIndexReference]:
        # Returns the RAG indexes activate for the current Agent/Run
        return self.doc_indexes

    def find_doc_index_by_name(self, index_name: str) -> DocIndexReference|None:
        for index in self.doc_indexes:
            # not sure if we will need or want something more fuzzy
            if index.name.lower() == index_name.lower():
                return index
        return None
        
    def create_agent_directory(self) -> str:
        """
        Create and return the path to an agent-specific directory.
        """
        safe_agent_name = re.sub(r'[^\w\-_\. ]', '_', self.agent_name)
        agent_dir_name = f"{safe_agent_name}_{self.agent_id}"
        agent_dir = agent_dir_name
        os.makedirs(agent_dir, exist_ok=True)
        return agent_dir

    def resolve_secrets(self, text: Any, require_value: bool=False) -> Any:
        # Resolves $ENV_VAR and ${ENV_VAR} references. If require_values is True then
        # throws an exception if the variable is not found.
        if not isinstance(text, str):
            return text

        # Finds any ${VAR} patterns in text and replaces them with env var values
        for var in re.findall(r"\${(.*?)}", text):
            replacement = self.secrets.get(var)
            if replacement is not None:
                text = text.replace(f"${{{var}}}", replacement)
            elif require_value:
                raise ValueError(f"Missing value for ${var}")
        for var in re.findall(r"\$([\w_]+)", text):
            replacement = self.secrets.get(var)
            if replacement is not None:
                text = text.replace(f"${var}", replacement)
            elif require_value:
                raise ValueError(f"Missing value for ${var}")
        return text

    def validate_secret(self, text: str|None) -> tuple[bool, str]:
        # Returns True,None if the indicated value is a literal or if it
        # refers to an Env Var that we know about. Otherwise it returns False and
        # a message about the missing value.
        if text is None:
            return True, ""
        try:
            self.resolve_secrets(text, require_value=True)
            return True, ""
        except ValueError as e:
            return False, str(e)

    def resolve_secret_values(self, values: dict) -> dict:        
        return {self.resolve_secrets(k): self.resolve_secrets(v) for k, v in values.items()}
    
    def _get_real_file_path(self, file_name: str) -> str:
        return os.path.join(get_user_directory(self.tenant_id, self.user_id), file_name)
    
    def __getstate__(self) -> object:
        state = self.__dict__.copy()
        for key in list(state.keys()):
            if key.startswith('_'):
                del state[key]
        return state
    
    def update_env_vars(self, vals: dict):
        self.secrets.update(vals)

    @contextmanager
    def get_db_session(self):
        with session_context() as session:
            yield session

    def get_user_object(self) -> JWTUser:
        return JWTUser(user_id=self.user_id, tenant_id=self.tenant_id)

    # Executing a sub-agent is tricky because of the call chain:
    # 
    # main ->
    #   EngineMgr ->
    #     ChatEngine ->
    #       AgentTool ->
    #         RunContext.execute_agent
    #            -> ChatEngine.respond
    #   <---------- logging
    #   <---------- run aborted check
    #         
    async def execute_agent(
        self,
        target_agent_id: str,
        prompt: str,
        callbacks: Optional[LangChainCallback]=None,
        ) -> str:
        """ Invokes the indicated agent and passes it the prompt. Returns the results from agent."""
        from .chat_logger import ChatLogger
        from .chatengine import ChatEngine

        parent_lc_run_id = callbacks.parent_run_id

        with session_context() as session:
            agent = session.get(Agent, target_agent_id)
            if agent is None:
                return f"Error: Agent {target_agent_id} not found"
            run_db = session.get(Run, self.run_id)
            if run_db is None:
                return f"Error: Run {self.run_id} not found"
            
            chatengine = ChatEngine()
            try:
                await chatengine.set_agent(
                    agent, 
                    run_db.tenant_id, 
                    run_db.user_id,
                    str(run_db.id),
                    run_db.scope,
                    run_db.logs_channel,
                    run_db.tools,
                    user_email=self.user_email,
                )
            except Exception as e:
                traceback.print_exc()
                return f"Error running agent: {e}"

            # Do we need to keep this chatengine? We would do so if we made sub-agent calling
            # 'stateful' so that you can invoke the same agent multiple times in a single run.
            # In that case our run might need a list of ChatEngines instead of a single one.
            # run_db.chatengine_id = chatengine.id

            return await self._invoke_agent(chatengine, prompt, run_db, parent_lc_run_id)

    async def _invoke_agent(self, chatengine, prompt, run, parent_lc_id) -> str:
        from .chat_logger import ChatLogger
        from .main import enginemgr
        
        mypublish = enginemgr.create_publish_function(run, lc_run_id=parent_lc_id)

        prompt_published: bool = False

        async def check_run_canceled():
            if run.logs_channel:
                if await pubsub.get(f"{run.logs_channel}_cancel"):
                    print("Run canceled!!")
                    await mypublish(AgentOutputEvent, str_result="Request canceled")
                    await mypublish(AgentEndEvent)
                    return True
            return False

        async def log_function(batch: AgentEvent|list[AgentEvent]):
            nonlocal prompt_published

            if not isinstance(batch, list):
                batch = [batch]

            if await check_run_canceled():
                # abort our tool function
                raise RuntimeError("Function aborted by cancel request")
            
            if len(batch) > 1 and batch[0].type == AgentLogEventTypes.OUTPUT:
                batch = AgentOutputEvent.coalese_output_events(batch)

            if not prompt_published:
                # This is really icky. Because of Langchain async, we will get invoked before
                # the "call_agent" tool function generates its start event. So if we publish our 
                # input event too early it will arrive out of sequence. So this hack waits until
                # the sub-agent generates its first (output) event before publishing the input prompt.
                # Ideally we would fix all this by moving to generating custom events for Tools 
                # (instead of side-publishing directly to Redis) so those events would flow out
                # the normal agent event mechanism.
                prompt_published = True
                await mypublish(ToolLogEvent, message=f"Input: {prompt}", role="user")

            if isinstance(batch, list):
                for event in batch:
                    if isinstance(event, AgentOutputEvent):
                        await mypublish(ToolLogEvent, message=event.str_result)
                    elif isinstance(event, ToolEvent):
                        await mypublish(ToolLogEvent, message=f"Calling {event.name}")
                    elif isinstance(event, ToolLogEvent):
                        await mypublish(ToolLogEvent, message=event.message)
                    else:
                        # probably want to filter various events from the subagent
                        await mypublish(event.__class__, **event.model_dump())

        response = ""

        output_events: list[AgentOutputEvent] = []
        batch_size = 25
        async for event in chatengine.respond(prompt, log_function, check_run_canceled):
            # Add the question and answer to the current chat.
            if await check_run_canceled():
                break
            if event.type == AgentLogEventTypes.OUTPUT:
                output_events.append(event)
                response += event.str_result or ""
            if event.type != AgentLogEventTypes.OUTPUT or len(output_events) > batch_size:
                if output_events:
                    await log_function(output_events)
                    output_events = []
                if event.type != AgentLogEventTypes.OUTPUT:
                    await log_function([event])

        if output_events:
            await log_function(batch=output_events)

        #await mypublish(AgentEndEvent)

        print("RETURNING RESPONSE FROM SUB AGENT:")
        print(response)
        return response
       
    @staticmethod
    def _get_test_context() -> "RunContext":
        def log_msg(*args, **kwargs):
            print(args, kwargs)

        return RunContext(
            ContextInit(
                tenant_id="t1", 
                user_id="u1", 
                agent_id="a1", 
                agent_name="agent 1", 
                run_id="run1",
                logs_channel="logs",
                secrets={},
                enabled_tools=[],
                user_email="none",
                run_scope="private",
                doc_indexes=[]
            )
        )
