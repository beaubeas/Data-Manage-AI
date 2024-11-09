from datetime import datetime
import json
from typing import Any, List, Optional, Union, Tuple
from .models import Agent, Folder, User, Tool

import reflex as rx

class Answer(rx.Base):
    output:      str = ""
    lc_run_id:   str|None=None
    tool_output: str = ""
    
    timestamp:  datetime|None=None # "server" time that this answer was generated
    elapsed_time: str = "" #time since prompt start that this answer arrived
    tool_time: str = "" # time taken by the tool execution
    
    # Env Var request
    requested_var_names: list[str] = []
    
    # Json related variables
    object_results: bool = False
    before_json:    Any = None
    tool_json:      Any = None
    after_json:     Any = None
    param_json:     Any = None
    
    # xml related variables
    xml_results:    bool = False
    tool_xml:       Any = None

    #audio related variables
    audio_results:   bool = False
    audio_url:      str = ""
    
    # table related variables
    table_start:    int = 0
    table_results:  bool = False                # signals to renderer that we can start displaying
    table_complete: bool = False                # means we've reached the end of the table
    headers:        list[str] = []              # List of strings for headers
    rows:           list[tuple[str, ...]] = []  # List of tuples, each tuple contains strings
    table_output:   str = ""                    # the buffered output
    prefix:         str = ""                    # holds any text before the first |
    postscript:     str = ""                    # holds any text after  the first |
    error_flag:     bool = False                # Encountered an internal exception during tool call
    alignment:      str = "left"

    hide_function_call: bool = False
    is_tool_call:       bool = False
    is_script:          bool = False
    code:               str = ""
    
    created_at:         Optional[datetime]
    
class QA(rx.Base):
    """A question and answer pair."""

    question:    str
    user_name:   str
    answers:     list[Answer] = []
    question_bg: str = "#9f9f"
    question_bg_sc: str = "#fbf49c42"

    answer_class:   str = ""

    @classmethod
    def with_answer(cls, msg: str, user_name: str, special=""):
        align = "left"
        if special == "welcome":
            align = "left"
        opts = {"question":"", "answers":[Answer(output=msg, alignment=align)], "user_name":user_name}
        if special == "welcome":
            opts["answer_class"] = "welcome_msg"
        return cls(**opts)

    
class UserState(rx.Base):
    name: str
    profile_url: str
    email: str
    id: str


class LocalCred(rx.Base):
    factory_id: str
    name: str
    id: str = ""
    system_name: str
    owner: str
    owner_id: str
    help_msg: str = ""
    tool_help: str = ""
    auth_config: dict[str,str]
    config_list: List[Tuple[str, Union[str, List[str]], str]] = [('a', ['b'], 'c'), ('b', 'c', 'd')]
    is_shared: bool = False
    uses_oauth: bool = False
    logo_url: str|None = None
    is_category_header: bool = False

    @classmethod
    def get_logo_url(cls, logo_domain: str|None) -> str|None:
        if logo_domain:
            return f"https://logo.clearbit.com/{logo_domain}"
        else:
            return None
    
    @classmethod
    def _from_cred_model(
        cls, c: dict, 
        system_name: str, 
        owner_id: str, 
        owner_name: str,
        logo_url: str|None):

        return cls(
            id=c["id"],
            factory_id=c["tool_factory_id"],
            name=c["name"],
            system_name=system_name,
            is_shared=c["scope"] == "shared",
            auth_config=json.loads(c["secrets_json"]),
            logo_url=logo_url,
            owner_id=owner_id,
            owner=owner_name,
        )

