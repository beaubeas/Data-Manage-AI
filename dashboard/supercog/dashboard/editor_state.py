import ast
import asyncio
from datetime import datetime, timezone, timedelta
import base64
import json
import os 
import yaml
import requests
import time
import pytz
from collections import defaultdict
import yaml
import re
import traceback
from typing import AsyncGenerator
from typing import List, Tuple, Any
from uuid import uuid4
from .metacommands import route_command, RunAgentWithInput, AddMemories, Reflect, COMMANDS

import markdown as markdown_converter
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
import reflex as rx
from reflex.utils.exceptions import ImmutableStateError

import timeago
import base64

from supercog.shared import timeit
from supercog.shared.models import RunOutput, RunUpdate, RunLogBase, CredentialBase, RunBase, PERSONAL_INDEX_NAME
from supercog.shared.logging import logger
from supercog.shared.apubsub import (
    pubsub, 
    AgentLogEventTypes, 
    EventRegistry,
    AgentEvent,
    AgentInputEvent,
    AgentOutputEvent,
    AgentEndEvent,
    ToolEvent,
    ToolLogEvent,
    ToolEndEvent,
    AgentErrorEvent,
    ToolResultEvent,
    TokenUsageEvent,
    RequestVarsEvent,
    ChatModelEnd,
    AddMemoryEvent,
    EnableToolEvent,
    ChangeStateEvent,
    AssetCreatedEvent,
)

from .models import User, Agent, Tool, Folder
from .state_models import LocalCred, UITool, UIFolder
from .global_state import HOME_LINK
from .agents_common_state import AgentsCommonState
from .prompt_helpers import PromptHelpers
from .costs import calc_tokens_cents

from .state_models import QA, Answer, AgentState
from .global_state import GlobalState
from supercog.shared.utils import Colors

END_SENTINEL = {"type":"end"}

GENERATION_COMPLETE_MARK = "⋼"

