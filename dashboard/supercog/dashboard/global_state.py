from datetime import timedelta, datetime, timezone
from sqlmodel import select, update, Session, delete

import reflex as rx

from supercog.dashboard.state_models import UIFolder
from supercog.shared.services import config
from supercog.shared import timeit

from .models import (
    AuthSession,
    User, 
    ANON_SENITINEL, 
    Agent, 
    Tenant,
    Folder,
    Tool,
)
from .engine_client import EngineClient

# Email registration variables
LOGIN_ROUTE = "/"
REGISTER_ROUTE = "/register"
AUTH_TOKEN_LOCAL_STORAGE_KEY = "_auth_token"
DEFAULT_AUTH_SESSION_EXPIRATION_DELTA = timedelta(days=14)
HOME_LINK = "/home"
RECENT_FOLDER = UIFolder(name="Recent", slug="recent", id=None, scope="private")
LOGO: str = "/homepage-logo1.png"

#agentsvc = EngineClient()

class GlobalState(rx.State):
    logo: str = "/homepage-logo1.png"
    service_status: str = ""
    markdown_modal_open: bool = False
    open_modals: dict[str,bool] = {}
    delete_items: dict[str,str] = {}
    new_folder_name: str = ""
    edit_folder_name: str = ""
    new_folder_modal_open: bool = False
    folders: list[UIFolder] = []
    _agentsvc: EngineClient = None

    # We have a "user_id" Var property for use on the front-end, but when we want to
    # pass the real string its nice to have a non-var attribute.
    _user_id: str = None
    user_is_admin: bool = False
    org_name: str = ""

    is_folder_shared: bool = False

    @rx.var
    def orgname(self) -> str:
        return self.org_name
    
    @rx.var
    def show_product_tour(self) -> bool:
        on_editor_page = "/edit" in self.router.page.path
        return on_editor_page and self.user and not self.user.user_has_flag("hide_edit_tour")
    
    @rx.var
    def show_sc_tour(self) -> bool:
        on_supercog_page = "/supercog" in self.router.page.path
        return on_supercog_page and self.user and not self.user.user_has_flag("hide_sc_tour")
    
    def signal_user_authenticated(self, user: User, session: Session):
        self.user = user
        tenant = session.get(Tenant, user.tenant_id)
        if tenant:
            self.org_name = tenant.name
        self.user_is_admin = user.is_admin
        self._user_id = str(user.id)

        return user

   
    ###############################################
    ## Code copied from AuthState
    ###############################################

    # The key is to user login is the 'auth_token' stored in localstorage. This value is
    # used as the 'session_id' in the AuthSession table. If the user has a valid for auth_token
    # and there exists a valid AuthSession record matching, then the user is "logged in".

    # The AuthSession is good until either it expires or it is deleted by the "do_logout".

    # The page protected decorator "require_login" checks the "is_authenticated", which
    # checks that self.authenticated_user is not the anonymous user. "authenticated_user"
    # looks up the AuthSession and the corresponding User, otherwise it returns the anonymous user.

    auth_token: str = rx.LocalStorage(name=AUTH_TOKEN_LOCAL_STORAGE_KEY)
    user: User = User(name=ANON_SENITINEL) 
    redirect_to: str = HOME_LINK
    
    @rx.var(cache=True)
    def authenticated_user(self) -> User:
        """The currently authenticated user, or a dummy user if not authenticated.

        Returns:
            A User instance with id=-1 if not authenticated, or the User instance
            corresponding to the currently authenticated user.
        """
        if self._agentsvc is None:
            self._agentsvc = EngineClient()

        with rx.session() as session:
            #print("Querying for auth session with: ", self.auth_token, " self: ", id(self))

            result = session.exec(
                select(User, AuthSession).where(
                    AuthSession.session_id == self.auth_token,
                    AuthSession.expiration
                    >= datetime.now(timezone.utc),
                    User.id == AuthSession.user_id,
                ),
            ).first()
            if result:
                user, auth_session = result
                #print(f"{id(self)} global set logging into agentsvc: {id(self._agentsvc)} with user {user.id}")
                self._agentsvc.user_login(
                    user.tenant_id, 
                    user.id,
                    name = user.name,
                    user_email = user.email,
                    timezone = user.timezone,
                )
                self.signal_user_authenticated(user, session)
                #print("Returning user ", user.name)
                return user
        #print("Returning anonymouse user because no session")
        return User(name=ANON_SENITINEL)

    @rx.var(cache=True)
    def user_id(self):
        return self.user.id
    
    @rx.var(cache=True)
    def is_authenticated(self) -> bool:
        """Whether the current user is authenticated.

        Returns:
            True if the authenticated user has a positive user ID, False otherwise.
        """
        return not self.authenticated_user.is_anonymous()
    
    @rx.var()
    def has_installed_slack(self) -> bool:
        if not self.is_authenticated:
            return False
        return bool(self.user.slack_user_id)
    
    def open_slack_modal(self, successful: bool):
        if successful:
            self.open_modals["slack_success"] = True
        else:
            self.open_modals["slack_failure"] = True

    def close_slack_modals(self):
        self.open_modals["slack_success"] = False
        self.open_modals["slack_failure"] = False

    def do_logout(self) -> None:
        """Destroy AuthSessions associated with the auth_token."""
        self.redirect_to = HOME_LINK
        with rx.session() as session:
            for auth_session in session.exec(
                select(AuthSession).where(AuthSession.session_id == self.auth_token)
            ).all():
                session.delete(auth_session)
            session.commit()
        self.auth_token = self.auth_token
        self._agentsvc.logout()
        self.reset()

    def scavange_auth_session(self, session: Session, session_id: str):
        statement = select(AuthSession).where(AuthSession.session_id == session_id)
        result = session.exec(statement).first()       
        if result:
            # Delete the record if found
            session.delete(result)
            session.commit()

    @rx.var()
    def get_query_params(self) -> str:
        raw_path_split = self.router.page.raw_path.split("?")
        query_param_string = ""
        if len(raw_path_split) > 1:
            query_param_string = f"?{raw_path_split[1]}"
        
        return query_param_string

    def redir(self) -> rx.event.EventSpec | None:
        """Redirect to the redirect_to route if logged in, or to the login page if not."""
        if not self.is_hydrated:
            # wait until after hydration to ensure auth_token is known
            return GlobalState.redir()  # type: ignore
        
        path = self.router.page.path
        query_param_string = self.get_query_params
    
        if not self.is_authenticated and path != LOGIN_ROUTE:
            print("Not logged, redir to home")
            self.redirect_to = path
            return rx.redirect(f"{LOGIN_ROUTE}{query_param_string}")
        elif (path == LOGIN_ROUTE or path == REGISTER_ROUTE) and self.is_authenticated:
            print("On the login route, redir to dest page or home")
            destination = self.redirect_to or HOME_LINK
            return rx.redirect(f"{destination}{query_param_string}")
    
    def remove_query_params(self) -> rx.event.EventSpec | None:
        path = self.router.page.path
        return rx.call_script(f"history.pushState(null, '', '{path}')")

    def _login(
        self,
        user_id: str,
        username: str,
        expiration_delta: timedelta = DEFAULT_AUTH_SESSION_EXPIRATION_DELTA,
    ) -> None:
        """Create an AuthSession for the given user_id.

        If the auth_token is already associated with an AuthSession, it will be
        logged out first.

        Args:
            user_id: The user ID to associate with the AuthSession.
            expiration_delta: The amount of time before the AuthSession expires.
        """
        if self.is_authenticated:
            self.do_logout()
        if username == ANON_SENITINEL:
            return
        self.auth_token = self.auth_token or self.router.session.client_token
        with rx.session() as session:
            self.scavange_auth_session(session, self.auth_token)
            session.add(
                AuthSession(  # type: ignore
                    user_id=user_id,
                    session_id=self.auth_token,
                    expiration=datetime.now(timezone.utc)
                    + expiration_delta,
                )
            )
            session.commit()

    ############################################
    @rx.var
    def get_server_host(self) -> str:
        url = str(self.router.page.host) + str(self.router.page.path)
        if not url.endswith("/"):
            url += "/" # production doesn't like the path with no trailing slash
        return url
        
    async def goto_edit_app(self, appid: str, folder_name: str|None=None, agent_name: str = "", success_modal_key: str = "") -> rx.event.EventSpec:
        from .editor_state import EditorState
        edit_state = await self.get_state(EditorState)
        await edit_state.clear_agent_state()
        self.loading_message = "Loading agent..."
        if appid.startswith("_supercog_") and not appid.startswith("_supercog_help"):
            return rx.redirect("/supercog/")
        

        if folder_name:
            folder_slug = Folder.name_to_slug(folder_name)
            return rx.redirect(f"/edit/{folder_slug}/{appid}")

        if agent_name and success_modal_key == "clone":
            return [rx.redirect(f"/edit/{appid}"), rx.toast.success(f"Cloned agent into: {agent_name}")]
        
        if agent_name and success_modal_key == "upload":
            return [rx.redirect(f"/edit/{appid}"), rx.toast.success(f"Uploaded agent: {agent_name}")]

        return rx.redirect(f"/edit/{appid}")

    def toggle_markdown_modal(self):
        self.markdown_modal_open = not self.markdown_modal_open


