import base64
import traceback
import yaml
import asyncio
from typing import Literal, Optional

import reflex as rx
from sqlmodel import Session

from supercog.shared.services import db_connect
from supercog.shared.logging import logger
from supercog.dashboard.global_state import RECENT_FOLDER

from .agents_common_state import AgentsCommonState
from .state_models import UIFolder, AgentState
from .models import Folder, Agent, Tool
from .images import generate_agent_image

# The Index page state needs a list of agents from the current folder, the users
# that own those agents, and the tools for each agent. But the tools don't need
# credentials just for the listing, so '_listing_ui_tool_info' only returns
# the basic tool name.


class IndexState(AgentsCommonState):
    recent_agent_list: list[AgentState] = []
    folder_agent_list: list[AgentState] = []
    all_agents_list: list[AgentState] = []
    live_agent_list: list[AgentState] = []
    folder_is_shared: bool = False
    # The Edit page sets this flag when the set of agents has changed
    agent_list_dirty: bool = False
    new_user_open_modal: bool = False

    avatar_generating: bool = False
    avatar_modal_open: bool = False
    avatar_instructions: str = ""
    avatar_generation_error: str = ""

    _avatar_agent: Agent = None

    def home_page_load(self):
        if self.user.is_anonymous():
            return

        self.load_connections()
        self.load_system_agent_templates()
        self.update_agent_list()
        self.service_status = self._agentsvc.status_message
        self.avatar_modal_open = False
        self.avatar_generating = False

    def index_page_load(self):
        if self.user.is_anonymous():
            return
    
        self.avatar_modal_open = False
        self.avatar_generating = False

        self.load_connections()
        self.update_agent_list()
        self.service_status = self._agentsvc.status_message

    def update_agent_list(self, reload=False):
        reload = reload or bool(self.agent_list_dirty)
        logger.debug("IN update_agent_list, reload: ", reload)

        with rx.session() as sess:
            if self.user:
                self.load_folders(sess)
                if len(self.all_agents_list) == 0 or reload:
                    all_agents = Agent.agents_any_folder(sess, self.user.tenant_id, None, sort="alpha")
                    self.all_agents_list = [
                        AgentState.create(sess, agent, self._listing_uitool_info) 
                        for agent in all_agents
                    ]
                    # list should have only agents owned by user and public agents.
                    self.global_agents_list = self.filter_global_agents(sess, all_agents) #self.all_agents_list
                folder_slug = self.current_folder
                folder_id = None
                folder: Folder|UIFolder
                if folder_slug == "recent":
                    folder = RECENT_FOLDER
                else:
                    folder = self.lookup_folder(folder_slug)
                    if folder is None:
                        return rx.toast.error("Folder not found")
                folder_id = folder.id

                self.folder_is_shared = (folder.scope == "shared")
                user_filter = self.user.id if folder.scope == "private" else None
                if folder == RECENT_FOLDER:
                    self.recent_agent_list = [
                        AgentState.create(sess, agent, self._listing_uitool_info) 
                        for agent in
                            Agent.agents_any_folder(
                                sess, 
                                self.user.tenant_id, 
                                user_filter, 
                                limit=5,
                            )
                    ]
                else:
                    self.recent_agent_list = []
                recents = [str(agent.id) for agent in self.recent_agent_list]
                self.folder_agent_list = [
                    AgentState.create(sess, agent, self._listing_uitool_info) 
                    for agent in
                        Agent.agents_by_folder(
                            sess, 
                            self.user.tenant_id, 
                            user_filter, 
                            folder_id,
                        )
                    if str(agent.id) not in recents
                ]
            else:
                self.folder_agent_list = []
            sess.commit()
        self.service_status = self._agentsvc.status_message

    def filter_global_agents(self, sess, all_agents):
        user_folders = Folder.get_user_folders(sess, self.user.tenant_id, self.user.id)
        user_folder_ids = set(folder.id for folder in user_folders)

        filtered_agents = [
            AgentState.create(sess, agent, self._listing_uitool_info)
            for agent in all_agents
            if agent.user_id == self.user.id or (agent.folder_id in user_folder_ids and agent.scope == "shared")
        ]
        return filtered_agents

    def _listing_uitool_info(self, tool: Tool, allow_replace_creds=False):
        sys_name = self.lookup_tool_factory_name(tool.tool_factory_id)
        tool_name = sys_name

        res= {
            "tool_factory_id": tool.tool_factory_id,
            "logo_url": self.lookup_tool_factory_logo_url(tool.tool_factory_id),
            "system_name": sys_name,
            "cred_name": "",
            "credential_id": tool.credential_id,
            "tool_id": tool.id,
            "name": tool_name,
            "agent_url": "",
            "functions_help": "",
        }
        return res
    
    async def handle_upload_agent(self, files: list[rx.UploadFile]) -> rx.event.EventSpec:
        file: rx.UploadFile
        for file in files:
            try:
                if file.filename.endswith("b64"):
                    encoded_data = await file.read()
                    yaml_data = base64.b64decode(encoded_data).decode('utf-8')
                else:
                    yaml_data = await file.read()
                descriptor = yaml.safe_load(yaml_data)
                with rx.session() as session:
                    descriptor['tenant_id'] = self.user.tenant_id
                    descriptor['user_id'] = self.user.id
                    agent = Agent.create_from_dict(descriptor, session, self._get_uitool_info)
                    return await self.goto_edit_app(agent.id, agent_name=agent.name, success_modal_key="upload")
            except Exception as e:
                traceback.print_exc()
                return [rx.clear_selected_files("upload2"), rx.toast.error(f"Upload failed:\n\n```\n{e}\n```")]
            
        return rx.clear_selected_files("upload2")
    
    def set_folder_for_agent(
            self,
            agent_id: str,
            folder_name: str,
            agent_list_type: Literal["all", "recent", "folder"]
        ):
        # Find the AgentState
        agent_state = None
        match agent_list_type:
            case "all":
                for agent in self.all_agents_list:
                    if agent.id == agent_id:
                        agent_state = agent
            case "recent":
                 for agent in self.recent_agent_list:
                    if agent.id == agent_id:
                        agent_state = agent
            case "folder":
                for agent in self.folder_agent_list:
                    if agent.id == agent_id:
                        agent_state = agent            

        # Return if no AgentState is found
        if not agent_state:
            return

        agent_state.folder_name = folder_name
        agent_state.folder_slug = Folder.name_to_slug(folder_name)

        with rx.session() as sess:
            _agent = sess.get(Agent, agent_id)

            if not _agent:
                return

            for folder in self.folders:
                if (folder.slug == agent_state.folder_slug):
                    agent_state.folder_id = folder.id

            # If the special key the agent does not have a folder
            if (folder_name == "no_folder_key"):
                agent_state.folder_name = ""
                agent_state.folder_slug = ""
                agent_state.folder_id = None
            
            _agent.update_from_state(agent_state, agent_state.folder_id)

            sess.add(_agent)
            sess.commit()
            sess.refresh(_agent)

            self._agentsvc.save_agent(_agent)
            self.agent_list_dirty = True
    
    def find_agent_by_id(self, recent_agent_list: list[AgentState], appid: str):
        agent_state = next((agentstate for agentstate in recent_agent_list if agentstate.id == appid), None)
        return agent_state
    
    def toggle_avatar_modal(self, appid: Optional[str] = None):
        self.avatar_generation_error = ""
        if self.avatar_modal_open == False:
            if appid:
                with rx.session() as sess:
                    self._avatar_agent = sess.get(Agent, appid) # type: ignore

                # Set the avatar instructions
                self.avatar_instructions = (
                    f"Generate a simple-styled logo for an AI agent named '{self._avatar_agent.name}'. "
                    "Use bright colors in the logo."
                )

        self.avatar_modal_open = not self.avatar_modal_open

    #
    # User instructions functions have moved to `prompt_helpers.py`
    #

    ## Avatar generation
    def generate_avatar(self):
        self.avatar_generation_error = ""
        # dispatch the image generation task
        with rx.session() as sess:
            self._avatar_agent.avatar_url = None
            sess.add(self._avatar_agent)
            sess.commit()
            sess.refresh(self._avatar_agent)

        # And dispatch a task to poll for the image gen to finish
        return [IndexState.gen_image, IndexState.poll_for_avatar]
    
    @rx.background
    async def gen_image(self):
        async with self:
            self.avatar_generating = True
            yield

        try:
            await generate_agent_image(
                "dashboard", 
                self._avatar_agent.id, 
                self._avatar_agent.name, 
                self.avatar_instructions,
            )
            yield
        except Exception as e:
            async with self:
                if 'content_policy_violation' in str(e):
                    self.avatar_generation_error = (
                            "Content Policy Violation:"
                            "Your prompt may contain text that is not allowed by the AI safety system. "
                            "Please review your input and try again."
                        )
                else:
                    self.avatar_generation_error = "Error generating image"
                yield
        
        async with self:
            self.avatar_generating = False
            yield

    @rx.background
    async def poll_for_avatar(self):
        with Session(db_connect("dashboard")) as sess:
            for _ in range(40):
                async with self:
                    if self.avatar_generation_error:
                        # If there's an error, stop polling
                        return
                
                agentdb = sess.get(Agent, self._avatar_agent.id)
                sess.refresh(agentdb)
                if agentdb is not None and agentdb.avatar_url:
                    async with self:
                        self._avatar_agent = agentdb
                        agent_state = self.find_agent_by_id(self.recent_agent_list, agentdb.id)
                        if agent_state is None:
                            agent_state = self.find_agent_by_id(self.folder_agent_list, agentdb.id)
                        if agent_state is not None:
                            agent_state.avatar = agentdb.avatar_url
                        self.avatar_modal_open = False
                        yield
                    return

                await asyncio.sleep(3.0)

        # If we've reached this point, the polling has timed out
        async with self:
            self.avatar_generation_error = "Image generation timed out. Please try again."
            yield

