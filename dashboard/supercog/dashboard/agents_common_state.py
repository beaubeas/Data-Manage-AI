import glob
import os
from datetime import datetime, timedelta

import reflex as rx

from supercog.shared import timeit
from supercog.shared.services import config
from .global_state import GlobalState
from .state_models import AgentState, TemplateTool, TemplateState, LocalCred, UIDocIndex
from .models import Agent, Tool, User
from .import_export import import_agent_template_from_markdown
from .utils import SYSTEM_AGENTS_DIR

# Agent listing and the Edit page both need credentials and
# Tool Factories, so collect those in this shared state class.

class AgentsCommonState(GlobalState):
    _tool_factories: list[dict] = []
    avail_tools: list[dict[str,str]] = [] # same as _tool_factories but available in the frontend
    avail_doc_sources: list[dict[str,str]] = []
    _factory_id_map: dict[str, dict] = {}
    mycredentials: list[LocalCred] = []
    doc_indexes: list[UIDocIndex] = []

    #FIXME: Load a slim versions of the agents list just
    # for use in the Tools menu
    global_agents_list: list[AgentState] = []
    system_agent_templates: list[TemplateState] = []

    @timeit
    def load_tool_factories(self):
        if self.user:
            self._tool_factories = self._agentsvc.tool_factories(self.user.tenant_id)
            if self._tool_factories:
                self._factory_id_map = {tf["id"]: tf for tf in self._tool_factories}
                self.avail_tools = sorted([
                        tf for tf in self._tool_factories if tf["auth_config"] != {} and not tf["is_docsource"]
                    ],
                    key=lambda tf: tf["system_name"]
                )
                if len(self.avail_tools) > 0:
                    self.service_status = self._agentsvc.status_message

                self.avail_doc_sources = sorted([
                        tf for tf in self._tool_factories if tf["is_docsource"]
                    ],
                    key=lambda tf: tf["system_name"]
                )
            else:
                self._tool_factories = []

    @timeit
    def load_connections(self, force: bool=False):
        if len(self.mycredentials) > 0 and not force:
            return
        
        self.load_tool_factories()
        if self.user:
            credslist = self._agentsvc.list_credentials(self.user.tenant_id, self.user.id + "")
            credslist = sorted(credslist, key=lambda c: c["tool_factory_id"])
            with rx.session() as sess:
                self.mycredentials = [
                    LocalCred._from_cred_model(
                        c, 
                        self.lookup_tool_factory_name(c["tool_factory_id"]),
                        c["user_id"],
                        self.lookup_owner_name(sess, c["user_id"]),
                        self.lookup_tool_factory_logo_url(c["tool_factory_id"]),
                    )
                    for c in credslist
                ]
                self.doc_indexes = self._agentsvc.list_doc_indexes(
                    self.user.tenant_id, 
                    self.user.id,
                    lambda rec: UIDocIndex(
                        id=rec["id"], 
                        name=rec["name"], 
                        scope=rec["scope"],
                        is_shared=rec["scope"] == "shared",
                        owner=self.lookup_owner_name(sess, rec["user_id"])
                    )
                )
        else:
            print("!! No user in load_connections")          
        return
    
    @timeit
    def load_system_agent_templates(self):
        if isinstance(self.system_agent_templates, list) and len(self.system_agent_templates) > 0:
            return
        self.system_agent_templates = []
        for mdfile in sorted(glob.glob(os.path.join(SYSTEM_AGENTS_DIR, "*.md"))):
            if os.path.basename(mdfile).startswith("_"):
                continue
            markdown_agent = open(mdfile, "r").read()
            template = import_agent_template_from_markdown(markdown_agent, self._tool_factories)
            if isinstance(template, TemplateState):
                template.id=Agent.calc_system_agent_id(self.user.tenant_id, self.user.id, template.name)
                # If it is a "dynamic tools" agent like Supercor or the Slack agens, then pre-create it in case
                # the user doesn't login to the Dashboard
                if config.DYNAMIC_TOOLS_AGENT_TOOL_ID in [tool.tool_factory_id for tool in template.tools]:
                    with rx.session() as sess:
                        self.create_agent_from_template(sess=sess, template=template)
                self.system_agent_templates.append(template)
            else:
                raise RuntimeError(f"Bad system Agent spec: {mdfile}")
            
    def resolve_tool(self, tool_dict: TemplateTool, agent_id: str):
        # tool syntax:   Tool name|Connection name|config_key=val,config_key=val2
        credential_id = None
        if tool_dict.config:
            agent_cred = self._agentsvc.set_credential(
                tenant_id=self.user.tenant_id,
                user_id=self.user.id + "",
                credential_id=None,
                tool_factory_id=tool_dict.tool_factory_id,
                name=tool_dict.name,
                is_shared=False,
                secrets=tool_dict.config,
            )
            credential_id = agent_cred.id

        tool = Tool(
            tool_name=tool_dict.name,
            tool_factory_id=tool_dict.tool_factory_id,
            agent_id=agent_id,
            created_at = None,
            credential_id=credential_id,
        )
        return tool

    def create_agent_from_template(self, sess, template: TemplateState) -> Agent:
        made_creds = False
        agent = sess.get(Agent, template.id)
        if agent is None:
            agent = Agent(
                id=template.id,
                name=template.name, 
                model=template.model, 
                avatar_url=template.avatar_url,
                system_prompt=template.system_prompt, 
                welcome_message=template.welcome_message,
                max_chat_length=template.max_chat_length,
                updated_at=datetime.now() - timedelta(days=365), # don't show as recent until edited
                user_id=self.user.id,
                tenant_id=self.user.tenant_id,
            )
            sess.add(agent)
            sess.commit()
            sess.refresh(agent)
            for tool_dict in template.tools:
                tool = self.resolve_tool(tool_dict, template.id)
                if tool:
                    if tool.credential_id:
                        made_creds = True
                    sess.add(tool)
            sess.commit()

        if made_creds:
            self.load_connections(force=True)

        if agent.enabled_indexes is None:
            agent.enabled_indexes = "[]"

        self._agentsvc.save_agent(agent)
        return agent

    def lookup_owner_name(self, sess, user_id):
        user = sess.get(User, user_id)
        if user:
            return user.username
        else:
            return "?"

    def lookup_tool_factory_logo_url(self, tool_factory_id: str|None) -> str|None:
        for tf in (self._tool_factories or []):
            if tf["id"] == tool_factory_id:
                return tf.get("logo_url")
        if tool_factory_id and tool_factory_id.startswith("agent:"):
            agent_id = tool_factory_id.split(":")[1]
            return next((a.avatar for a in self.global_agents_list if a.id == agent_id), "")
        return None
    
    def lookup_tool_factory_category(self, tool_factory_id: str|None) -> str|None:
        for tf in (self._tool_factories or []):
            if tf["id"] == tool_factory_id:
                return tf.get("category")
        return None

    def lookup_tool_factory_name(self, tool_factory_id: str):
        for tf in self._tool_factories:
            if tf["id"] == tool_factory_id:
                return tf["system_name"]
        if tool_factory_id.startswith("agent:"):
            agent_id = tool_factory_id.split(":")[1]
            return next((a.name for a in self.global_agents_list if a.id == agent_id), "<agent not found>")
        return f"<unknown '{tool_factory_id}'>"


    def lookup_tool_factory_id_by_name(self, tool_name: str):
        for tf in self._tool_factories:
            if tf["system_name"].lower() == tool_name.lower():
                return tf["id"]
        return None
        
    def tool_factory_uses_env_vars(self, tool_factory_id: str) -> bool:
        tf = self._factory_id_map.get(tool_factory_id)
        if tf and 'auth_config' in tf:
            return 'env_vars' in tf['auth_config']
        return False

    def tool_factory_agent_functions(self, tool_factory_id: str) -> list[str]:
        tf = self._factory_id_map.get(tool_factory_id)
        return tf.get('agent_functions', []) if tf else []

    def tool_factory_help(self, tool_factory_id: str) -> str:
        tf = self._factory_id_map.get(tool_factory_id)
        return tf.get('help', '') if tf else ''

    def lookup_credential_name(self, cred_id: str) -> str:
        if cred_id is None or cred_id == "":
            return None
        for cred in self.mycredentials:
            if cred.id == cred_id:
                return cred.name
        return "<missing>"

    def find_avail_credentials(self, tool_factory_id, compatible_factory_id=None) -> list[LocalCred]:
        # Sort creds by private first, then shared
        return sorted(
            [cred for cred in self.mycredentials if cred.factory_id in [tool_factory_id, compatible_factory_id]],
            key=lambda c: c.owner == "private",
            reverse=True,
        )
    
    def _get_uitool_info(self, tool: Tool, allow_replace_creds=False):
        sys_name = self.lookup_tool_factory_name(tool.tool_factory_id)
        tool_name = sys_name
        cred_name = self.lookup_credential_name(tool.credential_id)
        tool_id = tool.id
        if (cred_name is None or cred_name == "<missing>") and allow_replace_creds and \
            not self.tool_factory_uses_env_vars(tool.tool_factory_id):
            # Cred deleted, find a possible replacement
            replacements: list[LocalCred] = self.find_avail_credentials(tool.tool_factory_id)
            if len(replacements) > 0:
                tool.credential_id = replacements[0].id
                tool_id = None # force to create a new tool record when we save the agent
                cred_name = replacements[0].name
                self.app_modified = True

        if cred_name:
            tool_name = cred_name
            if sys_name.split()[0].lower() not in cred_name.lower():
                tool_name += f"({sys_name})"

        agent_url = ""
        if tool.tool_factory_id.startswith("agent:"):
            agent_url = f"/edit/{tool.tool_factory_id[6:]}"

        tool_helps = ""
        # We need this overall function when importing agent, but we don't need the 
        # tool function helps until the actual Edit page.
        if hasattr(self, "_tool_function_helps"):
            tool_helps = self._tool_function_helps.get(tool.tool_factory_id)

        res= {
            "tool_factory_id": tool.tool_factory_id,
            "logo_url": self.lookup_tool_factory_logo_url(tool.tool_factory_id),
            "system_name": sys_name,
            "cred_name": cred_name,
            "credential_id": tool.credential_id,
            "tool_id": tool_id,
            "name": tool_name,
            "agent_url": agent_url,
            "functions_help": tool_helps,
            "category": self.lookup_tool_factory_category(tool.tool_factory_id),
        }
        return res