### MOVE TO a Component State
    def toggle_new_folder_modal(self):
        self.new_folder_name = ""
        self.new_folder_modal_open = not self.new_folder_modal_open

    def toggle_edit_folder_modal(self, edit_folder_name: str):
        self.new_folder_name = edit_folder_name or ""
        self.edit_folder_name = edit_folder_name
        self.new_folder_modal_open = not self.new_folder_modal_open

    def toggle_delete_modal(self, key: str, item: str):
        self.open_modals[key] = not self.open_modals.get(key, False)
        if item:
            self.delete_items[key] = item

    def permanently_hide_tour(self):
        self.toggle_delete_modal('tour', '')

        with rx.session() as session:
            u: User = session.get(User, self.user.id)
            if u:
                u.set_user_flag("hide_edit_tour")
                session.add(u)
                session.commit()
                session.refresh(u)

    def permanently_hide_sc_tour(self):
        self.toggle_delete_modal('sc_tour', '')

        with rx.session() as session:
            u: User = session.get(User, self.user.id)
            if u:
                u.set_user_flag("hide_sc_tour")
                session.add(u)
                session.commit()
                session.refresh(u)

    def ignore_change(self, val):
        # Allow us to set on_change handlers for form fields but ignore the changes
        pass

    async def global_delete_item(self, key: str):
        result = None
        if key in self.delete_items:
            type, name = self.delete_items[key].split(":")
            if type == 'folder':
                result = self.delete_folder(name)
            if type == 'agent':
                result = await self.delete_agent(name)
        self.open_modals[key] = False
        return result

    @timeit
    def load_folders(self, session = None):
        with (session or rx.session()) as sess:
            self.folders = [
                UIFolder(**folder.model_dump()) 
                for folder in 
                Folder.get_user_folders(sess, self.user.tenant_id, self.user.id)
            ]
            for f in self.folders:
                if f.scope == "shared":
                    f.folder_icon_tag = "folder-tree"

    @rx.var
    def folders_list(self) -> list[str]:
        return [f.name for f in self.folders]
        
    
    def create_new_folder(self):
        scope = "shared" if self.is_folder_shared else "private"
        if self.edit_folder_name != "":
            with rx.session() as sess:
                folder = sess.exec(
                    select(Folder).where(
                        Folder.name == self.edit_folder_name,
                        Folder.tenant_id == self.user.tenant_id,
                        Folder.user_id == self.user.id
                    )).first()
                if folder:
                    folder.name = self.new_folder_name
                    folder.scope = scope
                    folder.set_slug()
                    sess.add(folder)
                    sess.commit()
                    sess.refresh(folder)
                    self.load_folders()
                    self.edit_folder_name = ""
                    self.new_folder_name = ""            
        else:
            with rx.session() as sess:
                folder = Folder(
                    name=self.new_folder_name,
                    tenant_id=str(self.user.tenant_id),
                    user_id=str(self.user.id),
                    scope=scope,
                )
                folder.set_slug()
                sess.add(folder)
                sess.commit()
                sess.refresh(folder)
                self.load_folders()
                self.new_folder_name = ""
        self.is_folder_shared = False # Reset the checkbox state after creating/editing the folder
        self.new_folder_modal_open = False

    def delete_folder(self, folder_slug):
        print(f"Deleting folder: {folder_slug}")
        with rx.session() as sess:
            folder = sess.exec(select(Folder).where(Folder.slug == folder_slug)).first()
            if folder:
                folder_name = folder.name
                if not folder.is_deleteable:
                    return rx.toast.error("You cannot delete this folder")
                # Unparent all the agents using this folder
                update_stmt = (
                    update(Agent)
                    .where(Agent.folder_id == folder.id)
                    .values({"folder_id": None})
                )
                sess.execute(update_stmt)
                # Now delete the folder
                sess.delete(folder)
                sess.commit()
                self.load_folders()
                return [rx.toast.success(f"Successfully deleted folder: {folder_name}"), rx.redirect(HOME_LINK)]
            
    async def delete_agent(self, agent_id: str):
        print(f"Deleting agent: {agent_id}")
        with rx.session() as sess:
            # Kinda gross. Should use 'cascade' on the relation but 1:many relationships
            # don't play nice with JSON seralization.
            sess.exec(delete(Tool).where(Tool.agent_id == agent_id))
            agent = sess.get(Agent, agent_id)
            agent_name = agent.name
            sess.delete(agent)
            sess.commit()
        
        # This may be circular
        from .index_state import IndexState
        index_state = await self.get_state(IndexState)
        index_state.agent_list_dirty = True

        folder = self.lookup_folder()
        redirect = f"/agents/{folder.slug}" if folder else HOME_LINK

        return [rx.redirect(redirect), rx.toast.success(f"Successfully deleted agent: {agent_name}")]

    # We have the first page param as either a folder slug or an appid
    # If there is a second param then the first is the folder slug, otherwise it is the appid
    @rx.var
    def current_appid_and_folder(self) -> tuple[str, str|None]:
        folder_or_appid = self.router.page.params.get("folder_or_appid", None)
        optional_appid = self.router.page.params.get("appid", None)
        
        appid: str = ""
        folder_slug: str|None = folder_or_appid
        if optional_appid is None:
            appid = folder_or_appid
            folder_slug = None
        elif isinstance(optional_appid, list):
            appid = optional_appid[0]
        else:
            appid = optional_appid
        
        return appid, folder_slug

    @rx.var
    def current_appid(self) -> str:
        appid, _folder_slug = self.current_appid_and_folder
        return appid

    @rx.var
    def current_folder(self) -> str:
        # For the case when we are on an edit page
        _appid, folder_slug = self.current_appid_and_folder
        if folder_slug is not None:
            return folder_slug
        
        # For the case when we are on an index page
        folder_param = self.router.page.params.get("folder", None)
        # If still None default to recent
        if folder_param is None:
            return "recent"
        
        if isinstance(folder_param, list):
            return folder_param[0]
        
        return folder_param


    @rx.var
    def current_folder_name(self) -> str | None:
        folder_slug = self.current_folder
        for folder in self.folders:
            if folder.slug == folder_slug:
                return folder.name
            
        return None

    def lookup_folder(self, folder_slug=None):
        folder_slug = folder_slug or self.current_folder
        with rx.session() as sess:
            return Folder.lookup_user_folder(sess, self.user.tenant_id, self.user.id, folder_slug)
        
def require_login(page: rx.app.ComponentCallable) -> rx.app.ComponentCallable:
    """Decorator to require authentication before rendering a page. This
       decorator checks the "local user" authentication state - it says nothing
       about the Google auth or other browser state.

    Args:
        page: The page to wrap.

    Returns:
        The wrapped page component.
    """

    def protected_page():
        return rx.fragment(
            rx.cond(
                GlobalState.is_hydrated & GlobalState.is_authenticated,  # type: ignore
                page(),
                rx.chakra.box(
                    # When this spinner mounts, it will redirect to the login page
                    rx.chakra.spinner(
                        on_mount=GlobalState.redir,
                        size="lg",
                    ),
                    display="flex",
                    align_items="center",
                    justify_content="center",
                    width="100%",
                ),
            )
        )

    protected_page.__name__ = page.__name__
    return protected_page

require_google_login = require_login
