from functools import partial
from datetime import datetime, timezone
from pathlib import Path
from pprint import pprint
import json
import time
from typing import (
    Dict, Any, List, Generator, Optional, AsyncGenerator, Callable, Sequence,
    Awaitable,
)
import os
import sys
import traceback
from uuid import uuid4

from openai import OpenAI
import pandas as pd
import re
from typing import Union
from langchain_openai import ChatOpenAI
import rollbar


from langchain.agents import AgentExecutor, Agent
from langchain_core.tools import BaseTool
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.callbacks import AsyncCallbackManagerForChainRun
from langchain_core.utils.input import get_color_mapping

import asyncio
from typing import Dict, List, Any, Union, Optional, AsyncIterator


from langchain_core.runnables.base import RunnableSequence, RunnableBinding

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate, HumanMessagePromptTemplate
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.prompts import MessagesPlaceholder
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, ToolMessage, SystemMessage, merge_content
from langchain.agents.format_scratchpad.openai_tools import (
    format_to_openai_tool_messages,
)
from langchain_community.chat_models import ChatOllama
from langchain_community.callbacks import get_openai_callback
from langchain.agents.output_parsers.openai_tools import OpenAIToolsAgentOutputParser
from langchain.agents import AgentExecutor
from langchain.agents import tool
from langchain.callbacks.base import BaseCallbackHandler
from langchain_groq import ChatGroq
from langchain_anthropic import ChatAnthropic
from langchain.callbacks import LangChainTracer
from langchain.callbacks.manager import CallbackManager

from sqlmodel import select

from supercog.engine.all_tools import FACTORY_MAP, ToolFactory, ReadFileTool
from supercog.engine.tools.s3_utils import get_file_from_s3, put_file_to_s3, list_files

from supercog.shared.utils import dict_safe_get, parse_markdown, NodeTypes
from supercog.shared.credentials import secrets_service
from supercog.shared.services import config
from supercog.shared.logging import logger
from supercog.shared.apubsub import (
    AgentEvent,
    AgentOutputEvent,
    TokenUsageEvent,
    ToolEvent,
    EnableToolEvent,
    ToolResultEvent,
    ToolEndEvent,
    ChatModelEnd,
    AgentErrorEvent,
    RequestVarsEvent,
    EventRegistry,
    AssetTypeEnum,
)

from supercog.shared.models import AgentBase, ToolBase, DocIndexReference
from .db import Credential, session_context, Run
from .tools.utils import async_logging_client

from .logging_handler import FileLogHandler

from .tools.agent_tool import AgentTool
from .tools.dynamic_agent_tool import DynamicAgentTool
from .tools.basic_data import BasicDataTool
from .run_context import RunContext, ContextInit
from .history_compression_manager import HistoryCompressionManager
from .tools.memory_compression_tool import MEMORY_COMPRESSION_TOOL_ID, MemoryCompressionTool
from .rag_utils import get_available_indexes
from .jwt_auth import User

from langchain.chains import LLMChain

logfile = "output.log"
file_logger = FileLogHandler(logfile) 

AsyncCallback = Callable[[AgentEvent], Awaitable[None]]
RunAbortedCallback = Callable[None, Awaitable[bool]]

GROQ_MODELS = [
    "llama-3.1-405b-reasoning",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "llama3-70b-8192",
    "llama3-groq-70b-8192-tool-use-preview",
]
bd = BasicDataTool()
FACTORY_MAP[bd.id] = bd