# Tool descriptor for use in the UI (maps in and out of 'Tool' db model)
class UITool(rx.Base):
    name: str
    category: str|None=None
    logo_url: str|None=None
    system_name: str|None=None
    tool_factory_id: str|None=None
    tool_id: str|None = None
    help: str=""
    avail_creds: list[LocalCred] = []
    auth_needed: bool = False
    creds_empty: bool = True
    credential_id: str|None = None
    agent_url:str = ""
    functions_help: Optional[str] = ""
    is_category_header: bool = False

    @classmethod
    def from_db_tool(cls, opts: dict) -> "UITool":
        if 'id' in opts:
            opts['tool_id'] = opts.pop('id')
        if 'tool_name' in opts:
            opts['name'] = opts.pop('tool_name')
            if not opts['name']:
                opts['name'] = "<no name>"
        opts.pop('agent_id', None)
        opts.pop('description', None)
        if 'name' not in opts:
           opts['name'] = "<no name>"
        return UITool(**opts)

    def to_db_tool(self, agent_id: str) -> dict:
        tool = Tool(
            id=self.tool_id, 
            agent_id=agent_id,
            tool_factory_id=self.tool_factory_id, 
            tool_name=self.name,
            credential_id=self.credential_id,
        )
        return tool.model_dump()

    @classmethod
    def from_api_run_tools(cls, tools: list[dict] | None) -> list["UITool"]:
        if tools:
            return [cls.from_db_tool(t) for t in tools]
        else:
            return []

    @classmethod
    def from_tool_factory_dict(cls, tf: dict) -> "UITool":
        def func_desc(fdict):
            help_text = fdict["help"]
            idx = help_text.find(".")
            if idx > 0:
                help_text = help_text[:idx+1]
            return f"**{fdict['name']}** - *{help_text}*"

        tool_function_helps = \
            "  \n".join(func_desc(f) for f in tf.get('agent_functions', []))

        tool_name = tf['name'] if "name" in tf else tf['system_name']

        return UITool(
            tool_factory_id=tf['id'],
            name=tool_name,
            system_name=tf['system_name'],
            logo_url=tf.get('logo_url', ''),
            help=tf.get('help', '') or '',
            functions_help=tool_function_helps,
            category=tf['category'] or '',
            is_category_header=False,
            credential_id=tf.get('credential_id'),
            auth_needed=tf['auth_config'] != {}
        )

class UIFolder(rx.Base):
    name: str
    slug: str
    scope: str
    id: str|None
    user_id: str|None=None
    tenant_id: str|None=None
    folder_icon_tag: str = "folder"
    is_deletable: bool = True

USER_CACHE = {}
FOLDER_CACHE = {}

class TemplateTool(rx.Base):
    name: str
    tool_factory_id: str
    logo_url: str
    config: dict[str, str]

class TemplateState(rx.Base):
    """ Used for system agents so we don't need to create them until clicked on """
    id: str = ""
    name: str
    model: str = ""
    system_prompt: str = "You are a helpful assistant."
    welcome_message: str = ""
    max_chat_length: int|None = None
    avatar_url: str|None = None
    tools: list[TemplateTool] = []

