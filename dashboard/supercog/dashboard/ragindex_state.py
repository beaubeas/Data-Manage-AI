import asyncio
import reflex as rx

from .state_models import LocalCred, UIDocSource
from .agents_common_state import AgentsCommonState
from .engine_client import TestResult
from supercog.shared.models import DocIndexBase

from typing import Optional, List

    
class RAGIndexState(AgentsCommonState):
## RAG Indexes

    file_uploading: bool = False
    files_status: str = ""
    index_id: str = ""
    index_files: list[dict] = []
    index_search_results: list[dict] = []
    doc_index: dict[str,str] = {}
    doc_source_modal_open: bool = False
    doc_source: UIDocSource = UIDocSource(factory_id="", name="", system_name="", owner_id="", owner="", auth_config={})
    doc_sources: list[UIDocSource] = []
    current_page : int = 1
    is_editing_docsource: bool = False
    _doc_factory: dict = {}
    authorize_url: str = ""

    def rag_index_page_load(self):
        self.load_connections()
        self.index_id = self.router.page.params.get('index_id', None)

        _doc_index = self._agentsvc.get_doc_index(self.user.tenant_id, self.index_id)
        self.doc_index = _doc_index.model_dump()
        self.index_files = self._agentsvc.get_index_files(self.user.tenant_id, self.user.id, self.index_id,self.current_page)
        self.load_docsources()

        print("Index files: ", [dict(d) for d in self.index_files])
        self.file_uploading = False
        self.index_search_results = []
        self. doc_source_modal_open = False

        error_status = self.router.page.params.get("error", None)
        if error_status:
            return rx.toast.error(error_status)

        # On callback from Ragie, these should be filled in
        source_id = self.router.page.params.get('source_id', None)
        connection_id = self.router.page.params.get('connection_id', None)
        if source_id and connection_id:
            return RAGIndexState.on_authorize_callback(source_id, connection_id)

    def load_docsources(self):
        configs = self._agentsvc.get_docsources(self.user.tenant_id, self.user.id, self.index_id)

        def lookup_system_name(d: dict):
            facs = [fac["system_name"] for fac in self.avail_doc_sources if fac['id'] == d['doc_source_factory_id']]
            if facs:
                return facs[0]
            else:
                return "?"
             
        self.doc_sources = [
            UIDocSource(
                id = d['id'],
                name = d['name'] or "",
                system_name = lookup_system_name(d),
                factory_id = d['doc_source_factory_id'] or "",
                folder_ids = ", ".join(d['folder_ids']),
                file_patterns = ", ".join(d['file_patterns']),
                provider_data = str(d.get("provider_data", {})),
            ) for d in configs
        ]

    def _update_index(self, key, value):
        self._agentsvc.update_index(
            self.user.tenant_id, 
            self.user.id, 
            self.doc_index["id"], 
            {key: value},
        )

    def update_index_name(self, name: str):
        if self.doc_index:
            self._update_index("name", name)


    def update_source_description(self, description: str):
        if self.doc_index:
            self._update_index("source_description", description)

    def toggle_is_shared(self, is_shared: bool):
        if is_shared:
            self.doc_index['scope'] = "shared"
        else:
            self.doc_index['scope'] = "private"
        self._update_index("scope", self.doc_index['scope'])

    async def handle_upload(self, files: list[rx.UploadFile]) -> rx.event.EventSpec:
        """Handle the upload of file(s).

        Args:
            files: The uploaded files.
        """
        self.file_uploading = True
        self.files_status = f"Uploading files..."
        yield

        try:
            for file in files:
                await self._agentsvc.upload_index_file(
                    self.user.tenant_id,
                    self.user.id,
                    self.index_id,
                    file
                )
        except Exception as e:
            print("Error uploading file: ", e)
            self.files_status = f"Error uploading file: {e}"
        self.file_uploading = False 
        yield rx.clear_selected_files("upload1")
        # TODO: refresh our doc list
        yield RAGIndexState.bg_refresh

    @rx.background
    async def bg_refresh(self):
        for wait in range(2):
            async with self:
                print("Checking for files...")
                self.index_files = self._agentsvc.get_index_files(self.user.tenant_id, self.user.id, self.index_id,self.current_page)
            await asyncio.sleep(1.0 + wait*2.0)

    @rx.background
    async def bg_previous(self):
        for wait in range(2):
            async with self:
                print("Checking for files...")
                self.current_page -= 1 
                self.index_files = self._agentsvc.get_index_files(self.user.tenant_id, self.user.id, self.index_id,self.current_page)
            await asyncio.sleep(1.0 + wait*2.0)

    @rx.background
    async def bg_next(self):
        for wait in range(2):
            async with self:
                print("Checking for files...")
                self.current_page += 1
                self.index_files = self._agentsvc.get_index_files(self.user.tenant_id, self.user.id, self.index_id,self.current_page)
            await asyncio.sleep(1.0 + wait*2.0)

    async def index_search(self, form_data: dict):
        query = form_data.get("search", "")
        print("Calling Index search for: ", query)
        self.index_search_results = []
        docs = self._agentsvc.index_search(self.user.tenant_id, self.user.id, self.index_id, query)
        print(f"Received {len(docs)} search results.")
        self.index_search_results = docs