class InterruptableAgentExecutor(AgentExecutor):
    interrupt: bool = False
    _tool_lock: asyncio.Lock

    class Config:
        extra = "allow" 

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tool_lock = asyncio.Lock()

    def _should_continue(self, iterations: int, time_elapsed: float) -> bool:
        if self.interrupt:
            return False
        else:
            return super()._should_continue(iterations, time_elapsed)

    async def add_tools(self, tools: list[BaseTool|Callable], replace: bool=False) -> None:
        """Add a new tool to the agent's toolkit."""
        async with self._tool_lock:
            existing_tool_names = [tool.name for tool in self.tools]
            if replace:
                self.tools = tools
            else:
                for t in tools:
                    if t.name not in existing_tool_names:
                        self.tools.append(t)
            # Update the agent's allowed tools if necessary
            if hasattr(self.agent, "allowed_tools"):
                self.agent.allowed_tools = [tool.name for tool in self.tools]
            await self._update_llm_tools()

    async def remove_tool(self, tool_name: str) -> None:
        """Remove a tool from the agent's toolkit by name."""
        async with self._tool_lock:
            self.tools = [tool for tool in self.tools if tool.name != tool_name]
            # Update the agent's allowed tools if necessary
            if hasattr(self.agent, "allowed_tools"):
                self.agent.allowed_tools = [
                    name for name in self.agent.allowed_tools if name != tool_name
                ]
            await self._update_llm_tools()

    async def _update_llm_tools(self) -> None:
        """Update the LLM's knowledge of available tools."""
        if hasattr(self.agent, 'runnable') and isinstance(self.agent.runnable, RunnableSequence):
            for i in range(len(self.agent.runnable.middle)):
                nextst = self.agent.runnable.middle[i]
                if isinstance(nextst, RunnableBinding):
                    new_step = nextst.bound.bind_tools(self.tools)
                    self.agent.runnable.middle[i] = new_step

    async def _aiter_next_step(
        self,
        name_to_tool_map: Dict[str, BaseTool],
        color_mapping: Dict[str, str],
        inputs: Dict[str, str],
        intermediate_steps: List[Any],
        run_manager: Optional[AsyncCallbackManagerForChainRun] = None,
    ) -> AsyncIterator[Union[AgentFinish, AgentAction, Any]]:
        """Override _aiter_next_step to update tool map and color mapping."""
        async with self._tool_lock:
            # Update name_to_tool_map with the current set of tools
            name_to_tool_map = {tool.name: tool for tool in self.tools}
            color_mapping = get_color_mapping(
                [tool.name for tool in self.tools], excluded_colors=["green"]
            )

        # Call the parent method to handle the rest of the logic
        async for step in super()._aiter_next_step(
            name_to_tool_map, color_mapping, inputs, intermediate_steps, run_manager
        ):
            yield step