class AgentState(rx.Base):
    """ An AI app. """
    
    id: str = ""
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful assistant."
    prompts: list [dict[str,str]] = []
    avatar: str|None = None
    model: str = ""
    input_mode: str = "fit"
    trigger: str = "Chat box"
    trigger_prefix: str = "Chat box"  # rx.Cond only works on full strings, and UI wants the "system name" prefix
    trigger_arg: str = ""
    scope: str = "private"
    welcome_message: str = ""
    user: UserState = UserState(name="", profile_url="", email="", id="")
    user_id: str = ""
    updated_at: datetime|None=None
    folder_id: str|None=None
    folder_name: str = ""
    folder_slug: str = ""
    agent_email: str = ""
    temperature: str = "0"
    max_agent_time: int = 600
    help_message: str|None = ""
    index_list: str = "" # Enabled index names, comma separated

    # In the UI we just keep tools as a list of Tool Factory names
    tools: list[str] = []
    uitools: list[UITool] = []

    is_folder_header: bool = False
    folder_icon_tag:  str = "folder"
    
    @classmethod
    def create(
        cls, 
        session, 
        agent: Optional[Agent], 
        tool_info_fn, 
        fixup_creds=False,
        help_message="") -> "AgentState":
        if agent and agent.user_id:
            try:
                prompts = json.loads(agent.prompts_json)
            except:
                prompts = [{"name": "test_prompt", "value": agent.prompts_json}] # temporary hact for migration

            # Fetch folder information if folder_id is available
            folder_scope = "private"
            folder_name = ""
            folder_slug =""
            if agent.folder_id:
                folder = session.get(Folder, agent.folder_id)
                if folder:
                    folder_scope = folder.scope
                    folder_name = folder.name
                    folder_slug = folder.slug
                    
            result = AgentState(
                id=agent.id,
                name=agent.name,
                scope=agent.scope,
                prompts=prompts,
                description=agent.description or "",
                system_prompt=agent.system_prompt or "",
                model=agent.model or "",
                tools=[str(t.tool_name or t.tool_factory_id) for t in agent.tools],
                input_mode=agent.input_mode,
                trigger=agent.trigger,
                trigger_arg=agent.trigger_arg or "",
                trigger_prefix=AgentState.get_trigger_prefix(agent.trigger),
                avatar=agent.avatar_url or "/robot_avatar2.png",
                welcome_message=agent.welcome_message or "",
                updated_at=agent.updated_at,
                user_id=agent.user_id,
                folder_id=agent.folder_id,
                folder_name = folder_name,
                folder_slug = folder_slug,
                agent_email=agent.get_agent_email_address(),
                temperature=str(agent.temperature),
                max_agent_time=agent.max_agent_time,
                uitools=[
                    UITool.from_db_tool(tool_info_fn(t, fixup_creds)) for t in agent.tools
                ],
                is_folder_header=False,  # Regular agents are not folder headers
                folder_icon_tag="folder-tree" if agent.scope == "shared" else "folder",
                help_message=help_message or agent.welcome_message or "",
                index_list=",".join([i.name for i in agent.get_enabled_indexes()]),
            )
            #print(f"folder name = {folder_name} folder tag = {result.folder_icon_tag}")
            result.lookup_user(session)
            return result
        else:
            return AgentState(name="agent or user missing")

    @classmethod
    def create_folder_header(cls, folder_name: str, folder_icon_tag: str) -> "AgentState":
        """Create a folder header AgentState."""
        return cls(
            name=folder_name,
            folder_name=folder_name,
            is_folder_header=True,
            folder_icon_tag = folder_icon_tag,
        )
    
    @staticmethod
    def get_trigger_prefix(trigger):
        if "(" in trigger:
            return trigger.split("(")[0].strip()
        else:
            return trigger

    def __lt__(self, other):
        return self.updated_at > other.updated_at

    def lookup_user(self, session):
        self.user = AgentState._lookup_db_user(self.user_id, session)

        if self.folder_id:
            if self.folder_id in FOLDER_CACHE:
                self.folder_name = FOLDER_CACHE[self.folder_id]
            else:
                folder = session.get(Folder, self.folder_id)
                if folder:
                    self.folder_name = str(folder.name)
                    FOLDER_CACHE[self.folder_id] = self.folder_name

    @staticmethod
    def _lookup_db_user(user_id: str, session) -> User:
        if user_id in USER_CACHE:
            return USER_CACHE[user_id]
        else:
            user_db = session.get(User, str(user_id))
            if user_db:
                user=UserState(
                    id=user_db.id,
                    name=user_db.username,
                    profile_url=user_db.profileurl or "",
                    email=user_db.emailval
                )
                USER_CACHE[user_id] = user
                return user
            else:
                return UserState(id=user_id, name="Guest", profile_url="", email="")

    def add_tool(self, tool: str):
        self.tools = list(set(self.tools + [tool]))

    def remove_tool(self, tool_id: str, tool_factory_id: str, tool_name: str):
        self.uitools = [t for t in self.uitools if t.tool_id != tool_id or t.tool_factory_id != tool_factory_id]
        self.tools = [t.name for t in self.uitools]
        
    def has_tool(self, tool: str) -> bool:
        return tool in self.tools

    def has_database_tool(self):
        return len([match for match in self.tools if "Database" in match]) > 0
    
    @property
    def get_agent_email_address(self) -> str:
        if self.agent_slug:
            return f"{self.agent_slug}@mail.supercog.ai"
        else:
            return "Save agent first"
        
class AgentTrigger(rx.Base):
    # Enum for the trigger type
    type: str
    variables: dict[str,Any]
    format_str: Optional[str] = None

    def __repr__(self) -> str:
        if self.format_str:
            return self.format_str.format(**self.variables)

    def format(self, **kwargs):
        if self.format_str:
            try:
                return self.format_str.format(**self.variables)
            except KeyError as e:
                raise RuntimeError("Trigger is missing variables: " + str(e))
        else:
            return str(self.variables)

class UIDatum(rx.Base):
    name:         str
    mime_type:    str
    category:     str

    is_directory: bool = False 
    is_expanded:  bool = False

    datum_type:   Optional[str] = None  # Adding icon_type as an optional attribute

    url:          Optional[str] = None
    children:     List['UIDatum'] = []
    path:         str = ""
    
    def toggle_expand(self):
        """Toggle the is_expanded flag to show or hide children in a UI."""
        self.is_expanded = not self.is_expanded

    def add_child(self, child: 'UIDatum'):
        """Add a child UIDatum to this datum if it is a directory."""
        if self.is_directory:
            self.children.append(child)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure that only directories can have children
        if not self.is_directory:
            self.children = []
            
class UIDocSource(rx.Base):
    id: str = ""
    name: str = ""
    system_name: str
    factory_id: str = ""
    folder_ids: str = ""
    file_patterns: str = ""
    uses_oauth: bool = False
    logo_url: str|None = None
    help_msg: str = ""
    auth_config: dict[str,str] = {}
    provider_data: str = ""
    config_list: List[Tuple[str, Union[str, List[str]], str]] = [('a', ['b'], 'c'), ('b', 'c', 'd')]

class UIDocIndex(rx.Base):
    id: str = ""
    name: str = ""
    scope: str = ""
    owner: str = ""
    is_shared: bool = False
