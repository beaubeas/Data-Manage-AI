import asyncio
import reflex as rx

from .state_models import LocalCred, UIDocSource
from .agents_common_state import AgentsCommonState
from .engine_client import TestResult
from supercog.shared.models import DocIndexBase

from typing import Optional, List

    
class ConnectionsState(AgentsCommonState):
    #############################################
    ######## Connections page state #############
    #############################################
    
    new_cred: LocalCred = LocalCred(factory_id="", name="", system_name="", owner_id="", owner="", auth_config={})
    selected_cred_name:              str = ""
    connections_modal_open:          bool = False
    is_editing_connection:           bool = False
    test_credentials_status_message: str = ""
    is_loading: bool = False
    # If set to True, then we are creating a Connection for a specific agent, so callback to
    # the EditorState to inform it the connection was created.
    patch_agent_tool: bool = False

    is_loading:                      bool = False
    all_credentials:                 list[LocalCred] = []
    expanded_systems:                set = set()    
    _factory:                        dict = {}

    def connections_page_load(self):
        if self.user.is_anonymous():
            return

        self.load_connections(force=True)
        self.patch_agent_tool = False
        self.connections_modal_open = False
        self.is_editing_connection = False
        self._factory = {}

        self.organize_credentials()
        
        # Get URL parameters
        cred_name = self.router.page.params.get('cred_name', None)
        index_id = self.router.page.params.get('index_id', None)
        
        if cred_name:
            self.selected_cred_name = cred_name
            self.connections_modal_open = False
            self.is_editing_connection = False
            
        # If we have an index_id, store it for OAuth redirect
        if index_id:
            self.current_index_id = index_id

    def organize_credentials(self):
        grouped = {}
        default_logo_url = "https://upload.wikimedia.org/wikipedia/commons/d/d5/No_sign.svg"

        # Group credentials by system name
        for cred in self.mycredentials:
            if cred.system_name not in grouped:
                grouped[cred.system_name] = []
            grouped[cred.system_name].append(cred)

        self.all_credentials = []  # Use all_credentials
        for system, creds in sorted(grouped.items()):
            # Assume the logo URL and factory_id is the same for all credentials under the same system
            #logo_url = creds[0].logo_url if creds else ""
            logo_url = creds[0].logo_url if creds and creds[0].logo_url else default_logo_url
            factory_id = creds[0].factory_id if creds and creds[0].factory_id else ""

            # Create a category header with the logo URL and flag
            self.all_credentials.append(
                LocalCred(
                    system_name=system,
                    is_category_header=True,
                    name="",
                    factory_id=factory_id,
                    owner="",
                    owner_id="",
                    auth_config={},
                    logo_url=logo_url,  # Add the logo URL
                    #has_logo=bool(logo_url),  # Set the flag based on the logo URL presence
                )
            )
            # Append the credentials under this system
            self.all_credentials.extend(creds)

    def toggle_system_group(self, system_name: str):
        if system_name in self.expanded_systems:
            self.expanded_systems.remove(system_name)
        else:
            self.expanded_systems.add(system_name)
            
    async def delete_item(self, key: str):
        result = None
        if key in self.delete_items:
            type, name = self.delete_items[key].split(":")
            if type == 'folder':
                result = self.delete_folder(name)
            elif type == 'credential':
                result = await self.delete_credential(name)
            elif type == 'docindex':
                result = await self.delete_doc_index(name)
        self.open_modals[key] = False
        return result

    def get_config_list(self, auth_config: dict) -> tuple[list, str]:
        # Converts a Tool's auth_config dict to a list of key, help pairs
        config_list: list[tuple[str,str,str]] = []
        help_msg = ""
        for opt, help in auth_config.items():
            if opt != "help":
                config_list.append((opt, help, opt.replace("_", " ").title()))
            else:
                help_msg = help
        config_list = config_list
        return config_list, help_msg

    def select_factory(self, factory_id):
        self._factory = [factory for factory in self._tool_factories if factory["id"] == factory_id][0]

    def factory_uses_oauth(self, tool_factory_id: str) -> bool:
        for tf in self._tool_factories:
            if tf["id"] == tool_factory_id:
                auth_keys = list(tf["auth_config"].keys())
                if len(auth_keys) > 0:
                    if "oauth" in auth_keys[0]:
                        return True
        return False
    
    def process_value(self, value):
        if isinstance(value, str):
            return value.replace(',', '')
        elif isinstance(value, dict):
            return [f"{k}:{v}" for k, v in value.items()]
        elif isinstance(value, list):
            return [str(item) for item in value]
        else:
            return [str(value)]

    def new_credential(self):
        if 'auth_config' not in self._factory:
            if len(self.avail_tools) > 0:    
                self._factory = self.avail_tools[0]
            else:
                return
        config_dict = list(self._factory["auth_config"].values())[0]
        config_list, help_msg = self.get_config_list(config_dict)

        config_list = [(key, self.process_value(value), description)
                for key, value, description in config_list]

        print("Config list: ", config_list)

        self.new_cred: LocalCred = LocalCred(
            factory_id=self._factory["id"],
            name=self._factory["system_name"],
            system_name=self._factory["system_name"],
            auth_config={},
            config_list=config_list,
            help_msg = help_msg,
            tool_help = self._factory.get("help") or "",
            is_shared = False,
            owner_id = self.user.id + "",
            owner = self.user.username,
            logo_url=self._factory["logo_url"],
        )
        self.new_cred.uses_oauth = self.factory_uses_oauth(self.new_cred.factory_id)
        self.test_credentials_status_message = ""
        self.connections_modal_open = True
        self.is_editing_connection = False
        self.test_credentials_status_message = ""
        self.is_loading = False


    def edit_credential(self, credential_id: str):
        for creds in self.mycredentials:
            if creds.id == credential_id:
                factory = [factory for factory in self._tool_factories if factory["id"] == creds.factory_id][0]
                self.new_cred = creds
                config_list, help = self.get_config_list(list(factory["auth_config"].values())[0])
                config_list = [(key, self.process_value(value), description)
                        for key, value, description in config_list]

                self.new_cred.config_list = config_list
                self.new_cred.help_msg = help
                self.new_cred.uses_oauth = self.factory_uses_oauth(self.new_cred.factory_id)
                self.connections_modal_open = True
                self.is_editing_connection = True
                self.test_credentials_status_message = ""
                self.is_loading = False
                return

    def change_is_shared(self, is_shared: bool):
        self.new_cred.is_shared = is_shared

    def save_cred_value(self, key, value):
        if key == 'name':
            self.new_cred.name = value
        else:
            self.new_cred.auth_config[key] = value

    async def test_connection(self):
        self.is_loading = True
        test_result = self._agentsvc.test_credential(self.user.tenant_id, 
                                self.user.id + "",
                                self.new_cred.factory_id,
                                self.new_cred.id,
                                dict(self.new_cred.auth_config))
        self.is_loading = False
        if test_result.success:
            print("Connection tested succesfully.")
            self.test_credentials_status_message = "✅ Connection tested succesfully."
        else:
            print("Fail to test credentials, error: " + test_result.message)
            self.test_credentials_status_message = "❌ Fail to test credentials, error: " + test_result.message
            
    async def save_credential(self):
        agent_cred = self._agentsvc.set_credential(
            self.user.tenant_id,
            self.user.id + "",
            self.new_cred.id,
            self.new_cred.factory_id,
            self.new_cred.name,
            bool(self.new_cred.is_shared),
            dict(self.new_cred.auth_config),
        )
        self.load_connections(True)
        self.organize_credentials()
        await self.set_creds_list_dirty()
        self.connections_modal_open = False
        self.is_editing_connection = False
        if self.patch_agent_tool:
            from .editor_state import EditorState
            edit_state = await self.get_state(EditorState)
            await edit_state.notify_credential_created(agent_cred)

    async def on_modal_close(self):
        self.test_credentials_status_message = ""

    # FIXME: !!
    # We should implement some internal signal system that avoids direct poking
    # of other state objects, and implements an observer pattern instead.
    async def set_creds_list_dirty(self):
        from .editor_state import EditorState
        edit_state = await self.get_state(EditorState)
        edit_state.credentials_list_dirty = True

    def cancel_credential(self):
        self.connections_modal_open = False
        self.is_editing_connection = False
        self.test_credentials_status_message = ""

    async def delete_credential(self, credential_id):
        self._agentsvc.delete_credential(self.user.tenant_id, self.user.id + "", credential_id)
        self.load_connections(True)
        self.organize_credentials()
        await self.set_creds_list_dirty()

    @rx.var
    def get_ut_id(self) -> str:
        """ Returns the user_id plus tenant_id """
        if self.user:
            return str(self.user.id) + ":" + str(self.user.tenant_id)
        else:
            return ""
        
    def new_index(self):
        index_rec = self._agentsvc.create_doc_index(self.user.tenant_id, self.user.id + "", "New RAG Index")
        return rx.redirect(f"/sconnections/index/{index_rec['id']}")

    async def delete_doc_index(self, index_id: str):
        self._agentsvc.delete_doc_index(self.user.tenant_id, self.user.id, index_id)
        self.load_connections(force=True)