# Doc Sources
    def select_doc_factory(self, factory_id):
        self._doc_factory = [factory for factory in self.avail_doc_sources if factory["id"] == factory_id][0]

    def toggle_doc_source_modal(self):
        self.doc_source_modal_open = not self.doc_source_modal_open

    def add_doc_source(self):
        if not self._doc_factory:
            self._doc_factory = self.avail_doc_sources[0]

        config_dict = list(self._doc_factory["auth_config"].values())[0]
        config_list, help_msg = self.get_config_list(config_dict)

        print("Config list: ", config_list)

        self.doc_source: UIDocSource = UIDocSource(
            factory_id=self._doc_factory["id"],
            name=self._doc_factory["system_name"],
            system_name=self._doc_factory["system_name"],
            auth_config={},
            config_list=config_list,
            help_msg = help_msg,
            tool_help = self._doc_factory.get("help") or "",
            owner_id = self.user.id + "",
            owner = self.user.username,
            logo_url=self._doc_factory["logo_url"],
        )
        self.doc_source.uses_oauth = 'strategy_oauth' in self._doc_factory["auth_config"]
        self.is_editing_docsource = False
        self.toggle_doc_source_modal()

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

    async def set_docsource_value(self, key: str, value: str):
        from .editor_state import EditorState

        setattr(self.doc_source, key, value)
        edit_state = await self.get_state(EditorState)
        edit_state.credentials_list_dirty = True


    def save_docsource(self):

        provider_data = {}
        for key, _, _ in self.doc_source.config_list:
            value = getattr(self.doc_source, key, None)
            if value:
                provider_data[key] = value
            
        print("Provider data being sent:", provider_data)
        
            
        self._save_docsource(provider_data)
        self.load_docsources()
        self.toggle_doc_source_modal()

    def _save_docsource(self, provider_data=None):
        print("Saving this doc source config: ", self.doc_source.dict())
        result = self._agentsvc.attach_docsource_to_index(
            self.user.tenant_id,
            self.user.id,
            self.index_id,
            self.doc_source.factory_id,
            self.doc_source.name,
            self.doc_source.folder_ids.split(",") if self.doc_source.folder_ids else [],
            self.doc_source.file_patterns.split(",") if self.doc_source.file_patterns else [],
            provider_data
        )
        self.doc_source.id = result["id"]

    def delete_doc_source(self, doc_config_id: str):
        if doc_config_id:
            self._agentsvc.delete_docsource(
                self.user.tenant_id,
                self.user.id,
                self.index_id,
                doc_config_id,
            )
            self.load_docsources()
        else:
            return rx.toast.error("No doc source config ID provided.")

    async def delete_doc(self, doc_id : str):
        self._agentsvc.delete_index_file(self.user.tenant_id, self.user.id, self.index_id, doc_id)
        if self.current_page >1 and len(self.index_files) == 1:
            self.current_page -= 1
        self.index_files = self._agentsvc.get_index_files(self.user.tenant_id, self.user.id, self.index_id,self.current_page)
        print(f"Deleted file")
        
    def oauth_authorize(self):
        print("Authorizing OAuth for doc source: ", self.doc_source.factory_id)
        # We have to save the doc_source first so we know it's ID
        # For OAuth sources, we don't need provider_data initially
        self._save_docsource({})  # Pass empty dict as provider_data
        self.authorize_url = self._agentsvc.get_docsource_authorize_url(
            self.user.tenant_id,
            self.index_id, 
            self.doc_source.id,
        )
        return rx.redirect(self.authorize_url)

    @rx.background
    async def on_authorize_callback(self, source_id: str, connection_id: str):
        self._agentsvc.authorize_callback(
            self.user.tenant_id, 
            self.index_id, 
            source_id, 
            {"connection_id" : connection_id}
        )
        async with self:
            self.load_docsources()