class EditorState(AgentsCommonState, PromptHelpers):
    """Define empty state to allow access to rx.State.router."""
    _n_tasks: int = 0
    _logs: list[str] = []
    avail_models: list[str] = []
    __run: dict = None
    # track the time that the last prompt started, so we can record elapsed time (and compare to created_at on events)
    _turn_started: datetime = datetime.now()
    run_model: str = ""
    run_input_tokens: int = 0
    run_output_tokens: int = 0
    _tool_id_to_remove: str|None = None
    _tool_factory_to_remove: str|None = None
    _tool_name_to_remove: str|None = None
    temp_upload_file: str|None=None
    # The current set of tools from the active run, or the agent tools if no Run
    run_tools: list[UITool] = []
    chats: list[QA] = []

    loading_message: str|None=None

    # The current question.
    question: str

    # Whether we are processing the question.
    processing: bool = False

    test_prompt_modal_open: bool = False
    tool_modal_open: bool = False
    remove_tool_modal_open: bool = False
    app_clone_modal_open: bool = False
    editor_pane_class: str = ""


    app_modified: bool = False

    app: AgentState = AgentState(name="")
    _agent: Agent = None
    _agent_runs: list[RunOutput] = []
    agent_runs: list[list[str]] = []
    agent_runs_ns: list[dict] = []
    active_run_id: str = None
    tool_logos: dict[str,str | None] = {}

    test_prompt: str = ""

    warn_message: str = ""

    # memory related
    agent_memories:      List[Tuple[str,bool]] = []
    agent_memories_init: List[str] = []
    tool_memories:       List[Tuple[str,bool]] = []
    global_memories:     List[Tuple[str,bool]] = []
    
    reflect_modal_open:              bool = False
    reflect_modal_result:            list[str] = []
    reflect_modal_checked:           list[bool] = []
    reflect_modal_total_tokens:      int = 0
    reflect_modal_prompt_tokens:     int = 0
    reflect_modal_completion_tokens: int = 0
    reflect_modal_analysis:          str = ""
    
    # triggers
    avail_triggers: list[str] = []
    avail_prompt_engineering_strategies: list[str] = []
    avail_overall_user_strategies: list[str] = []
    # Set to indicate we need to reload creds on next page load
    credentials_list_dirty:bool = False

    # connections chooser
    matching_connections: list[LocalCred] = []

    filtered_commands: list[str] = []

    audio_queue: list[str] = []
    current_audio: str = ""
    is_playing: bool = False
    synchronized_audio_html: str = ""
    loading_run_logs: bool = False
    
    # new Supercog "wide" chat version
    files_list : list[dict[str,str]] = []


    #--------------------------------------------------------------------------------------------------
    # This section has initialization functions
    #--------------------------------------------------------------------------------------------------
    def update(self):
        # This method forces a re-render of the components
        print("State updated, forcing re-render.")
        pass

    def page_setup(self):
        if len(self._tool_factories) == 0:
            self.load_tool_factories()
    
    async def supercog_page_load(self):
        if self.user.is_anonymous():
            return

        # Special page load handler for the /supercog/ page. Main logic
        # is to allow return from Oauth flow to complete adding new tool.
        page_load_results = await self.editor_page_load(is_supercog=True)
        if page_load_results is not None and not isinstance(page_load_results, list):
            page_load_results = [page_load_results]
        cred_name = self.router.page.params.get('cred_name', None)
        if cred_name:
            self.load_connections(force=True) # force reload all creds
            local_cred = next((cred for cred in self.mycredentials if cred.name == cred_name), None)
            if local_cred:
                await self.notify_credential_created(local_cred)
                page_load_results.append(rx.redirect("/supercog/"))
            else:
                print(f"Load cred was not found: {cred_name}")
        if page_load_results:
            return page_load_results

    @timeit
    async def editor_page_load(self, appid:str|None = None, is_supercog:bool=False):
        if self.user.is_anonymous():
            return
        if self.avail_models == [] or self.credentials_list_dirty:
            self.load_lists(force=True)

        self.editor_pane_class = ""

        if appid is None:
            appid = self.current_appid

        if appid is None and is_supercog:
            appid = Agent.calc_system_agent_id(self.user.tenant_id, self.user.id, "Supercog")

        print("Load Agent:", appid)
        self.load_connections()
        self.load_system_agent_templates()

        self.__run = None # force a new Agent run on next input
        self.active_run_id = None

        if appid == "new":
            folder_slug = self.current_folder
            # setup a new App
            await self.create_new_agent()
            return [rx.redirect(f"/edit/{folder_slug}/{self.app.id}"), rx.toast.success(f"Created new agent: {self.app.name}")]
        else:
            with rx.session() as sess:
                self._agent = sess.get(Agent, appid) # type: ignore
                # If there is no agent in state and the appid is a template id then create the agent
                if self._agent is None:
                    template_agent_created = False
                    for template in self.system_agent_templates:
                        if template.id == appid:
                            self._agent = self.create_agent_from_template(sess, template=template)
                            template_agent_created = True
                    
                    if not template_agent_created:
                        raise RuntimeError(f"Agent '{appid}' not found")
                    
                # create our UI state version of the agent, and fix any missing creds
                self.app = AgentState.create(sess, self._agent, self._get_uitool_info, fixup_creds=True)
                self.app.lookup_user(sess)
                self.run_tools = self.app.uitools
                
                memories = json.loads(self._agent.memories_json or "[]")
                self.sync_state_memory_from_agent(memories, set_init_memories=True)

            for tool in self.app.tools:
                self.tool_logos[tool] = self.lookup_tool_factory_logo_url(tool)

        self._auto_save_tools = is_supercog
        self.run_model = self.app.model
        self.test_prompt = ""
        self.processing = False # failsafe in case we hit an error
        self.loading_message = None
        self._clear_chats()
        self._agent_runs = []
        
        self.load_avail_triggers()
        self.load_prompt_engineering_strategies()
        self._agentsvc.status_message = ""
        self.service_status = self._agentsvc.status_message
        self.launch_product_tour(is_supercog)

        print(f"!! Mounting app: {self.app.name}")
        self.show_welcome_message()
        return [EditorState.bg_load_runs, EditorState.bg_load_files, EditorState.mark_user_seen_editor(is_supercog)]

    @timeit
    def load_lists(self, force:bool = False):
        logger.debug("EditState, load lists")
        if len(self.folders) == 0:
            self.load_folders()
        self.load_connections(force)
        self.load_agent_tools_list()
        self.load_agents_list()
        self.avail_models = []
        self._default_model = ""
        for model in self._agentsvc.avail_models():
            if model.startswith("default:"):
                self._default_model = model[len("default:"):]
            else:
                self.avail_models.append(model)
        self.load_avail_triggers()
        self.load_prompt_engineering_strategies()
        self.service_status = self._agentsvc.status_message

    #--------------------------------------------------------------------------------------------------
    # This section is for tool modal 
    #--------------------------------------------------------------------------------------------------

    wide_tools_library: dict[str,list[UITool]] = {} #new style dict of Categories to tool lists
    
    @rx.var
    def uitool_ids(self) -> list[str]:
        if not isinstance(self.app, AgentState) or not isinstance(self.app.uitools, list):
            return []
        return [tool.tool_factory_id for tool in self.app.uitools]

    @rx.var
    def all_agents(self) -> list[AgentState]:
        return self._agent_list

    _files_loaded: bool = False
    _auto_save_tools: bool = False


    _tool_function_helps: dict[str,str] = {}
    filtered_commands:    list[str] = []
    _agent_list:          list[AgentState] = []
    expanded_folders:     list[str] = []
    
        
    def refresh_tools(self):
        self.load_tool_factories()
        self.refresh_agents()
        self.load_lists(force=True)

    async def auto_remove_tools(self):
        # Special logic to auto-remove "old" tools from the Supercog agent so the user doesn't have to
        with rx.session() as sess:
            needs_save = False
            tool: UITool
            for tool in self.app.uitools:
                if (
                    tool.tool_factory_id not in ["dynamic_agent_tools", "auto_dynamic_tools"]
                ):
                    self.app.remove_tool(tool.tool_id, tool.tool_factory_id, tool.name)
                    needs_save = True
            if needs_save:
                await self._save_agent(False)
                
    def refresh_agents(self):
        self.load_agents_list()

    @timeit
    def load_agent_tools_list(self):
        logger.debug("Loading agent tools")

        # Should be called after 'load_tool_factories'
        cats = sorted(set(t['category'] or '' for t in self._tool_factories))
        cat_tools = defaultdict(list)
        self._tool_function_helps = {}

        for tf in self._tool_factories:
            tool = UITool.from_tool_factory_dict(tf)
            self._tool_function_helps[tool.tool_factory_id or ""] = tool.functions_help or ""

            if tf['auth_config'] != {}:
                # Indicate no creds needed by omitting 'avail_creds'
                tool.avail_creds = self.find_avail_credentials(tf['id'], tf['compatible_system'])
                tool.creds_empty = len(tool.avail_creds) == 0
                tool.auth_needed = True
            else:
                tool.auth_needed = False
            cat_tools[tf['category'] or ''].append(tool)

        for cat in cats:
            self.wide_tools_library[cat] = []
            for tool in cat_tools[cat]:
                self.wide_tools_library[cat].append(tool)

        self.service_status = ""

    async def add_uitool(self, uitool_dict: dict, credential: dict, save_agent: bool=False):
        uitool = UITool(**uitool_dict)
        if credential:
            uitool.name = credential['name']
            uitool.credential_id = credential['id']
        if self._agent.uses_dynamic_tools():
            self.run_tools.append(uitool)
            self._update_run_tools()
        else:
            self.app.uitools.append(uitool)
            self.app.tools.append(uitool.name)
            self.app_modified = True
            if save_agent or self._auto_save_tools:
                await self.save_agent()

    def _update_run_tools(self):
        if self.__run:
            tool_dicts = [tool.to_db_tool(self._agent.id) for tool in self.run_tools]
            update = RunUpdate(
                tools=tool_dicts,
                tenant_id=self.user.tenant_id,
                user_id=self.user.id,
                agent_id=self._agent.id,
            )
            self._agentsvc.update_run(self.user_id, self.__run['id'], update)

    @rx.var
    def real_tools(self) -> list[UITool]:
        return [tool for tool in self.app.uitools if not tool.tool_factory_id.startswith("agent:")]
                
    async def add_agent_tool(self, app: dict):
        uitool = UITool(
            tool_factory_id="agent:" + app['id'],
            name=app['name'],
            logo_url=app['avatar'],
            help=app['description'] or '',
        )
        uitool.agent_url = f"/edit/{app['id']}"
        self.app.uitools.append(uitool)
        self.app_modified = True
        self.tool_modal_open = False
        await self.save_agent()

    def remove_uitool(self, tool_id: str, tool_factory_id: str, tool_name: str):
        self._tool_id_to_remove = tool_id
        self._tool_factory_to_remove = tool_factory_id
        self._tool_name_to_remove = tool_name
        self.remove_tool_modal_open = True

    def force_remove_uitool(self, tool_id: str, tool_factory_id: str, tool_name: str):
        self._tool_id_to_remove = tool_id
        self._tool_factory_to_remove = tool_factory_id
        self._tool_name_to_remove = tool_name
        return EditorState.confirm_remove_uitool
    
    async def confirm_remove_uitool(self):
        if self._agent.uses_dynamic_tools():
            # We only use self.run_tools and update the Run
            self.run_tools = [
                tool for tool in self.run_tools 
                if not (tool.tool_id == self._tool_id_to_remove or 
                        tool.tool_factory_id == self._tool_factory_to_remove)
            ]
            self._update_run_tools()
        else:
            try:
                self.app.remove_tool(self._tool_id_to_remove, self._tool_factory_to_remove, self._tool_name_to_remove)
            except ValueError:
                pass
            self.remove_tool_modal_open = False
            self.app = self.app
            self.app_modified = True
            await self.save_agent()

    def toggle_folder(self, folder_name: str):
        """
        Toggle the expanded state of a folder.
        """
        if folder_name in self.expanded_folders:
            self.expanded_folders = [f for f in self.expanded_folders if f != folder_name]
        else:
            self.expanded_folders = self.expanded_folders + [folder_name]
        self.update()

    def is_folder_expanded(self, folder_name: str) -> bool:
        is_expanded = folder_name in self.expanded_folders
        return is_expanded

    def get_folder_icon(self, scope: str) -> str:
        if scope == "shared":
            return "folder-tree"
        return "folder"
    
    def set_folder(self, folder_name: str):
        if (folder_name == "no_folder_key"):
            self.app.folder_name = ""
            self.app.folder_slug = ""
            return

        self.app.folder_name = folder_name
        self.app.folder_slug = Folder.name_to_slug(folder_name)

        # Save the folder change
        with rx.session() as sess:
            folder_id = None
            if self.app.folder_name:
                f = self._get_agents_folder()
                if f:
                    folder_id = f.id
            self._agent.update_from_state(self.app, folder_id, self.doc_indexes)

            sess.add(self._agent)
            sess.commit()
            sess.refresh(self._agent)
            self.app.id = self._agent.id

            # POST new agent spec to the Engine
            self._agentsvc.save_agent(self._agent)
        
    
    @timeit
    def load_agents_list(self):
        logger.debug("Loading agents list")
        with rx.session() as sess:
            # Get all folders for the user
            folders = Folder.get_user_folders(sess, self.user.tenant_id, self.user.id)
            
            # Create a dictionary to store agents by folder
            agents_by_folder = defaultdict(list)
            
            # Get all agents for the user
            agents = Agent.agents_any_folder(sess, self.user.tenant_id, self.user.id)
            
            for agent in agents:
                folder_name = next((f.name for f in folders if f.id == agent.folder_id), "Uncategorized")
                folder_slug =  next((f.slug for f in folders if f.id == agent.folder_id), "")
                agent_state = AgentState.create(sess, agent, self._get_uitool_info)
                agent_state.folder_name = folder_name
                agent_state.folder_slu = folder_slug
                agents_by_folder[folder_name].append(agent_state)

            all_agents = []
            for folder in folders:
                folder_icon_tag="folder-tree" if folder.scope == "shared" else "folder"
                folder_header = AgentState.create_folder_header(folder.name, folder_icon_tag)
                all_agents.append(folder_header)
                all_agents.extend(agents_by_folder[folder.name])

            # Add uncategorized agents at the end
            if agents_by_folder["Uncategorized"]:
                uncategorized_header = AgentState.create_folder_header("Uncategorized", "folder")
                all_agents.append(uncategorized_header)
                all_agents.extend(agents_by_folder["Uncategorized"])

            self._agent_list = all_agents
            self.expanded_folders = []


    #--------------------------------------------------------------------------------------------------
    # This section is for Agent and chat specific in the editor page
    #--------------------------------------------------------------------------------------------------
    
    async def create_new_agent(self):
        if not hasattr(self, '_default_model'):
            self._default_model = "gpt-4o-mini"
        # Create the name as "Untitled Agent - " plus the current date like "June 05"
        name = "Untitled Agent - " + datetime.now().strftime("%B %d")
        self.app = AgentState(name=name, model=self._default_model, user_id=self.user.id)
        folder = self.lookup_folder()
        scope = "private"
        if folder:
            self.app.folder_name = folder.name
            self.app.folder_slug = folder.slug
            self.app.folder_id = folder.id
            self.app.scope = folder.scope
            scope = folder.scope
        else:
            self.app.folder_name = "Recent"
            self.app.folder_slug = ""
            self.app.folder_id = None
        self._agent = Agent(
            name=name,
            model=self.app.model, 
            user_id=self.user.id if self.user else "?",
            tenant_id=self.user.tenant_id if self.user else "?",
            updated_at=None,
            scope=scope,
        )
        if scope == 'private':
            self.app.index_list = PERSONAL_INDEX_NAME
        await self.save_agent()

    async def clear_agent_state(self):
        if not hasattr(self, '_default_model'):
            self._default_model = ""
        self.current_audio = ""
        self.app = AgentState(name="", model=self._default_model, user_id=self.user.id)

    async def confirm_app_clone(self):
        # Copy the current agent for the user and open the copy
        self.app_clone_modal_open = False
        with rx.session() as sess:
            new_agent = Agent(**self._agent.model_dump())
            new_agent.id = None
            new_agent.scope = "private"
            new_agent.user_id = self._user_id
            new_agent.name = "(copy) " + self.app.name
            sess.add(new_agent)
            sess.commit()
            sess.refresh(new_agent)
            for tool in self._agent.tools:
                new_tool = Tool(**tool.model_dump())
                new_tool.agent_id = new_agent.id
                new_tool.id = None
                sess.add(new_tool)
                sess.commit()
                sess.refresh(new_tool)
            sess.refresh(new_agent)
            return await self.goto_edit_app(new_agent.id, self.app.folder_name, agent_name=new_agent.name, success_modal_key="clone")

    async def app_run_page_load(self):
        await self.editor_page_load()
        chat_id = self.router.page.params.get("chat")
        if chat_id:
            self.click_runlist_cell(chat_id)
            for idx, run in enumerate(self._agent_runs):
                if str(run.id) == chat_id:
                    self.active_run_id = run.id
                    break
        return EditorState.bg_wait_for_runs  

    def set_app_value(self, attr: str, val: str):
        if attr == 'scope':
            val = "shared" if val else "private"
        elif attr == 'trigger':
            if "(" in val:
                self.app.trigger_prefix = val.split("(")[0].strip()
            else:
                self.app.trigger_prefix = val
        setattr(self.app, attr, val)
        self.app_modified = True

    async def change_model(self, model: str):
        self.app.model = model
        self.run_model = model
        self.app_modified = True
        await self._save_agent(False)

    async def reflect_chat(self):
        if self.__run is None:
            return
        
        self.processing = True
        try:
            # Get reflection result
            yield
            reflection_result = self._agentsvc.reflect(str(self.__run['id']), self._user_id)
            
            # Initialize facts as empty list
            facts = []
            
            # Parse reflection result based on type
            if hasattr(reflection_result, 'facts') and hasattr(reflection_result, 'token_usage'):
                # Handle ReflectionResult object
                facts = reflection_result.facts
                self.reflect_modal_analysis = reflection_result.analysis
                token_usage = reflection_result.token_usage
                self.reflect_modal_total_tokens = token_usage.get("total_tokens", 0)
                self.reflect_modal_prompt_tokens = token_usage.get("prompt_tokens", 0)
                self.reflect_modal_completion_tokens = token_usage.get("completion_tokens", 0)
            elif isinstance(reflection_result, dict):
                # Handle dictionary response
                facts = reflection_result.get("facts", [])
                self.reflect_modal_analysis = reflection_result.get("analysis", "")
                token_usage = reflection_result.get("token_usage", {})
                self.reflect_modal_total_tokens = token_usage.get("total_tokens", 0)
                self.reflect_modal_prompt_tokens = token_usage.get("prompt_tokens", 0)
                self.reflect_modal_completion_tokens = token_usage.get("completion_tokens", 0)
            elif isinstance(reflection_result, list):
                # Handle legacy response format where result is just a list of facts
                facts = reflection_result
                self.reflect_modal_total_tokens = 0
                self.reflect_modal_prompt_tokens = 0
                self.reflect_modal_completion_tokens = 0
                self.reflect_modal_analysis = ""
            else:
                logger.error(f"Unexpected reflection result type: {type(reflection_result)}")
                facts = []
                
            if facts:  # Only show modal if we have facts
                logger.debug("Reflect result: ", facts)
                self.show_reflect_modal(facts)
            else:
                logger.warning("No reflection facts generated")
                # Optionally show a toast or other notification here
                
        except Exception as e:
            logger.error(f"An error occurred during reflection: {str(e)}")
            # Reset token counts on error
            self.reflect_modal_total_tokens = 0
            self.reflect_modal_prompt_tokens = 0
            self.reflect_modal_completion_tokens = 0
            self.reflect_modal_analysis = ""
            # Could show an error toast here
            import traceback
            traceback.print_exc()
        finally:
            self.processing = False
            
    def show_reflect_modal(self, reflect_result):
        """Show the reflection modal with the given results"""
        self.reflect_modal_open = True
        self.reflect_modal_result = reflect_result
        self.reflect_modal_checked = [True] * len(reflect_result)

    def close_reflect_modal(self):
        """Close the reflection modal and clean up state"""
        self.reflect_modal_open = False
        self.reflect_modal_result = []
        self.reflect_modal_checked = []
        self.reflect_modal_total_tokens = 0
        self.reflect_modal_prompt_tokens = 0
        self.reflect_modal_completion_tokens = 0

    @rx.var
    def reflection_cost(self) -> str:
        """Calculate the cost of reflection based on token usage"""
        costs = calc_tokens_cents("gpt-4o-mini", self.reflect_modal_prompt_tokens, self.reflect_modal_completion_tokens)
        dollars = (costs[0]/100.0) + (costs[1] / 100.0)
        return f"${dollars:.4f}"
        
    async def reset_chat(self):
        self.test_prompt = ""
        self.temp_upload_file = None
        self._clear_chats()
        self.show_welcome_message()
        self.__run = None
        self.active_run_id = None
        self.run_model = self.app.model
        if self._agent.uses_dynamic_tools():
            await self.auto_remove_tools()
        self.run_tools = self.app.uitools

    def _clear_chats(self):
        self.chats = []
        self.run_input_tokens = 0
        self.run_output_tokens = 0

    def _insert_agent_message(self, message, reset=False, special=""):
        if reset:
            self._clear_chats()
        self.chats.append(
            QA.with_answer(message, "", special=special)
        )
    
    def _get_agents_folder(self) -> UIFolder|None:
        return next(
            (uifolder for uifolder in self.folders if uifolder.name == self.app.folder_name), 
            None
        )

    #--------------------------------------------------------------------------------------------------
    # This section is for Memory specific in the editor page
    #--------------------------------------------------------------------------------------------------

    
    @rx.var
    def agent_memory_has_not_changed(self) -> bool:
        if len(self.agent_memories) != len(self.agent_memories_init):
            return False
        return all(
            mem[0] == init_mem[0] and mem[1] == init_mem[1] 
            for mem, init_mem in zip(self.agent_memories, self.agent_memories_init)
        )
    
    def on_change_memory(self, value: str, index: int):
        # Update the corresponding memory in the agent's memories
        memories = json.loads(self._agent.memories_json or "[]")
        memories[index]["memory"] = value

        # Update the agent's memories and the UI
        self._agent.memories_json = json.dumps(memories)
        self.sync_state_memory_from_agent(memories)

    def delete_memory(self, index: int):
        memories = json.loads(self._agent.memories_json or "[]")
        del memories[index]

        self._agent.memories_json = json.dumps(memories)
        self.sync_state_memory_from_agent(memories)

    def new_memory(self):
        # Get the current memories from the agent
        memories = self._agent.add_fact_as_memory("")
        self.sync_state_memory_from_agent(memories)

    async def agent_memories_click_cell(self, pos):
        col, row = pos
        if col == 1:  # click on checkbox
            memory_to_toggle = self.agent_memories[row][0]
            memories = json.loads(self._agent.memories_json or "[]")
            
            # Toggle the 'enabled' property of the memory
            for memory in memories:
                if memory['memory'] == memory_to_toggle:
                    memory['enabled'] = not memory.get('enabled', True)
                    break
            self._agent.memories_json = json.dumps(memories)
            self.sync_state_memory_from_agent(memories)

    def add_to_memory(self, memories: list[str]) -> list[dict]:
        logger.debug(f"Adding memories: {memories}")
        # Parse the existing memories_json
        if self._agent.memories_json:
            existing_memories = json.loads(self._agent.memories_json or "[]")
        else:
            existing_memories = []

        # Get the current timestamp
        current_timestamp = int(datetime.now().timestamp())

        # Create new memory entries
        new_memories = [{"memory": memory, "ts": current_timestamp, "enabled": True} for memory in memories]

        # Append the new memories to the existing memories
        updated_memories = existing_memories + new_memories

        # Update the memories_json field with the updated memories
        self._agent.memories_json = json.dumps(updated_memories)
        return updated_memories

    def sync_state_memory_from_agent(self, memories, set_init_memories: bool = False):
        self.agent_memories = [
            [memory['memory'], memory.get('enabled', True)]
            for memory in memories
        ] 

        if set_init_memories:
            self.agent_memories_init = self.agent_memories  
    
    async def on_agent_saved(self):
        try:
            self.run_tools = self.app.uitools # assume that Run will be forced to reflect the Agent's current tools
            if self._agent is not None:
                memories = json.loads(self._agent.memories_json or "[]")
                self.sync_state_memory_from_agent(memories, set_init_memories=True)
        except Exception as e:
            print(e)
        
    async def save_agent(self):
        await self._save_agent()

    async def _save_agent(self, visible_update: bool=True, skip_agents: bool=False):
        # Update Agent model and save it
        last_update = self._agent.updated_at
        with rx.session() as sess:
            if self._agent.user_id is None or len(self._agent.user_id) < 3:
                # Workaround bug where New page is loaded before login
                self._agent.user_id = self.user.id
            folder_id = None
            f = self._get_agents_folder()
            if f:
                folder_id = f.id
            self._agent.update_from_state(self.app, folder_id, self.doc_indexes)
            sess.add(self._agent)
            sess.commit()
            sess.refresh(self._agent)
            self.app.id = self._agent.id

            # Create a proper Tool record which connects a ToolFactory reference
            # to its resolved credential.
            keep: bool
            for tool, keep in self._agent.resolve_tools(
                self.app.uitools,
                ):
                if keep:
                    if (
                        tool.credential_id is None and 
                        not tool.tool_factory_id.startswith("agent:")
                    ):
                        logger.debug(f"!!!!!!!!! WARNING TOOL {tool.tool_factory_id} HAS NO CREDENTIAL")
                    logger.debug("Keeping tool: ", tool)
                    sess.add(tool)
                else:
                    logger.debug("Discarding tool: ", tool)
                    sess.delete(tool)
            sess.add(self._agent)
            sess.commit()
            sess.refresh(self._agent)
            # update tool_ids on our UITools, assuming factory_ids are unique
            for uitool in self.app.uitools:
                if uitool.tool_id is None:
                    dbtool = next((t for t in self._agent.tools if t.tool_factory_id == uitool.tool_factory_id), None)
                    if dbtool is not None:
                        uitool.tool_id = dbtool.id

            # POST new agent spec to the Engine
            if not skip_agents:
                self._agentsvc.save_agent(self._agent, self.__run.get('id') if self.__run else None)

            await self.on_agent_saved()

            self.app_modified = False

        if visible_update:
            await self.set_agent_list_dirty()
            tools = [t.name for t in self.app.uitools]
            self._insert_agent_message(
                f"(New agent created, model: {self.app.model}, with tools: {','.join(tools)})",
                reset=False,
            )
    
    async def quiet_save_agent(self):
        with rx.session() as sess:
            sess.add(self._agent)
            sess.commit()
            sess.refresh(self._agent)
            self.app.id = self._agent.id

    def show_welcome_message(self):
        welcome = self.app.welcome_message
        if welcome:
            self._insert_agent_message(welcome, special="welcome")


    async def set_agent_list_dirty(self):
        from .index_state import IndexState
        index_state = await self.get_state(IndexState)
        index_state.agent_list_dirty = True
        logger.debug("Set agent list to dirty")

    def get_credential_map(self) -> dict[str,LocalCred]:
        return {cred.system_name: cred for cred in self.mycredentials}
    
    async def clear_run(self):
        if self.__run:
            await pubsub.cancel_subscriber(
                self.router.session.client_token,
                self.__run["logs_channel"],
            )
            self.__run = None
            self.active_run_id = None

    async def unmount_chat(self):
        if self.__run and self.__run.get("logs_channel"):
            await pubsub.cancel_subscriber(
                self.router.session.client_token,
                self.__run["logs_channel"],
            )

    async def call_engine_service(self, form_data: dict[str, str]):
        try:
            res = await self.__call_engine_service(form_data)
            if res:
                return [rx.call_script("window.setupChatScrolling()"), res, rx.clear_selected_files("upload_chat")]
            else:
                return [rx.call_script("window.setupChatScrolling()"), rx.clear_selected_files("upload_chat")]
        except Exception as e:
            traceback.print_exc()
            self.processing = False
            return rx.toast.error(str(e))

    async def send_a_prompt(self, prompt: str, index: int):
        prompt = f"[{index+1}] {prompt}"
        try:
            res = await self.__call_engine_service({"question":prompt})
            if res:
                return [rx.call_script("window.setupChatScrolling()"), res]
            else:
                return [rx.call_script("window.setupChatScrolling()")]
        except Exception as e:
            traceback.print_exc()
            self.processing = False
            return rx.toast.error(str(e))

    async def __call_engine_service(self, form_data: dict[str, str]):
        # Get the question from the form
        question = form_data["question"]

        # Get user timezone from the form
        user_timezone = form_data.get("timezone", "UTC") # default this as sometimes can't find in form

        # Check if the question
        if question == "":
            return
        return await self.handle_command(question, user_timezone)

    async def handle_command(self, text, user_timezone: str | None):
        command = route_command(text)
        match command:
            case RunAgentWithInput(input=input_text):
                return EditorState.handle_run_agent_with_input(input_text, user_timezone)
            case AddMemories(memories=memories_list):
                self.add_to_memory(memories_list)
                await self.save_agent()
                await self.editor_page_load()
            case Reflect():
                await self.reflect_chat()
            case _:
                print("Unknown command")
                # Handle unknown commands or raise an exception

    async def handle_run_agent_with_input(self, question: str, user_timezone: str | None = None):
        if self._agentsvc is None:
            print("Authed user is: ", self.authenticated_user)
            yield rx.redirect(self.router.page.raw_path)
            return
        if self.app_modified:
            await self._save_agent(visible_update=False)

        self.service_status = ""
        was_processing = self.processing
                  
        self.processing = True
        self.test_prompt = ""
        
        qa = QA(question=question or "", user_name=self.authenticated_user.name or "No name")
        qa.answers.append(Answer())
        self.chats.append(qa)
        yield
   
        attached_file = None
        # If the user uploaded a file with the chat, tell the LLM in the prompt
        if self.temp_upload_file:
            attached_file = self.temp_upload_file
            question = f"uploaded file:: uploads/{attached_file}\n{question}"
            # clear the upload file field here early so it doesn't get left around if there's an error
            self.temp_upload_file = None

        # Call the engine service to create a new Run. We keep
        # this until the agent config changes, or we Reset, and then
        # we create a new one. When create a random logs channel
        # when we create a new Run to receive its events.

        # Note that inside self.click_runlist_cell we query an existing
        # run which may be re-used here.
        if self.__run is None:
            try:
                try:
                    self.__run = self._agentsvc.create_run(
                        tenant_id=self.user.tenant_id, 
                        user_id=self.user.id, 
                        agent=self._agent,
                        logs_channel="logs:" + self._agent.name[0:15] + uuid4().hex,
                    )
                    # A new run should take the tools from 
                    print("New run: ", self.__run)
                    self.run_tools = UITool.from_api_run_tools(self.__run.get("tools"))
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 401:
                        # This shouldn't happen, but put in a catch here to try and recover
                        self._agentsvc.user_login(
                            self.user.tenant_id, 
                            self.user.id,
                            name = self.user.name,
                            user_email = self.user.emailval,
                            timezone = None, # need to keep user timezone somewhere
                        )
                        raise
                    
                    if e.response.status_code == 404:
                        # Agent not posted to the backend end
                        await self._save_agent(visible_update=False)
                        self.__run = self._agentsvc.create_run(
                            tenant_id=self.user.tenant_id, 
                            user_id=self.user.id, 
                            agent=self._agent,
                            logs_channel="logs:" + self._agent.name[0:15] + uuid4().hex,
                        )
                    else:
                        raise
                if self._check_run_failed():
                    return

                self.run_model = self._agent.model

        
            except Exception as e:
                traceback.print_exc()
                self._cleanup_run_failed(str(e))
                return

        await pubsub.create_subscriber(
            self.router.session.client_token,
            self.__run["logs_channel"]
        )

        self._agentsvc.send_input(self.__run["id"], question, attached_file)
        if self._check_run_failed():
            return
        
        self.question = ""

        if not was_processing:
            print("Processing was false, so starting background event listener")
            # FIXME: we have a race condition where our background thread doesn't subscribe to Redis
            # in time to receive the first event. We should probably do the subscribe here in the foreground
            # thread BEFORE we start the background reading of events.
            yield EditorState.wait_for_agent_events
        else:
            print("Processing was true, so skipping background event listener")
            return

    @rx.background
    async def wait_for_agent_events(self):
        print("Starting background event listener: ", datetime.now())
        async for event in self.read_engine_events(self.__run["logs_channel"]):
            async with self:
                runlog = RunLogBase.model_validate(event)
                await self.render_run_event(runlog, live=True)
                if self.processing == False:
                    break

        async with self:
            print("------- DONE READING EVENTS ----------")
            self.processing = False
            self.finish_chat_render()
        return [EditorState.bg_load_runs, rx.call_script("window.grabPromptFocus();")]

    def cancel_agent_run(self):
        print("!!!! CANCELING AGENT !!!!")
        self.processing = False
        if self.__run:
            self._agentsvc.cancel_run(self.__run['id'])

    def _check_run_failed(self):
        if self._agentsvc.status_message:
            return self._cleanup_run_failed()
        else:
            return False

    def _cleanup_run_failed(self, error_msg = None) -> bool:
        self.service_status = error_msg or self._agentsvc.status_message
        print("After cleanup service status is : ", self.service_status)
        self.__run = None
        if len(self.chats) > 0 and self.chats[-1].question == "":
            self.chats.pop()
        if len(self.chats) > 0:
            self.chats[-1].answers[-1].output += GENERATION_COMPLETE_MARK

        self.processing = False
        return True


    def filter_metacommands_tooltip(self, text):
        if text.startswith("/"):
            self.filtered_commands = [cmd for cmd in COMMANDS if cmd.startswith(text) and cmd != text]
        else:
            self.filtered_commands = []

    #--------------------------------------------------------------------------------------------------
    # This section is for chat window display of events from the self._agentsvc in the editor page
    #--------------------------------------------------------------------------------------------------
    
            
    def find_last_json(self, text):
        """
        Finds the last JSON object in a string and returns:
        everything before it as the before_part,
        the JSON string itself as the json_part,
        and everything after it as the after_part.
        Ignores singleton lists.
        
        Args:
            text (str): The input text containing JSON.
        Returns:
            tuple: A tuple containing the before_part, json_part, and after_part.
        """
        last_brace_index = text.rfind('}')
        last_bracket_index = text.rfind(']')
        
        if last_brace_index == -1 and last_bracket_index == -1:
            return text, None, ""  # No JSON found
        
        end_index = max(last_brace_index, last_bracket_index) + 1
        stack = []
        
        for i in range(end_index - 1, -1, -1):
            char = text[i]
            if char in '}]':
                stack.append(char)
            elif char in '{[':
                if stack and ((char == '{' and stack[-1] == '}') or (char == '[' and stack[-1] == ']')):
                    stack.pop()
                    if not stack:
                        potential_json = text[i:end_index].strip()
                        
                        # Check for singleton list
                        if potential_json.startswith('[') and potential_json.endswith(']'):
                            content = potential_json[1:-1].strip()
                            if ',' not in content:  # It's a singleton list
                                continue
                        
                        try:
                            parsed_json_dict = self.try_parsing_json(potential_json)
                            if parsed_json_dict:
                                before_json = text[:i].strip()
                                after_json = text[end_index:].strip()
                                return before_json, parsed_json_dict, after_json
                        except json.JSONDecodeError as e:
                            print(f"JSON decoding failed: {str(e)} from string {potential_json[0:420]}")
                            continue
        
        return text, None, ""  # No valid JSON found

    def parse_simple_list(self, input_string: str) -> dict:
        """
        Parse a string representation of a list into a hierarchical dictionary.
        
        Args:
            input_string (str): The string representation of the list.
        
        Returns:
            dict: The parsed list as a hierarchical dictionary.
        """
        parsed_list, _ = self._parse_list_helper(input_string)
        return self._convert_to_hierarchical_dict(parsed_list)

    def _convert_to_hierarchical_dict(self, lst: list) -> dict:
        """
        Convert a nested list into a hierarchical dictionary.
        
        Args:
        
            lst (list): The list to convert.
        
        Returns:
            dict: The hierarchical dictionary representation of the list.
        """
        result = {}
        for i, item in enumerate(lst):
            if isinstance(item, list):
                result[f"item_{i}"] = self._convert_to_hierarchical_dict(item)
            else:
                result[f"item_{i}"] = item
        return result

    def _parse_list_helper(self, input_string: str, start: int = 0) -> tuple[list, int]:
        """
        Helper function to recursively parse lists, including nested lists.
        
        Args:
            input_string (str): The string representation of the list.
            start (int): The starting index for parsing.
        
        Returns:
            tuple[list, int]: The parsed list and the index where parsing ended.
        """
        result = []
        current_item = ""
        i = start
        
        while i < len(input_string):
            char = input_string[i]
            
            if char == '[':
                # Start of a nested list
                nested_list, new_i = self._parse_list_helper(input_string, i + 1)
                result.append(nested_list)
                i = new_i
            elif char == ']':
                # End of the current list
                if current_item:
                    result.append(self._parse_item(current_item))
                return result, i
            elif char == ',':
                # End of an item
                if current_item:
                    result.append(self._parse_item(current_item))
                    current_item = ""
            else:
                current_item += char
            
            i += 1
        
        if current_item:
            result.append(self._parse_item(current_item))
        
        return result, i

    def _parse_item(self, item: str):
        """
        Parse an individual item from the list.
        
        Args:
            item (str): The string representation of an item.
        
        Returns:
            The parsed item (str, int, float, or None).
        """
        item = item.strip()
        if item.lower() == 'none':
            return None
        try:
            return int(item)
        except ValueError:
            try:
                return float(item)
            except ValueError:
                # Remove quotes if present
                return item.strip("'\"")
            
    def try_parsing_json(self, input_string):
        """
        Attempts to parse a string as JSON. If it fails, attempts to parse it as a Python dictionary.

        Args:
            input_string (str): The input string to parse.

        Returns:
            dict or list: The parsed JSON/dict object.
        """
        # Check if input_string is a simple list
        if input_string.startswith('[') and input_string.endswith(']') and not re.search(r'[{}]', input_string):
            try:
                parsed = self.parse_simple_list(input_string)
                return parsed
            except (ValueError, SyntaxError):
                return None
        
        # Try to parse as JSON first
        try:

            parsed = json.loads(input_string)
            #print("Successfully parsed as JSON!")
            return parsed
        except json.JSONDecodeError:
            # If JSON parsing fails, try to parse as a Python dict
            try:
                parsed = ast.literal_eval(input_string)
                return parsed
            except (ValueError, SyntaxError):
                return None
            
    def fix_json_string(self, input_string):
        """
        Cleans and fixes common issues in a JSON string to make it JSON-decodable.

        Args:
            input_string (str): The input JSON string.

        Returns:
            str: The cleaned JSON string.
        """
        #print(f"Original JSON string: {input_string}")

        # Remove any leading/trailing whitespace and quotes
        input_string = input_string.strip().strip('"')
        #print(f"After removing leading/trailing whitespace and quotes: {input_string}")
        
        # Replace escaped newlines with actual newlines
        input_string = input_string.replace('\\n', '\n')
        #print(f"After replacing escaped newlines: {input_string}")
        
        # Replace unescaped newlines within JSON values with space
        input_string = re.sub(r'(?<!\\)\n', ' ', input_string)
        #print(f"After replacing unescaped newlines within JSON values: {input_string}")

        # Replace single quotes with double quotes for keys
        input_string = re.sub(r"(?<!\\)'(?=\w+:)", '"', input_string)
        #print(f"After replacing single quotes with double quotes for keys: {input_string}")

        # Replace single quotes with double quotes for values
        input_string = re.sub(r'(:\s*)\'(.*?)\'', r'\1"\2"', input_string)
        #print(f"After replacing single quotes with double quotes for values: {input_string}")

        # Correctly handle embedded single quotes within values by escaping them
        def escape_single_quotes(match):
            return match.group(1) + match.group(2).replace("'", "\\'") + match.group(3)
        
        input_string = re.sub(r'(".*?":\s*")([^"]*?)(".*?")', escape_single_quotes, input_string)
        #print(f"After escaping embedded single quotes within values: {input_string}")
        
        # Remove invalid escape sequences like \ at the end of the string
        input_string = re.sub(r'\\$', '', input_string, flags=re.MULTILINE)
        #print(f"After removing invalid escape sequences: {input_string}")
        
        # Correctly handle escaped double quotes within values
        input_string = re.sub(r'\\\\', r'\\', input_string)
        input_string = re.sub(r'\\"', r'"', input_string)
        #print(f"After handling escaped double quotes: {input_string}")
        
        # Remove invalid control characters
        input_string = re.sub(r'[\x00-\x1f\x7f]', '', input_string)
        #print(f"After removing invalid control characters: {input_string}")
        
        # Replace NaN with null to make JSON valid
        input_string = re.sub(r'\bNaN\b', 'null', input_string)
        #print(f"After replacing NaN with null: {input_string}")

        return input_string

    def _append_json_output(self, answer: Answer, error_flag: bool) -> bool:
        """
        Attempts to parse and append JSON output to the answer.
        Args:
            answer (Answer): The answer object to update.
            error_flag (bool): Indicates if an error occurred during tool run.
        Returns:
            bool: True if JSON was successfully parsed and appended, False otherwise.
        """
        before_json, parsed, after_json = self.find_last_json(answer.tool_output)
        
        if parsed:
            try:
                # Ensure the parsed result is a dictionary or a list of dictionaries
                if isinstance(parsed, dict):
                    answer.tool_json = parsed
                elif isinstance(parsed, (list, tuple)) and all(isinstance(item, dict) for item in parsed):
                    merged_dict = {f"item_{idx}": item for idx, item in enumerate(parsed)}
                    answer.tool_json = merged_dict
                else:
                    print(f"Parsed data is not a dictionary or list/tuple of dictionaries: {type(parsed)}")
                    return False
                #print(f"=================> before = {before_json}")
                #print(f"=================> after = {after_json}")
                answer.before_json    = before_json
                answer.after_json     = after_json
                answer.object_results = True
                answer.error_flag     = error_flag
                return True
            except Exception as e:
                print(f"\n------> Got exception: {e} during parsing")
        else:
            pass
        return False
    
    def _extract_xml_from_json(self, text) -> str:
        # Regex pattern to extract the XML part from a JSON string
        match = re.search(r"\{'xml': '(.*?)'\}⋼", text, re.DOTALL)
        if match:
            xml_content = match.group(1)
            # Replace escaped newlines and other unnecessary escape sequences
            xml_content = xml_content.replace("\\n", "").replace("\\", "")
            return xml_content
        else:
            return ""  # No XML found in the text
     
    def _append_xml_output(self, answer:Answer,  error_flag: bool) ->bool:
       if re.search(r"<\?xml version", answer.tool_output):
            try:
                xml_content = self._extract_xml_from_json(answer.tool_output)
                answer.tool_xml = xml_content
                answer.xml_results = True
                answer.error_flag = error_flag
                #print(f"----> XML Output: { answer.tool_xml}")
                return True
            except Exception as e:
                print(f"State: tool output xml: An error occurred: {e}")
       return False

    def is_audio(self, answer:Answer):
        try:
            return answer.tool_json.get("content_type") == 'audio/mpeg'
        except Exception as e:
            print(f"State: is_audio: An error occurred: {e}")
        return False
    
    def _append_audio_output(self, answer: Answer) -> bool:
        try:
            answer.audio_results = True
            try:
                answer.raw_audio_url = answer.tool_json.get("audio_url").get("url")
            except:
                answer.raw_audio_url = answer.tool_json.get("audio_url")
            audio_id = f"audio_{hash(answer.raw_audio_url)}"
            #
            # Below is the little player embedded in the chat. And some javascript
            # that remembers that we want to play this file even if another is currently
            # playing.
            #
            answer.audio_url = f"""
            <audio id="{audio_id}" controls style="width: 300px; height: 25px; border-radius: 20px;">
                <source src="{answer.raw_audio_url}" type="audio/mpeg">
                Your browser does not support the audio element.
            </audio>
            <script>
                window.addToAudioQueue('{answer.raw_audio_url}');
            </script>
            """
            #
            # And here is the global player right under the chat winow.
            #
            if not self.loading_run_logs:
                print(f"loading the SYNC audio player with {answer.raw_audio_url}")
                self.current_audio = answer.raw_audio_url
                self.synchronized_audio_html = f"""
                    <audio
                        id="sync-audio-player"
                        controls
                        style="width: 250px; height: 20px; border-radius: 15px;"
                        data-current-audio="{self.current_audio}"
                        <source src="{self.current_audio}" type="audio/mpeg">
                    >
                        Your browser does not support the audio element.
                    </audio>
                """
            return True
        except Exception as e:
            print(f"State: tool output xml: An error occurred: {e}")
        return False
    
    def _append_tool_output(self,
                            event:      dict,
                            output:     str,
                            error_flag: bool,
                            at_time: datetime|None = None) -> None:
        """
        Appends tool output to the relevant answer block in the chat history, handling both JSON and XML data.

        This function checks for the presence of a 'lc_run_id' in the event and matches it with an answer block
        in the chat history. It appends the new output to the existing tool output and tries to detect and
        format JSON and XML data.

        Args:
            event (dict): An event dictionary containing metadata and identifiers.
            output (str): The raw output string from the tool that needs to be appended and formatted.
            error_flag (bool): A flag indicating whether the tool execution resulted in an error.

        Process:
            1. Identifies the correct answer block using 'lc_run_id'.
            2. Appends raw output to the existing content.
            3. Detects and formats JSON data:
               - Tries to parse and reformat the JSON for better readability.
            4. Detects and formats XML data:
               - Converts XML string to an ElementTree, then to a prettified string.
            5. Updates the chat history to reflect changes.

        Returns:
            None: This function directly modifies the chat history state.
        """
        if 'lc_run_id' in event:
            lc_run_id = event['lc_run_id']
            answer = self._search_for_answer(lc_run_id)
            if not answer:                                 # some old history the tool output comes back without tool call
                if self.chats[-1].answers[-1].output == "":
                    # If empty, use the existing last answer
                    #Colors.printc(f"tool call and last answer empty{self.chats} :", Colors.OKBLUE)
                    answer = self.chats[-1].answers[-1]
                else:
                    # If not empty, create a new Answer object
                    answer = Answer()
                    # Append the new Answer to the current chat's answers
                    self.chats[-1].answers.append(answer)
                answer.lc_run_id = lc_run_id
            else:
                # calc tool execution time
                if at_time and answer.timestamp:
                    answer.tool_time = f"{(at_time - answer.timestamp).total_seconds():.2f}"
                    
            if answer and not answer.hide_function_call:
                output = re.sub(r'__END__$', '', output)
                answer.tool_output += output
                # Handle JSON output
                if not self._append_json_output(answer,error_flag):
                    # Handle XML output
                    if not self._append_xml_output(answer,error_flag):
                        # handle text output
                        pass
                # switch on the type of JSON output
                else:
                    if self.is_audio(answer):
                        # Handle Audio output
                        self._append_audio_output(answer)
                if answer.tool_output == "":
                    answer.tool_output = " "
                self.dirty_vars.add("chats")
                return
            else:
                print("!%!%!%!%!% Cant find answer for tool output: ", self.chats)
        else:
            print("No lc_run_id in event: ", event)

    def _search_for_answer(self, lc_run_id: str|None) -> Answer|None:
        for qa in reversed(self.chats):
            for answer in reversed(qa.answers):
                if answer.lc_run_id == lc_run_id:
                    return answer
        return None

    def format_tool_call(self, answer: Answer, details: dict[str, Any]) -> str:
        function_name = details["name"]
        parameters    = details["data"]

        # Convert parameters to a dictionary if it is a string
        if isinstance(parameters, str):
            try:
                parameters = eval(parameters) if parameters.startswith("{") else json.loads(parameters)
            except (json.JSONDecodeError, SyntaxError) as e:
                #print(f"Error decoding JSON: {e} params = {parameters}")
                parameters =  {"unexpected response": f"{parameters}"}

        # Check if parameters is already a dictionary
        if not isinstance(parameters, dict):
            raise ValueError("The 'data' field in details must be a dictionary")
        
        # Check if the first key is "script" and set is_script field
        if parameters and (list(parameters.keys())[0] == "script" or
                           list(parameters.keys())[0] == "code"):
            #print(f"------------------------>> parameters are: {parameters}")
            answer.is_script = True
            answer.code = list(parameters.values())[0]
        else:
            answer.is_script = False
            
        #answer.output = "Using: " + function_name + " - " + ", ".join(parameters.keys())
        answer.output = "Using: " + function_name
        #try:
        #    parsed = json.loads(parameters)
        #except:
        #    parsed = ast.literal_eval(parameters)
        answer.param_json = parameters
        #print(f"-----> param json = {answer.param_json}")
        answer.is_tool_call     = True
        
        
    def hidden_function_call(self, details: dict[str, Any]) -> bool:
        # Extract the function name from the details dictionary
        function_name = details.get("name", "")

        # Check if the function name ends with an underscore
        return function_name.endswith("_")

    @staticmethod          

    @staticmethod
    def detect_markdown_table(answer: Answer) ->bool:
        """
        Detects the presence of a Markdown table in the 'output' field of the Answer object
        and returns the start position of the Markdown table.

        Args:
            answer (Answer): An object containing the output text and table detection results.

        Returns:
            Optional[int]: The start position of the Markdown table if detected, else None.
        """
        lines = [line.strip() for line in answer.output.split('\n')]

        header_pattern = r'^\|(\s*[^|\n]*\s*\|)+\s*$'
        delimiter_pattern = r'^\|(\s*:?-+:?\s*\|)+\s*$'

        for i in range(len(lines) - 1):
            if re.match(header_pattern, lines[i]):
                if re.match(delimiter_pattern, lines[i + 1]):
                    answer.table_results = True
                    answer.table_start = answer.output.find(lines[i])
                    return True

        return False
    
    @staticmethod            
    def parse_markdown_table(answer: Answer, md_table: str):
        """ Parse out the header and rows of a markdown table that is
            arriving from the LLM or another place. Handles prefix text
            before the table and postfix text.sets flags for Reflex code
            to present table with Table container component.
        """
        if not answer.table_output: # this is the first time through
            # Find the start of the table by locating the first pipe symbol
            start_of_table = answer.table_start
            if start_of_table > 0:
                answer.prefix = answer.output[:start_of_table]
                answer.table_output = answer.output[start_of_table:] #+ md_table
                #print(f"/////////////////// answer prefix had {answer.prefix} \\\\\\\\\\\\\\\\\\\\\\")
                #print(f"/////////////////// answer table had {answer.table_output} \\\\\\\\\\\\\\\\\\\\\\")
            else:
                start_of_table = md_table.find('|')   # FIXME, this won't work if there are any other |'s
                                                      #        earlier in the output
                answer.table_output = md_table[start_of_table:]
                answer.prefix = answer.output +  md_table[:start_of_table]
        else:
            answer.table_output += md_table  # Append new incoming table data to the buffer

        # Split the buffered data into lines and attempt to detect table boundaries
        lines = answer.table_output.split('\n')
        
        # Reset headers and rows to build them from scratch
        answer.headers = []
        answer.rows = []

        reading_table = False
        table_started = False
        postscript_started = False

        for line in lines:
            line = line.strip()
            #print(f"!!!!!!!!!!! parse mark down line ( {line} ) !!!!!!!!!!!")
            if '|' in line:
                if not table_started:  # This line is the header line
                    answer.headers = line.strip('|').split('|')
                    answer.headers = [header.strip() for header in answer.headers]
                    table_started = True
                    reading_table = True
                elif '-' in line and not line.replace('|', '').replace('-', '').strip():
                    # this is the Alignment line
                    continue  # Skip alignment line
                else:
                    row_data = line.strip('|').split('|')
                    row_data = tuple(data.strip() for data in row_data)
                    answer.rows.append(row_data)
            else: # this is the end of the table
                #print("!!!!!!! Reached the end of the table !!!!!!!!!!")
                if table_started and not postscript_started:
                    postscript_started = True
                    if reading_table:
                        reading_table = False
                        answer.postscript = line
                    else:
                        answer.postscript += '\n' + line
                    #print(f"############ {answer.postscript} #############")
                    answer.table_complete = True
                elif not table_started:
                    # not actually the end of the table
                    # but some multi-line prefix before the table
                    answer.prefix += '\n' + line if answer.prefix else line
                else:
                    answer.postscript += '\n' + line
                    #print(f"#####OO##### {answer.postscript} ######OO#####")
                    
        answer.table_results = True           # tell the reflex code that this answer has a table
        answer.table_size = len(answer.rows)  # number of rows. When it gets to a certain size, pagination starts.
    
    def render_LLM_output(self, content: str, elapsed: float, lag: float):
        answer = self.chats[-1].answers[-1]
        answer.output += content
        elapsed_label = f"{elapsed:.2f}s"
        #if lag > 0.0:
        #    elapsed_label += f" (lag: {lag:.2f}s)"
        answer.elapsed_time = elapsed_label
        if EditorState.detect_markdown_table(answer):
            EditorState.parse_markdown_table(answer, content)
        return answer
            
    def render_error_output(self, event: dict):
        """ render errors that come back from tool execution or just from the LLM running """
        try:
            # Attempt to parse the event content as JSON
            details = json.loads(event['content'])
            print("TOOL ERROR JSON output:", details)
        except json.JSONDecodeError:
            # Handle cases where the error is not part of a tool running (e.g., direct LLM error)
            print(f"LLM ERROR string OUTPUT = {event['content']}")
            answer = self.chats[-1].answers[-1]
            answer.output += event['content']
            answer.error_flag = True
            return
        except Exception as e:
            # Handle any other exceptions that may occur during parsing
            print(f"An error occurred: {e}")
            return

        # If we reach here, JSON parsing was successful

        # Check if the last answer in the current chat is empty
        if self.chats[-1].answers[-1].output == "":
            # If empty, use the existing last answer
            a = self.chats[-1].answers[-1]
        else:
            # If not empty, create a new Answer object
            a = Answer()
            # Append the new Answer to the current chat's answers
            self.chats[-1].answers.append(a)
        # FIXME: this is probably an incorrect way to format the error
        # Format the tool output and set it as the answer's output
        self.format_tool_call(a, details)
        # Mark this answer as an error
        a.error_flag = True

        # If 'lc_run_id' is present in the event, set it for the answer
        if 'lc_run_id' in event:
            a.lc_run_id = event['lc_run_id']

        # Append a new empty Answer to the current chat's answers
        self.chats[-1].answers.append(Answer())

    def render_tool_call(self, content: str, lc_run_id: str|None, at_time: datetime|None = None):
        # Parse the content of the event as JSON
        if isinstance(content, dict):
            details = content
        else:
            details = json.loads(content)

        # Check if the last answer in the current chat is empty
        if self.chats[-1].answers[-1].output == "":
            # If empty, use the existing last answer
            #Colors.printc(f"tool call and last answer empty{self.chats} :", Colors.OKBLUE)
            a = self.chats[-1].answers[-1]
        else:
            # If not empty, create a new Answer object
            a = Answer()
            # Append the new Answer to the current chat's answers
            self.chats[-1].answers.append(a)
        
        a.hide_function_call = self.hidden_function_call(details)
        a.timestamp = at_time
        # Format the tool output and set it as the answer's output
        self.format_tool_call(a, details)
        # If 'lc_run_id' is present in the event, set it for the answer
        #Colors.printc(f"tool call and lc_run_id = {lc_run_id}", Colors.OKBLUE)
        if lc_run_id:
            a.lc_run_id = lc_run_id
        else:
            pass
            #Colors.printc(f"tool call and lc_run_id = {lc_run_id}", Colors.OKRED)
        # Append a new empty Answer to the current chat's answers
        self.chats[-1].answers.append(Answer())
        
    async def render_run_event(self, runlog: RunLogBase, live: bool):
        logger.debug(f">> {runlog.type} >> ", runlog, "\n<<\n")
        agevent: AgentEvent = EventRegistry.get_event(runlog)
        agevent.live = live

        # NOTE:
        # For now we are simply publishing ToolEvent and ToolLogEvents from sub-agents, so there
        # is no need to support special subagent events.

        # NOTE on timing
        # Agent events are all timestamped, so we can see timings and elapsed time as far as the
        # agent execution. But when we are running live we also want to see if the UI is "lagging"
        # in processing events, so we calculate "lag" as the time we process the event minus its
        # timestamp (we have to assume clocks are reasonably in sync).

        def get_username(agevent: AgentEvent) -> str:
            if agevent.user_id == str(self.authenticated_user.id):
                # normal case of current user in the chat
                return self.authenticated_user.name or "?"
            else:
                with rx.session() as sess:
                    user = AgentState._lookup_db_user(agevent.user_id, sess)
                    print("Got user back: ", user)
                    return user.name or "?"

        match agevent:
            case AgentInputEvent():
                self._turn_started = runlog.created_at or datetime.utcnow()
                if self.chats[-1].question == "":
                    self.chats[-1].question = agevent.prompt
                    self.chats[-1].user_name = get_username(agevent)
                else:
                    # For "responsive" appeal we show the input message *ourselves* rather than 
                    # waiting on the <input> event from the agent. So generally we don't need to 
                    # handle this input event at all.
                    if self.chats[-1].question != agevent.prompt:
                        # Super hack. We should have a better way to signal inputs we want to hide
                        if not agevent.prompt.startswith("uploaded file::"):
                            self.chats.append(
                                QA(question=agevent.prompt, user_name=get_username(agevent), answers=[Answer()])
                            )
            
            case AgentOutputEvent():
                # calc elapsed time from prompt start
                elapsed = (runlog.created_at or datetime.utcnow()) - self._turn_started

                lag = 0
                if live and runlog.created_at:
                    # calc if we are receiving/processing events behind real time
                    lag = (datetime.utcnow() - runlog.created_at).total_seconds()
                self.render_LLM_output(agevent.str_result, elapsed.total_seconds(), lag)
            
            case ToolEvent():
                self.render_tool_call(
                    {"name": agevent.name, "data": agevent.tool_params},
                    agevent.lc_run_id,
                    at_time= runlog.created_at,
                )
            
            case ToolLogEvent():
                #print(f"++++++++> ToolLogEvent: { agevent.message}")
                self._append_tool_output(
                    dict(agevent),
                    agevent.message,
                    False,
                    at_time = runlog.created_at,
                )
            #case AudioStreamEvent():
            #    self.
            case AgentErrorEvent():
                self.render_error_output({"content":agevent.message}) # compat with the old style events
                self.cancel_agent_run()
            
            case ToolResultEvent():
                res = ""
                if isinstance(agevent.output_object, str):
                    res = agevent.output_object
                else:
                    res = json.dumps(agevent.output_object, indent=4)

                self._append_tool_output(
                    dict(agevent),
                    res,
                    False,
                    runlog.created_at,
                )
            
            case ToolEndEvent():
                self._append_tool_output(dict(agevent), GENERATION_COMPLETE_MARK, False)
            
            case TokenUsageEvent():
                usage = agevent.usage_metadata
                if 'input_tokens' in usage:
                    self.run_input_tokens += int(usage['input_tokens'])
                if 'output_tokens' in usage:
                    self.run_output_tokens += int(usage['output_tokens'])

            case RequestVarsEvent():
                print("!!!! GET RequestVarsEvent: ", agevent.var_names)
                if agevent.lc_run_id:
                    answer = self._search_for_answer(agevent.lc_run_id)
                    if answer:
                        print("Found the correct answer: ", answer)
                        answer.requested_var_names = agevent.var_names
                        self.dirty_vars.add("chats")
                    else:
                        print("!! Could not find the answer from lc_run_id: ", agevent.lc_run_id, " maybe a race condition?")
                else:
                    print("Agevent has no lc_run_id, just jamming it out there")
                    answer = self.render_LLM_output("(need info) ", 0, 0)
                    answer.requested_var_names = agevent.var_names

            case AddMemoryEvent():
                if agevent.live:
                    memories = self.add_to_memory([agevent.fact])
                    await self.quiet_save_agent()
                    self.sync_state_memory_from_agent(memories, True)

            case EnableToolEvent():
                # We could edit the Agent model, and then update the UI based on that.
                # But instead we create a UITool as if the tool had been added in the UI,
                # and let that code path edit the underlying agent.

                # We have 4 cases:
                # 1. Tool requires no auth. In that case we can just add it
                # 2. Tool requires auth, but we have no creds. We add the tool "provisionally" and open
                # the modal to create the Connection
                # 3. Tool requires auth, and we have 1 cred. In that case we add tool with that cred
                # 4. Tool requires auth, and we have multiple creds. In that case we "provisionally" 
                #  add the tool, and let the user create a Connection to fill in its cred
                # 

                async def add_tool(tf_dict: dict):
                    async def sync_add():
                        uitool = UITool.from_tool_factory_dict(tf_dict)
                        if self._agent.uses_dynamic_tools():
                            self.run_tools.append(uitool)
                        else:
                            self.app.uitools.append(uitool)
                            await self._save_agent(visible_update=False, skip_agents=True)
                    if not self._is_mutable():
                        async with self:
                            await sync_add()
                    else:
                        await sync_add()
                
                if agevent.live:
                    print("!!!GOT AN ENABLE TOOL EVENT: ", agevent.__dict__)
                    tf_dict = self._factory_id_map.get(agevent.tool_factory_id)
                    if tf_dict is None:
                        return

                    if tf_dict.get('auth_config', {}) == {}:
                        # Case 1 (no auth needed)
                        await add_tool(tf_dict)

                    else:
                        creds: list[LocalCred] = self.find_avail_credentials(tf_dict['id'])
                        if agevent.credential_id:
                            # If the event has a credential_id, it means the tool is being enabled
                            # with a specific credential
                            creds = [c for c in creds if c.id == agevent.credential_id]

                        if len(creds) == 0:
                            # Case 2 (auth needed, but no creds)
                            await self.prompt_for_new_connection(tf_dict['id'])
                        elif len(creds) == 1:
                            # Case 3 (auth needed, and we have 1 cred)
                            tf_dict['credential_id'] = creds[0].id
                            tf_dict['name'] = creds[0].name
                            await add_tool(tf_dict)
                        else:
                            # Case 4 (auth needed, and we have multiple creds)
                            try:
                                async with self:
                                    self.matching_connections = creds
                                    global_state: GlobalState = await self.get_state(GlobalState)
                                    global_state.open_modals['connections'] = True
                            except ImmutableStateError:
                                self.matching_connections = creds
                                global_state: GlobalState = await self.get_state(GlobalState)
                                global_state.open_modals['connections'] = True

            case AssetCreatedEvent():
                print("!!! An asset was created: ", agevent)

            case ChatModelEnd():
                pass

            case AgentEndEvent():
                pass

            case ChangeStateEvent():
                # Agent has requested to change state
                # For now the ChatEngine is toggling its record of the state itself, so we only have
                # to change our local agent model.
                if agevent.live:
                    self._agent.state = agevent.state
                    with rx.session() as sess:
                        sess.add(self._agent)
                        sess.commit()
                        sess.refresh(self._agent)
            case _:
                # This case handles any unmatched event types
                print("Dashboard recevied unknown event: ", agevent, " type: ", type(agevent))

    async def prompt_for_new_connection(self, tool_factory_id: str):
        from .connections_state import ConnectionsState

        conns_state: ConnectionsState = await self.get_state(ConnectionsState)
        conns_state.connections_page_load()
        conns_state.patch_agent_tool = True
        conns_state.select_factory(tool_factory_id)
        conns_state.new_credential()

    async def prompt_for_edit_connection(self, credential_id: str):
        from .connections_state import ConnectionsState

        conns_state: ConnectionsState = await self.get_state(ConnectionsState)
        conns_state.connections_page_load()
        conns_state.patch_agent_tool = True
        conns_state.edit_credential(credential_id)

    # Signaled from the ConnectionsState that a new connection was created. Patch
    # it onto our agent if needed. This assumes that the "uitool" was already added
    async def notify_credential_created(self, dbcred: CredentialBase|LocalCred):
        from .connections_state import ConnectionsState

        tf_dict = {}
        if isinstance(dbcred, LocalCred):
            tf_dict = self._factory_id_map.get(dbcred.factory_id) or {}
        else:
            tf_dict = self._factory_id_map.get(dbcred.tool_factory_id) or {}

        tf_dict['credential_id'] = str(dbcred.id)
        tf_dict['name'] = dbcred.name
        uitool = UITool.from_tool_factory_dict(tf_dict)
        
        # If the tool already exists update it
        tool_updated = False                
        for i, ut in enumerate(self.app.uitools):
            if ut.tool_factory_id == uitool.tool_factory_id and ut.credential_id == uitool.credential_id:
                self.app.uitools[i] = uitool
                # Reset the tools list to match
                self.app.tools = [t.name for t in self.app.uitools]
                tool_updated = True

        if not tool_updated:
            self.app.uitools.append(uitool)
            self.app.tools.append(uitool.name)

        # Update the wide_tools_library to include the new credentials
        cred_updated = False
        for i, wide_tool in enumerate(self.wide_tools_library[uitool.category]):
            if wide_tool.tool_factory_id == uitool.tool_factory_id:
                for j, avail_cred in enumerate(wide_tool.avail_creds):
                    if avail_cred.id == dbcred.id:
                        self.wide_tools_library[uitool.category][i].avail_creds[j] = dbcred
                        cred_updated = True
                # If no match found add it
                if not cred_updated:
                    self.wide_tools_library[uitool.category][i].avail_creds.append(dbcred)

        await self._save_agent(visible_update=False)

        # Make sure connections modal is closed
        conns_state: ConnectionsState = await self.get_state(ConnectionsState)
        conns_state.connections_modal_open = False

    async def choose_tool_connection(self, credential_id, cred_name: str):
        # Invoked from the "choose connection" dialog when multiple connections match a dynamically added tool
        self.open_modals['connections'] = False
        for cred in self.matching_connections:
            if cred.id == credential_id:
                tf_dict = self._factory_id_map.get(cred.factory_id) or {}
                tf_dict['credential_id'] = credential_id
                tf_dict['name'] = cred_name

                uitool = UITool.from_tool_factory_dict(tf_dict)
                self.app.uitools.append(uitool)
                await self._save_agent(visible_update=False)
                return 

    def finish_chat_render(self):
        # Chat window shows spinner if latest output is empty
        self.chats[-1].answers[-1].output += " "

    def help_page_load(self):
        self.page_setup()

    async def save_env_vars(self, form_data: dict):
        print("Saving env vars: ", form_data)
        self._agentsvc.save_secrets(self.user.tenant_id, self.user.id, form_data)
        prompt = f"Values saved for vars: {', '.join(form_data.keys())}"
        return EditorState.handle_run_agent_with_input(prompt)

    async def read_engine_events(self, channel, timeout=500) -> AsyncGenerator[dict, None]:
        channel = await pubsub.create_subscriber(
            self.router.session.client_token,
            self.__run["logs_channel"],
            recreate=False,
        )

        start = time.time()
        timeout = float(self.app.max_agent_time)  # Ensure this is a float
        while time.time() - start < timeout:
            message = await channel.get_message(ignore_subscribe_messages=True, timeout=0.05)
            if message:
                try:
                    data = json.loads(message['data'])
                    yield data
                    if isinstance(data, dict) and data.get("type") == AgentLogEventTypes.END:
                        message = await channel.get_message(ignore_subscribe_messages=True, timeout=0.05)
                        if message is None:
                            return
                        else:
                            # Seems like more messages, so keep going
                            data = json.loads(message['data'])
                            yield data
                except Exception as e:
                    traceback.print_exc()
                    pass

    def toggle_editor_pane(self):
        if self.editor_pane_class in ["", "editor_open"]:
            self.editor_pane_class = "editor_closed"
            return EditorState.bg_load_runs
        else:
            self.editor_pane_class = "editor_open"

    def toggle_test_prompt_modal(self):
        self.test_prompt_modal_open = not self.test_prompt_modal_open

    def toggle_tools_modal(self):
        self.tool_modal_open = not self.tool_modal_open
        if self.tool_modal_open:
            self.load_agents_list()

    def toggle_remove_tool_modal(self):
        self.remove_tool_modal_open = not self.remove_tool_modal_open

    def toggle_app_clone_modal(self):
        self.app_clone_modal_open = not self.app_clone_modal_open
        
    def toggle_reflect_modal_checkbox(self, index: int):
        self.reflect_modal_checked[index] = not self.reflect_modal_checked[index]

    async def save_reflect_modal(self):
        # Create a list to store the selected reflections
        selected_reflections = []
        for reflection, checked in zip(self.reflect_modal_result, self.reflect_modal_checked):
            if checked:
                selected_reflections.append(reflection)

        print("Saving reflect modal state:", selected_reflections)

        # Add the selected reflections to the agent's memory
        self.add_to_memory(selected_reflections)
        print("Agent memory: ", self._agent.memories_json)
        self.close_reflect_modal()
        await self.save_agent()
        await self.editor_page_load()

    ## Triggers
    @timeit
    def load_avail_triggers(self):
        # The list of triggers comes from the available connections plus a few defaults.
        AVAIL_TRIGGER_TOOLS = ["slack_connector", "gmail_connector", "database","s3_connector"]
        triggers = ["Chat box", "Auto run", "Scheduler", "Email"]
        for local_cred in self.mycredentials:
            if local_cred.factory_id in AVAIL_TRIGGER_TOOLS:
                if local_cred.name != local_cred.system_name:
                    triggers.append(f"{local_cred.system_name} ({local_cred.name})")
                else:
                    triggers.append(local_cred.system_name)
        self.avail_triggers = triggers

    ## Prompt Engineering
    @timeit
    def load_prompt_engineering_strategies(self):
        # these are hardcoded strategies that are filled out in test_prompt_modal.py
        prompt_engineering_strategies = [ "Original Prompt",
                                          "A U T O M A T",
                                          "Chain of thought",
                                          "Output Format",
                                          "Few Shot Learning",
                                          "Prompt Template"]
        # Attach the form template for this engineering strategy here.
        self.avail_prompt_engineering_strategies = prompt_engineering_strategies

            ## Prompt Engineering
    def load_overall_user_strategies(self):
        # these are hardcoded strategies that are filled out in test_prompt_modal.py
        prompt_engineering_strategies = [ "Original Prompt",
                                          "A U T O M A T",
                                          "Chain of thought",
                                          "Output Format",
                                          "Few Shot Learning",
                                          "Prompt Template"]
        # Attach the form template for this engineering strategy here.
        self.avail_prompt_engineering_strategies = prompt_engineering_strategies
   
    def download_agent(self):
        cred_names = {cred.id: cred.name for cred in self.mycredentials}
        return rx.download(
            filename=f"{self.app.name}.ai.yaml.b64",
            data=base64.b64encode(
                yaml.safe_dump(
                    self._agent.to_yaml_dict(cred_names), 
                        default_flow_style=False,
                        sort_keys=False,
                        indent=4
                    ).encode()
                )
            )

    async def open_datums_page(self):
        run_id = self.__run['id'] if self.__run else '0'
        if self._agent:
            return rx.redirect(
                f"/datums/{self._agent.id}/{run_id}/", 
                external=True
            )
            
    async def view_single_datum(self, file_name):
        run_id = self.__run['id'] if self.__run else '0'
        agent_id = self._agent.id if self._agent else '0'

        script = "try {" + \
            f"window.openPopup('/datum/{agent_id}/{run_id}/" + \
            "?file=' + encodeURIComponent('" + file_name + "'));" + \
            "} catch {}"
        return rx.call_script(script)

    def download_file(self, file_name):
        if not self._agentsvc:
            return
        
        file_info = self._agentsvc.get_file_info(
            tenant_id=self.user.tenant_id,
            user_id=self.user_id,
            filename=file_name,
        )

        if 'error' in file_info:
            return

        return rx.redirect(
            file_info['url'],
            external=True
        )


    def delete_file(self, file_name):
        if not self._agentsvc:
            return
        
        self._agentsvc.delete_file(
            tenant_id=self.user.tenant_id,
            user_id=self.user_id,
            filename=file_name
        )

    # Handle a file upload from the chat window, by steaming it directly to the Engine    
    async def handle_chat_upload(self, files: list[rx.UploadFile]): # -> list[rx.event.EventSpec]:
        def remove_non_ascii(text):
            return ''.join(char for char in text if ord(char) <= 127)
        
        for file in files:
            print("Received upload, sending file to Engine: ", file.filename)
            file.filename = remove_non_ascii(file.filename)
            self.temp_upload_file = file.filename
            yield
            # FIXME: we can't index a chat file upload if the Run hasn't been started yet
            await self._agentsvc.upload_file(
                self.user.tenant_id,
                self.user_id,
                "uploads",
                file,
                index_file=True,
                run_id=self.__run.get('id') if self.__run else None,
            )

        yield rx.clear_selected_files("upload_chat")

    async def clear_upload_file(self):
        self.temp_upload_file = None

    async def tray_file_upload(self, files: list[rx.UploadFile]) -> list[rx.event.EventSpec]:
        for file in files:
            await self._agentsvc.upload_file(
                self.user.tenant_id,
                self.user.id,
                "",
                file
            )
        self.files_list = []
        return [rx.clear_selected_files("upload_tray"), EditorState.bg_load_files]
    
    def refresh_data_list(self):
        self.files_list = []
        return EditorState.bg_load_files

    @rx.var
    def user_owns_agent(self) -> bool:
        if self.user and self.app:
            return self.user.id == self.app.user_id
        else:
            return False
        
    @rx.var
    def is_supercog_agent(self) -> bool:
        return self.app.id.startswith("_supercog_") and not self.app.id.startswith("_supercog_help")
    
    @rx.var
    def agent_editable(self) -> bool:
        f = self._get_agents_folder()

        if self.is_supercog_agent:
            return False
        # Allow agent in ANY shared folder to be edited by anyone, for now until
        # we have proper per-user sharing
        if self.user_owns_agent or (f is not None and f.scope == "shared"):
            return self.editor_pane_class != "editor_closed"
        else:
            return False

    @rx.var
    def usage_message(self) -> str:
        return f"{self.run_input_tokens:,} / {self.run_output_tokens:,}"
    
    @rx.var
    def costs_message(self) -> str:
        if self.run_model != "":
            costs = calc_tokens_cents(self.run_model, self.run_input_tokens, self.run_output_tokens)
            dollars = (costs[0]/100.0) + (costs[1] / 100.0)
            return f"${dollars:,.4f}"
        else:
            return ""
        
    @rx.var
    def chat_answers_length(self) -> int:
        answers_length = 0
        for chat in self.chats:
            answers_length += len(chat.answers)
        
        return answers_length

    @timeit
    def load_runs(self):
        if self._agent:
            self._agent_runs = self._agentsvc.get_runs(self._agent, self._user_id)
            now = datetime.utcnow()
            def get_input(runobj):
                if runobj.input:
                    return runobj.input
                elif runobj.run_log:
                    agevent: AgentEvent = EventRegistry.get_event(runobj.run_log)
                    if isinstance(agevent, AgentInputEvent):
                        return agevent.prompt
                    else:
                        return runobj.run_log.content
                else:
                    return ""
            def get_time(created):
                tmsg = timeago.format(created, now)
                for match,rep in (("minute","mn"),("hour","hr"), ("second", "sc")):
                    tmsg = tmsg.replace(match, rep)
                return tmsg
                        
            self.agent_runs = [
                [f"{get_time(r.created_at)} - {get_input(r)}"] for r in self._agent_runs
            ]
            self.agent_runs_ns = [
                dict(time=get_time(r.created_at), input=get_input(r), id=str(r.id)) for r in self._agent_runs
            ]
        else:
            self._agent_runs = []

    @rx.background
    async def bg_load_runs(self):
        async with self:
            self.load_runs()
            # if chat is empty, and agent_runs is non-empty, and the first run was created less than 10 mins ago
            # then load the logs for that run
            if (
                len(self.chats) == 0 and 
                len(self._agent_runs) > 0 and 
                self._agent_runs[0].created_at.replace(tzinfo=timezone.utc) > (datetime.now(timezone.utc) - timedelta(seconds=600))
            ):
                await self.load_runlogs(str(self._agent_runs[0].id))

    def click_runlist_cell(self, pos):
        if isinstance(pos, int):
            runrec = self._agent_runs[pos]
            run_id = runrec.id
        elif isinstance(pos, str):
            run_id = pos
        else:
            runrec = self._agent_runs[pos[1]]
            run_id = runrec.id
        return EditorState.load_runlogs(str(run_id))

    async def load_runlogs(self, run_id: str):
        if self._agentsvc is None:
            return rx.redirect(self.router.page.raw_path)
        self.loading_run_logs = True
        self.__run = self._agentsvc.get_run(run_id)
        self.active_run_id = run_id
        if 'model' in self.__run:
            self.run_model = self.__run['model']
        self.run_tools = UITool.from_api_run_tools(self.__run.get("tools"))
        runlogs = self._agentsvc.get_run_logs(run_id, self._user_id)
        self._clear_chats()
        qa = QA(question="", user_name=self.authenticated_user.name)
        qa.answers.append(Answer())
        self.chats.append(qa)

        for runlog in runlogs:
            await self.render_run_event(runlog, live=False)
        self.finish_chat_render()
        self.loading_run_logs = False

    async def delete_run(self, run_id: str):
        # Delete run and its logs concurrently
        await asyncio.gather(
            self._agentsvc.delete_run_logs(run_id, self._user_id),
            self._agentsvc.delete_run(run_id)
        )
        
        if self.__run and self.__run["id"] == run_id: 
            self.temp_upload_file = None
            self._clear_chats()
            self.show_welcome_message()
            self.__run = None
            self.active_run_id = None
            self.run_model = self.app.model
            self.test_prompt = ""

        # Refresh the list of runs after deletion
        return EditorState.bg_load_runs