class ChatEngine(BaseCallbackHandler):
    GPT3_MODEL = "gpt-3.5-turbo-1106"
    GPT4_MODEL = "gpt-4o"
    DEFAULT_MODEL = "gpt-4o-mini"
    DEFAULT_OPENAI_KEY = config.get_global("OPENAI_API_KEY")

    def __init__(self) -> None:
        self.id = uuid4()
        self.chat_history: list[HumanMessage|AIMessage|ToolMessage] = []
        self.prompt: ChatPromptTemplate = None
        self.cache_enabled = False
        self._agent_model: AgentBase|None = None
        self._agent_dict: dict
        self.agent_id: str = None
        self.tenant_id: str = None
        self.user_id: str = None
        self.tool_factories: list[ToolFactory] = []
        self.run_tools: list[ToolBase] = []
        self.enabled_tool_funcs: list[Callable] = []
        # Map tool functions back to their Source tool names, for display purposes
        self.function_tool_names = {}
        self.inject_llm_context: Callable[[], str]|None = None
        self.generating: bool = False
        # Sometimes tools may log BEFORE we get the tool start event, and this confuses the dashboard.
        # So cache the logs in this case so we can send them once the tool officially starts.
        self.tool_logs_cache: dict[str,list] = {}
        self.seen_tool_run_ids: list[str] = list()
        self.llm: BaseChatModel = None
        self.parent_log_function: AsyncCallback = None
        # Follow dict holds things (currently DataFrames) in server memory that can be shared amongst
        # the tools of an agent.
        self.tools_inmem_state: dict = dict()
        self.required_token_var: str = ""
        self.pending_agent_updates = []
        self.max_history: int|None = None
        self.history_compression_manager = HistoryCompressionManager()
        # The set of RAG indexes enabled for this agent
        self.doc_indexes: list[DocIndexReference] = []


    def reset(self):
        self.chat_history = []

    def info(self):
        return {
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "history_len": len(self.chat_history),
            "generating": self.generating,
        }

    @property
    def agent(self):
        if self._agent_model is None:
            self._agent_model = AgentBase(**self._agent_dict)
        return self._agent_model
    
    async def set_agent(
            self, 
            agent: AgentBase, 
            tenant_id: str, 
            user_id: str,
            run_id: str, 
            run_scope: Optional[str]="private",
            run_log_channel: str|None=None,
            run_tools: list[dict] = [],
            user_email: str|None=None,
        ):
        if not agent.model:
            agent.model = self.DEFAULT_MODEL
        self._agent_dict = agent.model_dump()
        self.agent_id = agent.id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.max_history = agent.max_chat_length
        # Load the user's secrets
        secret_list = secrets_service.list_credentials(tenant_id, user_id, "ENV:", include_values=True)
        secrets = {k[4:]: v for k, v in secret_list}
        self.run_tools = [ToolBase(**d) for d in run_tools]
        self.doc_indexes = agent.get_enabled_indexes()

        self.run_context = RunContext(
            ContextInit(
                tenant_id=tenant_id, 
                user_id=user_id, 
                agent_id=agent.id, 
                agent_name=agent.name, 
                run_id=run_id,
                logs_channel=run_log_channel,
                secrets=secrets,
                enabled_tools={},
                user_email=user_email,
                run_scope=run_scope,
                doc_indexes=self.doc_indexes,
            )
        )

        self.chat_history = []
        await self.create_agent()

    async def update_agent(self, newagent: AgentBase):
        if not self.generating:
            self._agent_dict = newagent.model_dump()
            self._agent_model = None
            # This works because the agent memory is store separately
            print("Updating agent: ", newagent.id)
            self.run_tools = newagent.tool_list
            await self.create_agent()
            # clear any older updates
            self.pending_agent_updates.clear()
        else:
            print("Queueing agent update while still generating")
            self.pending_agent_updates.append(newagent)

    async def update_run_tools(self, run_tools: list[dict]):
        self.run_tools = [ToolBase(**t) for t in run_tools]
        await self.create_agent()

    async def process_pending_agent_updates(self):
        if self.pending_agent_updates:
            await self.update_agent(self.pending_agent_updates[-1])
            self.pending_agent_updates.clear()



    async def update_agent_secrets(self, secrets: dict):
        self.run_context.secrets |= secrets
        # Special case if the user has _just_ set their LLM API key
        if any([key for key in secrets if key.endswith("_API_KEY")]):
            print("Forcing create agent for new Env Vars")
            await self.create_agent()

    def replace_agent(self, newagent):
        # We keep chatengines around, but sometimes the Agent SQLModel throws an error
        # cause of a stale session
        self.agent = newagent

    def clear_chat_history(self):
        self.chat_history = []

    def reload_chat_history(self, runlogs: Sequence):
        self.chat_history = [
            HumanMessage(content=rl.content) if rl.role == "user" else 
            AIMessage(content=rl.content)
            for rl in runlogs
        ]

    def get_tool_credential(self, tool: ToolBase) -> Optional[Credential]:
        # Retrieve the Credential record referenced the Agent's tool. 
        if tool.credential_id is None:
            return None
        with session_context() as session:
            cred = session.get(Credential, tool.credential_id)
            if cred:
                # FIXME: Add 'credential resolution' logic that find's a matching Cred
                # available to the user in case the referenced one is private to 
                # someone
                #if cred.user_id == self.agent.user_id and \
                #    cred.tenant_id == self.agent.tenant_id:
                return cred
        return None

    def make_agent_tool(self, tool: ToolBase) -> Callable:
        agentTool = AgentTool()
        agentTool.run_context = self.run_context
        agentTool.inmem_state = self.tools_inmem_state
        self.tool_factories.append(agentTool)
        agent_id = tool.tool_factory_id.split(":")[1]
        return agentTool.get_tools(agent_id, tool.tool_name)[0]

    def load_agent_tools(self) -> list[Callable]:
        # Load the tools for the LLM agent. For each tool we need to retrieve
        # it's Credential and load the plaintext secrets. Then we construct
        # a partial tool func that passes the secrets into the function so
        # they can be used inside the tool.
        llm_tools: list[Callable] = []
        self.tool_factories = []

        preset_tools = []
        auto_tools = ['basic_data_functions']

        preset_tools.extend([
            ToolBase(id="t1", tool_factory_id=tool_id, agent_id=self.agent_id)
            for tool_id in auto_tools
        ])

        self.inject_llm_context = None
        for tool in ((self.run_tools or self.agent.tool_list) + preset_tools):
            if tool.tool_factory_id.startswith("agent:"):
                llm_tools.append(self.make_agent_tool(tool))
            else:
                # handle normal tools
                try:
                    factory: ToolFactory = FACTORY_MAP[tool.tool_factory_id]
                except Exception as e:
                    # fixme: ARO: 6/8/24 this happens when load_agent_tools is called before the get_tools request
                    #        from the dashboard. That currently causes dynamic tools to load. Static tools
                    #        are loaded statically but we can't load the dynamic tools until we know the tenant_id.
                    error_msg = f"Failed to load tool missing from FACTORY_MAP {tool.tool_factory_id}. Error: {e}. Skipping tool"
                    logger.error(error_msg)
                    continue
                tool_fact: ToolFactory = factory.__class__()
                if tool.tool_name:
                    tool_fact.system_name = tool.tool_name
                tool_fact.run_context = self.run_context
                self.tool_factories.append(tool_fact)
                tool_fact.inmem_state = self.tools_inmem_state

                if not tool.credential_id:
                    # special case for tool that needs no creds
                    llm_tools.extend(self._markup(tool_fact._get_full_agent_tools(), tool_fact.system_name))
                else:
                    cred = self.get_tool_credential(tool)
                    if cred is not None:
                        secrets = cred.retrieve_secrets()
                        secrets = tool_fact.prepare_creds(cred, secrets)
                        tool_fact.credentials = secrets
                        llm_tools.extend(self._markup(tool_fact._get_full_agent_tools(), tool_fact.system_name))
                        if hasattr(factory, "get_llm_context"):
                            func = getattr(factory, "get_llm_context")
                            self.inject_llm_context = partial(func, secrets)
                    else:
                        print("CANT FIND CRED FOR TOOL: ", tool)
                        print("Skipping tool")

        # Remove any duplicate functions
        new_list = []
        seen_names = set()
        for func in llm_tools:
            if not func.name in seen_names:
                new_list.append(func)
                seen_names.add(func.name)
            else:
                logger.error("WARNING: Removing Duplicate tool function: " + func.name)

        llm_tools = new_list

        self.run_context.set_enabled_tools(
            {tf.id: tf.system_name for tf in self.tool_factories}
        )
        logger.debug("Activated functions: ", str([f.name for f in llm_tools]))

        return llm_tools

    def _markup(self, funcs: list[Callable], tool_name: str) -> list[Callable]:
        for func in funcs:
            self.function_tool_names[id(func)] = tool_name
        return funcs
    
    async def enable_tool_insitu(self, tool_event: EnableToolEvent):
        # This function attempts to path our current running agent to add the functions
        # from a newly enabled tool. Previously we just re-created the agent to do this,
        # but that doesn't work inside a turn of the executor loop.
        self.run_tools.append(
            ToolBase(
                id="",
                tool_factory_id=tool_event.tool_factory_id,
                agent_id=self.agent_id,
                tool_name=tool_event.name,
                credential_id=tool_event.credential_id,
            )
        ) 
        # Persist new tool set on the Run
        with session_context() as session:
            rundb: Optional[Run] = session.get(Run, tool_event.run_id)
            if rundb:
                rundb.update_tools(self.run_tools)
                session.add(rundb)
                session.commit()

        # This get the new tool functions, and sets 'self.tool_factories' which is our enabled list
        new_funcs_list = self.load_agent_tools()
        existing_funcs = [f.name for f in self.enabled_tool_funcs]

        to_add = [func for func in new_funcs_list if func.name not in existing_funcs]
        # Now patch our running LangChain agent with the new functions
        await self.agent_executor.add_tools(to_add)
        self.enabled_tool_funcs = new_funcs_list


    async def attach_file_reading(self, attached_file: str):
        # In case the user uploads a file for analysis during a chat, we want to 
        # make sure that our agent has the tools to read the file. For now we
        # are just attaching generic file reading, but we should try to attach the
        # "right" tool based on the file type.
        readfile = ReadFileTool()
        readfile.run_context = self.run_context
        await self.create_agent(readfile.get_tools())

    def get_memories_prompt_message(self) -> List[HumanMessage]:
        # Check if the compression tool is available
        has_compression_tool = any(tool.tool_factory_id == MEMORY_COMPRESSION_TOOL_ID for tool in self.agent.tool_list)
        
        prompt = ""
        
        if has_compression_tool:
            prompt = """Respond to queries using your general knowledge and capabilities. If you encounter a <COMPRESSED_MESSAGE_ID> tag, do not automatically retrieve its content. Instead, ask the user if they want you to access the full content of that specific compressed message. Only use the Compression tool to retrieve the full content if the user explicitly confirms they need it. If the user doesn't confirm or says no, proceed with your task using only the information available in the current context. Do not mention compression or chat history unless directly relevant to the user's query. """
        try:
            memories = json.loads(self.agent.memories_json or "[]")
        except Exception as e:
            print(f"Exception in load memories {e}")
            return [HumanMessage(content=prompt)]

        # Filter memories where "enabled" is True
        memories = [m for m in memories if m["enabled"]]
        
        if memories:
            prompt += "\n\nMemory: \n\nYour <memory> block contains vital information for task success and error avoidance. Always access and utilize this memory to ensure optimal performance. \n"
            prompt += "<memory>\n- " + "\n- ".join(
                memory["memory"]
                for memory in sorted(memories, key=lambda x: x["ts"])
            ) + "\n</memory>\n"
        return [HumanMessage(content=prompt)]
        
    def get_tools_state_prompt(self, user_timezone: str|None):
        # Returns the readiness state of tools attached to the agent. This is meant to help Agents instrospect
        # which "tools" they have attached and whether those tools are ready to use (or if they need auth still).
        if len(self.tool_factories) > 0:
            msg = (
                "\n======== Current Tools ========\n" +
                "As an AI agent, you can enable one or more tools to accomplish work. Each tool\n" +
                "has a name and purpose, and provides a set of functions which you can call.\n" +
                "To add more tools, call 'search_for_tool' or 'enable_agent_tool'.\n" +
                "IGNORE any previously mentioned tools - you only have these enabled now:\n"
            )
            for tool_fact in self.tool_factories:
                ready, tool_msg = tool_fact.is_tool_ready()
                if ready:
                    msg += f"✅ {tool_fact.system_name} tool is enabled.\n"
                else:
                    msg += f"❌ {tool_fact.system_name} tool is not ready to use: {tool_msg}\n"
            msg += self.get_datetime_message(user_timezone)
            msg += "\n===========\n"
            # Because of this below we are connecting to the db on every Agent prompt... so we should probably
            # just create a db connection to wrap the whole "respond" call
            if len(self.doc_indexes) > 0:
                msg += "==== Current Knowledge Indices ===\n"
                for index in self.doc_indexes:
                    msg += f"📚 {index.name} \n"
                msg += "\n===========\n"
            return [HumanMessage(content=msg)]
        else:
            return []

    def get_datetime_message(self, user_timezone: Optional[str] = None) -> str:
        # Get the current UTC datetime 
        current_datetime = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        # Construct the message based on the presence of user_timezone

        datetime_message = f"Current UTC time is: {current_datetime}."
        if user_timezone:
            datetime_message += f" The human's tz offset is: {user_timezone}."

        return datetime_message

        
    async def create_agent(self, preset_tools: list[Callable] = []):
        print("Agent model is: ",self.agent.model)
        if 'claude' in self.agent.model:
            self.required_token_var = "CLAUDE_API_KEY"
        elif self.agent.model in GROQ_MODELS:
            self.required_token_var = "GROQ_API_KEY"
        else:
            self.required_token_var = "OPENAI_API_KEY"

        api_key = self.run_context.secrets.get(self.required_token_var)

        self.enabled_tool_funcs = []
        if self.agent.model and "mistral" in self.agent.model:
            # FIXME: Use the functions version
            self.llm = ChatOllama(model="mistral:latest")
        elif self.agent.model and 'claude' in self.agent.model and api_key is not None:
            self.llm = ChatAnthropic(
                model_name=self.agent.model,
                temperature=self.agent.temperature or 0,
                api_key=api_key,
            ) # type: ignore
            self.enabled_tool_funcs = self.load_agent_tools()
            self.enabled_tool_funcs.extend(preset_tools)

            if len(self.enabled_tool_funcs) > 0:
                self.llm = self.llm.bind_tools(self.enabled_tool_funcs) # type: ignore
        elif self.agent.model in GROQ_MODELS and api_key is not None:
            self.llm = ChatGroq(
                api_key=api_key,
                model=self.agent.model,
                temperature=self.agent.temperature or 0,
                streaming=False,
            ) # type: ignore
            self.enabled_tool_funcs = self.load_agent_tools()
            self.enabled_tool_funcs.extend(preset_tools)
            if len(self.enabled_tool_funcs) > 0:
                self.llm = self.llm.bind_tools(self.enabled_tool_funcs) # type: ignore
        else:
            # NOTE: We always allow a fallback to GPT4-mini so that people can run their agents.
            # At some level of usage we might decide not to offer this subsidy.
            self.enabled_tool_funcs = self.load_agent_tools()

            #logger.debug("Enabled tools: ", self.enabled_tools)
            if len(self.enabled_tool_funcs) + len(preset_tools) > 0:
                model_args = {"parallel_tool_calls":False}
            else:
                model_args = {}
            self.llm = ChatOpenAI(
                api_key=api_key or self.DEFAULT_OPENAI_KEY,
                model=self.agent.model if api_key else self.DEFAULT_MODEL, 
                temperature=self.agent.temperature or 0,
                streaming=True,
                stream_usage=True,
                #http_client=await async_logging_client(file_logger),
                callbacks=[file_logger],
                model_kwargs=model_args,
            )
            self.enabled_tool_funcs.extend(preset_tools)
            if len(self.enabled_tool_funcs) > 0:
                self.llm = self.llm.bind_tools(self.enabled_tool_funcs) # type: ignore

        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system", "{system_prompt}",
                ),
                MessagesPlaceholder(variable_name="agent_memory"),
                MessagesPlaceholder(variable_name="chat_history"),
                MessagesPlaceholder(variable_name="tools_state"),
                ("user", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )

        #print(self.prompt)

        langchain_tracer = self.get_langchain_tracer() # Traces visible in LangSmith UI
        tracers = list(filter(None, [langchain_tracer]))
        manager = CallbackManager(tracers)
               
        has_compression_tool = any(tool.tool_factory_id == MEMORY_COMPRESSION_TOOL_ID for tool in self.agent.tool_list)

        self.lang_agent = (
           {
               "system_prompt": lambda x: x["system_prompt"],
               "input": lambda x: x["input"],
               "agent_scratchpad": lambda x: format_to_openai_tool_messages(
                   x["intermediate_steps"]
               ),
               "agent_memory": lambda x: x["agent_memory"],
               "tools_state": lambda x: x["tools_state"],
               "chat_history": lambda x: x["chat_history"]
                if not has_compression_tool
                else self.history_compression_manager.process_chat_history(
                    x, self.agent.tool_list
                ),
           }
            | self.prompt
            | self.llm
            | OpenAIToolsAgentOutputParser()
        )
        
        max_time = self.agent.max_agent_time or 600
        self.agent_executor = InterruptableAgentExecutor(
            agent=self.lang_agent, 
            callback_manager=manager,
            tools=self.enabled_tool_funcs, 
            max_execution_time=max_time,   # wait 5 minutes. FIXME - would like to set this from user inruction screen for each run
            #handle_parsing_errors=True,
            verbose=True)
        

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        """Run when tool starts running."""
        pass

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        """Run when tool ends running."""
        pass

    def get_message_content(self, message):
        if isinstance(message.content, str):
            return message.content
        return "\n".join([
            str(content) 
            for content in message.content
        ])

    async def cancel_agent(self):
        self.agent_executor.interrupt = True

    def agent_is_canceled(self):
        return self.agent_executor.interrupt
    
    async def respond(
            self, 
            query: Any, 
            log_function: AsyncCallback,
            run_aborted: RunAbortedCallback,
            user: User,
        ) -> AsyncGenerator[AgentEvent, None]:
        llm_responses: list[str|dict] = [""]
        self.agent_executor.interrupt = False
        self.generating = True
        self.parent_log_function = log_function
        self.run_aborted_callback: RunAbortedCallback = run_aborted
        # squirrel these down for sub-agents
        self.run_context.set_extras({"log_function": log_function, "run_aborted": run_aborted})

        meta = {"agent_id": self.agent_id, "user_id": self.user_id}

        actual_model = ""
        if hasattr(self.llm, "model_name"):
            actual_model = self.llm.model_name
        elif hasattr(self.llm, "model"):
                actual_model = self.llm.model

        if actual_model != "" and actual_model != self.agent.model:
            # happens if user didn't supply the needed API key
            query = f"I can't use the selected LLM model {self.agent.model}. Please request this env var: {self.required_token_var}"
            query = f"Report the user must provide a key to use that LLM model."
            yield RequestVarsEvent(
                **(meta | {"var_names": [self.required_token_var]})
            )

        for event in self.handle_system_commands(query, meta, user):
            if event == True:
                yield ChatModelEnd(**meta)
                self.generating = False
                return
            else:
                yield event
        
        try:
            print(f"--------> Query = {query}")
       
            def get_text_content(content):
                if isinstance(content, list):
                    return " ".join([get_text_content(c) for c in content])
                if isinstance(content, str):
                    return content
                elif isinstance(content, dict) and 'text' in content:
                    return content['text']
                else:
                    return "" #str(content)


            # truncate chat history, but break at a turn start (HumanMessage)
            clean_history = self.sanitize_chat_history()
            #pprint(clean_history)
            
            def save_agent_response(content):
                llm_responses[-1] += content

            # Hacky way to identify the human to the agent. I considered adding closer to the system
            # prompt, but we want to show how messages from different humans are alternating, so it 
            # makes sense to keep the identity with the prompt.
            if user.name:
                first_name = user.name.split(" ")[0]
                query = f"{first_name}: {query}"

            async for event in self.agent_executor.astream_events(
                {
                    "system_prompt": self.agent.system_prompt,
                    "input": query, 
                    "chat_history": clean_history,
                    "agent_memory": self.get_memories_prompt_message(),
                    "tools_state": self.get_tools_state_prompt(user.timezone),
                },
                {
                    'callbacks': [self, file_logger],
                    # I _think_ I added this for Groq support, but I don't think it works...
                    'metadata': {'tools': self.enabled_tool_funcs},
                },
                version="v2",
            ):
                self.debug_lc_event(event)
                if await run_aborted():
                    break

                if event['event'] == 'on_chat_model_stream':
                    content = event['data']['chunk'].content
                    content = get_text_content(content)
                    save_agent_response(content)
                    yield AgentOutputEvent(**(meta | {"str_result":content, "lc_run_id":event['run_id']}))

                    chunk = event['data']['chunk']
                    if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                        yield TokenUsageEvent(
                            **(meta | {"usage_metadata":chunk.usage_metadata, 
                                       "lc_run_id":event['run_id']})
                        )

                elif event['event'] == 'on_tool_start':
                    params = dict_safe_get(event, 'data', 'input', default="")
                    tool_run_id = event['run_id']
                    self.seen_tool_run_ids.append(tool_run_id)
                    yield ToolEvent(
                        **(meta | {"name": event['name'], "tool_params":params, "lc_run_id":event['run_id']})
                    )

                    for event in self.unspool_tool_messages(tool_run_id):
                        yield event

                elif event["event"] == "on_tool_end":
                    message = event['data']['output']
                    async for asset_event in self.run_context.get_queued_asset_events():
                        yield asset_event
                    
                    yield ToolResultEvent(
                        **(meta | {"output_object":message, "lc_run_id":event['run_id']})
                    )
                    yield ToolEndEvent(**(meta | {"lc_run_id":event['run_id']}))

                    # FIXME: now that LC supports custom events, we should use that path to send tool logs so
                    # we don't have to queue them...
                    for tool_msg in self.unspool_tool_messages(event['run_id']):
                        yield tool_msg

                    llm_responses.append(
                        {"function_call": event["name"],
                         "input": str(event["data"]["input"]),
                         "output": str(event["data"]["output"]),
                        }
                    )
                    llm_responses.append("")
                elif event["event"] == "on_chat_model_end":
                    yield ChatModelEnd(**(meta | {"lc_run_id":event['run_id']}))

                elif event["event"] == "on_custom_event":
                    # custom event with be in the 'name' property
                    agevent = EventRegistry.reconstruct_event(meta | event["data"] | {"lc_run_id":event['run_id']})
                    if isinstance(agevent, EnableToolEvent):
                        await self.enable_tool_insitu(agevent)

                    yield agevent

                else:
                    pass

        except Exception as e:
            traceback.print_exc()
            rollbar.report_exc_info(sys.exc_info(), extra_data={"agent_id": self.agent_id, "query":query})
            msg = f"Agent internal error: {e}"
            logger.error(msg)
            save_agent_response("\n" + msg)
            # FIXME: we should probably have an "error" event type
            #yield  meta | {"type": AgentLogEventTypes.ERROR, "content": msg}
            yield AgentErrorEvent(**(meta | {"message":msg}))

        # Other LangChain events:
        # on_prompt_start, on_prompt_end - we could collect the agent input
        # from these events.
        if query:
            self.chat_history.append(HumanMessage(content=query))
        for response in llm_responses:
            if isinstance(response, dict):
                # assume a tool response
                self.chat_history.append(HumanMessage(content=str(response)))
            else:
                self.chat_history.append(AIMessage(content=response))

        self.generating = False

    def format_prompt(self):
        prompt_copy = self.prompt.copy()
        return prompt_copy.format(
            system_prompt=self.agent.system_prompt, 
            agent_memory=self.get_memories_prompt_message(),
            chat_history=self.sanitize_chat_history(), 
            tools_state=self.get_tools_state_prompt(None), 
            input="<input>", 
            agent_scratchpad=[]
        )

    def handle_system_commands(self, query, meta: dict, user: User) -> Generator[AgentOutputEvent|bool, None, None]:
        cmd = query.strip().replace(" ", "")
        res = None
        if cmd == "{tools}":
            time.sleep(3)
            res = "Enabled tools include:\n\n"
            for tool in self.tool_factories:
                res += f"**{tool.system_name}**\n\n"

        elif cmd == "{functions}":
            res = "Enabled functions include:\n\n"
            for func in self.enabled_tool_funcs:
                if id(func) in self.function_tool_names:
                    res += f"_{self.function_tool_names[id(func)]}_ **{func.name}**\n\n"
                else:
                    res += f"**{func.name}**\n\n"

        elif cmd == "{prompt}":
            time.sleep(3)
            res = "```\n" + self.format_prompt() + "\n```"

        elif cmd == "{user}":
            res = f"User: {user}\n"

        elif cmd == "{indexes}":
            res = "Available indexes:\n\n"
            for index in self.doc_indexes:
                res += f"**{index.name}**\n\n"

        if res:
            yield AgentOutputEvent(**(meta | {"str_result":res}))
            for _ in range(5):
                yield AgentOutputEvent(**(meta | {"str_result":"\n"}))
            yield True


    def sanitize_chat_history(self) -> list[HumanMessage|AIMessage|ToolMessage]:
        # Claude insists that chat messages are non-empty, and alternate cleanly beween
        # Human and AI. So this function removes empty messages and coalesces messages so they
        # alternate cleanly.

        # We work backwards in history and stop if we are at a human message and have exceeded
        # our max_chat_history length.
        revised = []
        for msg in reversed(self.chat_history):
            if msg.content in ["", [], None]:
                print("!!!!! REMOVING EMPTY CHAT HISTORY ENTRY: ", msg)
                continue
            elif len(revised) == 0 or type(msg) != type(revised[-1]):
                revised.append(msg)
            else:
                # coalesce same message type
                revised[-1].content = merge_content(revised[-1].content, msg.content)
            if self.max_history and isinstance(msg, HumanMessage) and len(revised) >= self.max_history:
                break
        
        return list(reversed(revised))

    def unspool_tool_messages(self, tool_run_id):
        for event in self.tool_logs_cache.get(tool_run_id, []):
            yield event
        self.tool_logs_cache[tool_run_id] = []


    def debug_lc_event(self, event):
        return
        print(f"--- {event['event'].upper()} -- langchain event")
        print(event)
        print()
        
    # Configures the LangChainTracer for the project
    # https://smith.langchain.com/ - here you can see the traces
    # Returns None if the API key is not set
    def get_langchain_tracer(self): 
        if not os.environ.get("LANGCHAIN_API_KEY"):
            return None
        
        project_name = os.environ.get("LANGCHAIN_PROJECT", "default")
        print(f"LangChain/LangSmith configured for '{project_name}' project, initializing tracer.")
    
        
        # Initialize LangChainTracer with the project name
        tracer = LangChainTracer(project_name=project_name)
        
        return tracer