### OAUTH FLOWS
            
    def handle_submit(self, form_data: dict):
        """NOTE: I DONT THIS THIS IS USED. 
        Handle the form submit."""
        self.connections_modal_open = False


    def download_chat_transcript(self):
        """ Renders the current chat transcript into HTML for download """
        # create a file name based on the agent and the current day/time
        # ensure we create the ./web/public/downloads dir
        filename = f"{self._agent.name}-{datetime.now().strftime('%Y-%m-%d-%H-%M')}.html"

        css = """
            <style>
            body {
                background-color: #F8F8F8;
                @media only screen and (max-width: 768px) {
                    width: calc(100vw - 8px);
                }
                @media only screen and (min-width: 769px) and (max-width: 1200px) {
                    width: 80vw;
                }
                @media only screen and (min-width: 1201px) {
                    width: 60vw;
                }
            }
            .codehilite {
                padding: 8px;
                border-radius: 0.75rem;
                overflow: scroll;
                background-color: #F8F8F8 !important;
            }
            * {
                font-family: Roboto, sans-serif;
                font-size: 13px;
                color: #444;
            }
            .answer {
                padding: 1rem;
            }
            .question {
                background-color: #fbf49c42;
                white-space: pre-wrap;
                word-wrap: break-word;
                padding: 1rem;
                border-radius: 0.75rem;
                width: fit-content;
            }
            .parameters-dropdown {
                background-color: white;
                border-radius: 0.75rem;
                padding: 1rem;
            }
            .tool {
                background-color: white;
                font-family: courier;
                padding: 1rem;
                border-radius: 0.75rem;
            }
            </style>
            """

        def cleanup_markdown(m):
            lines = m.split("\n")
            for i in range(len(lines)):
                line = lines[i]
                line = re.sub(r"^(```[\w]*)\s+", r"\1\n", line)
                line = re.sub(r"(.+)```$", r"\1\n```\n", line)
                lines[i] = line
            return "\n".join(lines)

        if os.path.exists(".web/public"):
            actualfile = f".web/public/{filename}"
        else:
            actualfile = f"/srv/{filename}"

        extensions = [
            CodeHiliteExtension(noclasses=True, pygments_style='friendly'),
            FencedCodeExtension(),
            "md_in_html",
        ]

        with open(actualfile, "w") as f:
            f.write(css)

            # Write header
            created_at = datetime.now()
            if self.__run:
                created_at = self.__run['created_at']

            header = f"**{self._agent.name} - {created_at}**\n\n"
            header += f"model: _{self.run_model}_\n"
            f.write(markdown_converter.markdown(header, extensions=extensions))

            # Process chats one answer at a time
            for answer in self.chats:
                markdown=""
                if answer.question:
                    markdown += f"""<p class="question" markdown='1'>{answer.question}</p>\n"""
                for a in answer.answers:
                    if a.output:
                        if a.param_json:
                            markdown += "<div>\n"
                            markdown += f"""
                                <details class="parameters-dropdown">
                                    <summary>{a.output}</summary>
                                    <p class="tool" markdown="1">{a.param_json}</p>
                                </details>
                            """
                            markdown += "\n</div>\n"
                        else:
                            markdown += "<div class='answer' markdown='1'>\n"
                            markdown += a.output
                            markdown += "\n</div>\n"

                    if a.tool_output:
                        markdown += "<div class='answer'>\n"
                        markdown += f"""
                            <details>
                                <summary>details</summary>
                                <p class="tool" markdown="1">{a.tool_output}</p>
                            </details>
                        """
                        markdown += "\n</div>\n"

                markdown = cleanup_markdown(markdown)
                f.write(markdown_converter.markdown(markdown, extensions=extensions))
                f.flush()  # Ensure data is written to disk

            # Write footer
            footer = "--------------------\n"
            footer += f"_Usage_: {self.usage_message} - {self.costs_message}"
            f.write(markdown_converter.markdown(footer, extensions=extensions))

        return rx.download(filename=filename, url=f"/{filename}")

    @rx.background  
    async def bg_load_files(self):
        # Call self._agentsvc.list_files outside the loop
        if self.user is not None and len(self.files_list) == 0:
            async with self:
                new_list = []
                file_list = self._agentsvc.list_files(self, self.user.tenant_id, self.user.id)

                for f in file_list:
                    try:
                        last_mod = datetime.strptime(f["last_modified"], "%Y-%m-%dT%H:%M:%SZ")
                    except:
                        last_mod = datetime.strptime(f["last_modified"], '%Y-%m-%dT%H:%M:%S.%fZ')
                    
                    file_info = {
                        "name": f["name"],
                        "url": f["url"],
                        "last_modified": last_mod.replace(tzinfo=pytz.utc),
                    }
                    new_list.append(file_info)
                self._files_loaded = True
                self.files_list = new_list

    @rx.background
    async def mark_user_seen_editor(self, is_supercog: bool):
        flag = "seen_supercog" if is_supercog else "seen_editor"
        if self.user and not self.user.user_has_flag(flag):
            with rx.session() as session:
                u: User = session.get(User, self.user.id)
                if u:
                    u.set_user_flag(flag)
                    session.add(u)
                    session.commit()
                    session.refresh(u)

    def launch_product_tour(self, is_supercog: bool):
        if is_supercog:
            if self.user and not self.user.user_has_flag("seen_supercog"):
                self.toggle_delete_modal('sc_tour', '')
        else:
            if self.user and not self.user.user_has_flag("seen_editor"):
                self.toggle_delete_modal('tour', '')

    async def edit_tool_connection(self, tool_id):
        from .connections_state import ConnectionsState

        uitool: UITool
        for uitool in self.app.uitools:
            if uitool.tool_id == tool_id:
                if uitool.credential_id is not None:
                    conns_state: ConnectionsState = await self.get_state(ConnectionsState)
                    conns_state.connections_page_load()
                    conns_state.edit_credential(uitool.credential_id)
