import random
import json
from typing import Optional, Any, Generator, Callable, List
import traceback
from datetime import datetime, timezone, timedelta
import logging


from passlib.context import CryptContext
from sqlmodel import (
    Column, 
    DateTime,
    Field, 
    func,
    JSON,
    Relationship,
    select,
    Session,
    SQLModel,
)
from sqlalchemy import or_, not_
from sqlalchemy.sql.expression import func

from supercog.shared.models import AgentCore, get_uuid4, DocIndexReference
from supercog.shared.utils import upload_bytes_to_s3, sanitize_string

from slack_sdk.oauth.installation_store import Installation

import reflex as rx
from reflex.utils.serializers import serializer

@serializer
def serialize_sqlmodel(sql_model: SQLModel) -> dict:
    try:
        ser = sql_model._serialize()
        return ser
    except:
        # print stacktrace
        traceback.print_exc()
        return sql_model.model_dump()
    
class SlackInstallation(rx.Model, table=True):
    __tablename__ = "slack_installations"

    id: str = Field(default_factory=get_uuid4, primary_key=True)
    app_id: Optional[str]
    bot_id: Optional[str]
    bot_scopes: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    bot_token: Optional[str]
    bot_user_id: Optional[str]
    enterprise_id: Optional[str]
    enterprise_name: Optional[str]
    enterprise_url: Optional[str]
    installed_at: float
    is_enterprise_install: bool
    team_id: Optional[str]
    team_name: Optional[str]
    token_type: Optional[str]
    user_id: str
    user_scopes: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
    user_token:  Optional[str]

    @classmethod
    def from_slack_installation(cls, slack_installation: Installation) -> 'SlackInstallation':
        return cls(
            app_id=slack_installation.app_id,
            bot_id=slack_installation.bot_id,
            bot_scopes=slack_installation.bot_scopes,
            bot_token=slack_installation.bot_token,
            bot_user_id=slack_installation.bot_user_id,
            enterprise_id=slack_installation.enterprise_id,
            enterprise_name=slack_installation.enterprise_name,
            enterprise_url=slack_installation.enterprise_url,
            installed_at=slack_installation.installed_at,
            is_enterprise_install=slack_installation.is_enterprise_install,
            team_id=slack_installation.team_id,
            team_name=slack_installation.team_name,
            token_type=slack_installation.token_type,
            user_id=slack_installation.user_id,
            user_scopes=slack_installation.user_scopes,
            user_token=slack_installation.user_token
        )

    def update_from_slack_installation(self, slack_installation:Installation):
        self.app_id=slack_installation.app_id
        self.bot_id=slack_installation.bot_id
        self.bot_scopes=slack_installation.bot_scopes
        self.bot_token=slack_installation.bot_token
        self.bot_user_id=slack_installation.bot_user_id
        self.enterprise_id=slack_installation.enterprise_id
        self.enterprise_name=slack_installation.enterprise_name
        self.enterprise_url=slack_installation.enterprise_url
        self.installed_at=slack_installation.installed_at
        self.is_enterprise_install=slack_installation.is_enterprise_install
        self.team_id=slack_installation.team_id
        self.team_name=slack_installation.team_name
        self.token_type=slack_installation.token_type
        self.user_id=slack_installation.user_id
        self.user_scopes=slack_installation.user_scopes
        self.user_token=slack_installation.user_token
    
    def to_slack_installation(self) -> Installation:
        return Installation(
            app_id=self.app_id,
            bot_id=self.bot_id,
            bot_scopes=self.bot_scopes,
            bot_token=self.bot_token,
            bot_user_id=self.bot_user_id,
            enterprise_id=self.enterprise_id,
            enterprise_name=self.enterprise_name,
            enterprise_url=self.enterprise_url,
            installed_at=self.installed_at,
            is_enterprise_install=self.is_enterprise_install,
            team_id=self.team_id,
            team_name=self.team_name,
            token_type=self.token_type,
            user_id=self.user_id,
            user_scopes=self.user_scopes,
            user_token=self.user_token
        )

class TenantMember(rx.Model, table=True):
    __tablename__ = "tenant_members"

    tenant_id: Optional[str] = Field(default=None, foreign_key="tenants.id", primary_key=True)
    user_id: Optional[str] = Field(default=None, foreign_key="users.id", primary_key=True)
    role: str = Field(default="member")

    tenant: "Tenant" = Relationship(back_populates="tenant_members")
    user: "User" = Relationship(back_populates="memberships")


class Tenant(rx.Model, table=True):
    __tablename__ = "tenants"
    id: str = Field(default_factory=get_uuid4, primary_key=True)

    # Email domain for the tenant
    domain: str
    name: str = Field(
        sa_column_kwargs=dict(server_default="New org")
    ) # Organization name
    tenant_members: List[TenantMember] = Relationship(back_populates="tenant")
    slack_team_id: Optional[str]
    #users: List["User"] = Relationship(back_populates="tenants", link_model=TenantMember)

    def lookup_membership(self, user_id: str) -> Optional[TenantMember]:
        return next((m for m in self.tenant_members if m.user_id == user_id), None)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logging.getLogger('passlib').setLevel(logging.ERROR)

ANON_SENITINEL = "__anonymous__"
# Hack to support our "guest" page runner for Agents
GUEST_USER_ID = "__guest_user__"

class User(rx.Model, table=True):
    _EMPTY_SENTINEL: str = '_empty'
    __tablename__ = "users"

    _is_anonymous: bool = False

    id: str = Field(default_factory=get_uuid4, primary_key=True)
    tenant_id: str
    gtoken_json: str = ""
    gtoken_sub: str = ""
    gtoken_email: str = ""
    gtoken_info_json: str = ""
    slack_user_id: str|None = Field(unique=True, nullable=True, index=True)

    # Local auth fields
    email: str|None = Field(unique=True, nullable=True, index=True)
    name: str|None = Field(nullable=True)
    password_hash: str|None = Field(nullable=True)
    enabled: bool = False
    is_admin: bool = False
    created_at: Optional[datetime] = Field(
        sa_column_kwargs=dict(server_default=func.current_timestamp())
    )

    def is_anonymous(self) -> bool:
        """Whether this user is an anonymous user."""
        return self.name == ANON_SENITINEL

    #tenants: List[Tenant] = Relationship(back_populates="users", link_model=TenantMember)
    memberships: List[TenantMember] = Relationship(back_populates="user")

    @property
    def timezone(self):
        return None # need to figure out where to get this
    
    @staticmethod
    def hash_password(secret: str) -> str:
        """Hash the secret using bcrypt.

        Args:
            secret: The password to hash.

        Returns:
            The hashed password.
        """
        return pwd_context.hash(secret)

    @classmethod
    def user_by_email(cls, session: Session, email: str) -> Optional["User"]:
        statement = select(User).where(or_(cls.email == email, cls.gtoken_email == email))
        return session.exec(statement).first()
    
    def verify(self, secret: str) -> bool:
        """Validate the user's password.

        Args:
            secret: The password to check.

        Returns:
            True if the hashed secret matches this user's password_hash.
        """
        return pwd_context.verify(
            secret,
            self.password_hash,
        )

    def set_google_empty(self):
        self.gtoken_json = self._EMPTY_SENTINEL
        self.gtoken_sub = self._EMPTY_SENTINEL
        self.gtoken_email = self._EMPTY_SENTINEL
        self.gtoken_info_json = self._EMPTY_SENTINEL

    # Tracks user lifecycle with bit flags comma separated 
    stage: str = ""

    def user_has_flag(self, flag: str) -> bool:
        return flag in self.stage.split(",")
    
    def set_user_flag(self, flag: str):
        if not self.user_has_flag(flag):
            self.stage = ",".join(self.stage.split(",") + [flag])

    def info(self) -> dict:
        if not self.gtoken_info_json:
            return {}
        if not hasattr(self, "__info"):
            if self.gtoken_info_json != self._EMPTY_SENTINEL:
                self.__info = json.loads(self.gtoken_info_json)
            else:
                self.__info = {}
        return self.__info

    def __getitem__(self, key: str) -> Any:
        if key == "name":
            return self.username
        elif key == "picture":
            return self.profileurl
        elif key == "email":
            return self.emailval
        else:
            return None
        
    @property
    def username(self) -> str:
        if self.name:
            return self.name
        return self.info()["name"]
    
    def file_folder_name(self) -> str:
        return self.username.lower().replace(" ", "_")
    
    @property
    def profileurl(self) -> str|None:
        if self.info():
            return self.info().get("picture")
    
    @property
    def emailval(self) -> str:
        return self.email or self.info()["email"]

    @property
    def email_domain(self) -> str:
        return self.emailval.split("@")[1]
    
    def lookup_tenant(self, session: Session) -> Optional[Tenant]:
        return session.get(Tenant, self.tenant_id)

    def owns_tenant(self, tenant_id: str) -> bool:
        return tenant_id in [m.tenant_id for m in self.memberships if m.role == 'owner']

    def is_tenant_admin(self, tenant_id: str) -> bool:
        return tenant_id in [m.tenant_id for m in self.memberships if m.role in ['owner','admin']]

    def lookup_membership(self, tenant_id: str) -> Optional[TenantMember]:
        return next((m for m in self.memberships if m.tenant_id == tenant_id), None)
   
class Tool(rx.Model, table=True):
    __tablename__ = "tools"

    id: str = Field(default_factory=get_uuid4, primary_key=True)

    # ID of the ToolFactory (exported by Engine service).
    # Strictly speaking a Tool could simply reference its `Credential`
    # and THAT would point to the ToolFactory.
    tool_factory_id: str
    tool_name: Optional[str] = None

    # Optional description so in case the user wants to use two
    # instances of a tool (connect to two databases, for example),
    # then they can distinguish them.
    description: Optional[str] = None
    agent_id: str = Field(foreign_key="agents.id", ondelete="CASCADE")
    created_at: Optional[datetime] = Field(
        sa_column_kwargs=dict(server_default=func.current_timestamp())
    )

    #agent: Optional["Agent"] = Relationship(
    #    #back_populates="tools",
    #)

    # Pointer to the credential used by this Tool
    credential_id: Optional[str] = Field(default=None)


class ToolMapper(Tool):
    credential_name: str = ""

class Folder(rx.Model, table=True):
    __tablename__ = "folders"
    name: str
    scope: str = "private"
    slug: str = ""

    id: str = Field(default_factory=get_uuid4, primary_key=True)
    parent_folder_id: str = Field(foreign_key="folders.id", nullable=True, default=None)

    user_id: str = Field(foreign_key="users.id", nullable=True, default=None)
    tenant_id: str = Field(foreign_key="tenants.id", nullable=True, default=None)

    folder_icon_tag: str = Field(default="folder")

    def set_slug(self):
        self.slug = sanitize_string(self.name)

    @classmethod
    def name_to_slug(cls, name: str) -> str:
        return sanitize_string(name)
                               
    @property
    def is_deleteable(self) -> bool:
        return self.name not in ["Shared", "Recent"]
    
    @classmethod
    def get_user_folders(cls, session, tenant_id, user_id):
        sel = select(Folder).where(
            Folder.tenant_id == tenant_id,
            or_(Folder.user_id == user_id, Folder.scope == "shared")
        ).order_by(Folder.scope)
        return session.exec(sel).all()

    @classmethod
    def lookup_user_folder(cls, session, tenant_id, user_id, folder_slug) -> Optional["Folder"]:
        sel = select(Folder).where(
            Folder.slug == folder_slug,
            Folder.tenant_id == tenant_id,
            or_(Folder.user_id == user_id, Folder.scope == "shared")
        )
        return session.exec(sel).first()

    @classmethod
    def lookup_shared_folder(cls, session, tenant_id, folder_slug) -> Optional["Folder"]:
        sel = select(Folder).where(
            Folder.slug == folder_slug,
            Folder.tenant_id == tenant_id,
            Folder.scope == "shared",
        )
        return session.exec(sel).first()

class Agent(AgentCore, table=True):
    __tablename__ = "agents"

    id: str = Field(default_factory=get_uuid4, primary_key=True)
    scope: str = "private" # one of 'private' or 'shared'
    user_id: str = Field(foreign_key="users.id", nullable=True, default=None)
    folder_id: str = Field(foreign_key="folders.id", nullable=True, default=None)
    
    tenant_id: str
    avatar_url: str|None=None
    avatar_blob: bytes = b''
    prompts_json: Optional[str] = ""
    updated_at: Optional[datetime] = Field(
        sa_column_kwargs=dict(server_default=func.current_timestamp())
    )

    tools: list["Tool"] = Relationship(sa_relationship_kwargs={"lazy":"selectin"})

    def uses_dynamic_tools(self) -> bool:
        return any([t.tool_factory_id == "auto_dynamic_tools" for t in self.tools])
    
    @classmethod
    def calc_system_agent_id(cls, tenant_id: str, user_id: str|None=None, agent_name: str="unknown"):
        slug = sanitize_string(agent_name)
        if user_id:
            user_id = f"_{str(user_id)[0:20]}"
        else:
            user_id = ""
        return f"_{slug}_{str(tenant_id)[0:20]}{user_id}"

    @classmethod
    def agents_by_folder(cls, session, tenant_id, user_id, folder_id, sort: str="recent", limit:int=0) -> list["Agent"]:
        query = select(Agent).where(
            Agent.tenant_id==tenant_id
        )
        if user_id:
            query = query.where(Agent.user_id == user_id, not_(Agent.id.like('\\_supercog%')))
        if folder_id != "__any__":
            query = query.where(Agent.folder_id == folder_id)

        if sort == 'recent':
            # The logic is to limit window to prior 6 months. But this is mostly to skip
            # showing Demo agents which we backdate to 12 months updated.
            query = (
                query.order_by(Agent.updated_at.desc())
                .where(Agent.updated_at > datetime.now(timezone.utc) - timedelta(days=180))
            )
        else:
            query = query.order_by(Agent.name)
        
        if limit > 0:
            query = query.limit(limit)

        #logger.debug("*** AGENT FOLDER QUERY: ", str(query), "user_id", user_id, "folder_id", folder_id, "sort", sort)
        return session.exec(query).all()

    @classmethod
    def agents_any_folder(cls, session, tenant_id, user_id, sort: str="recent", limit:int=0) -> list["Agent"]:
        return cls.agents_by_folder(session, tenant_id, user_id, "__any__", sort, limit)

    def __lt__(self, other):
        return self.updated_at > other.updated_at
    
    def network_dump(self):
        res = self.model_dump(exclude={'avatar_blob','avatar_url','updated_at'})
        if res['system_prompt']:
            res['system_prompt'] = self.strip_comments(res['system_prompt'].strip())
        res.update({"tools": json.dumps([t.model_dump() for t in self.tools], default=str)})
        return res

    def strip_comments(self, prompt):
        if prompt is None:
            return None
        lines = prompt.split("\n")
        return "\n".join([
            line for line in lines 
            if (
                not line.startswith("#")
            )
        ])
    
    def get_help_message(self):
        # Parse any initial comments from the system_prompt as the "help" message for the agent
        help_lines = []
        if self.system_prompt:
            for line in self.system_prompt.split("\n"):
                if line.startswith("#"):
                    help_lines.append(line[1:].strip('#').strip())
                else:
                    break
        return "\n".join(help_lines)
        
    def update_from_state(
            self, 
            agent_state: Any,
            folder_id: str, 
            doc_indexes: list["UIDocIndex"],
        ):
        from .state_models import AgentState

        astate: AgentState = agent_state
        for key, value in astate.dict().items():
            if key not in ['id',
                           'user',
                           'tools',
                           'uitools',
                           '_user_id',
                           'avatar',
                           'trigger_prefix',
                           'folder_name',
                           'folder_slug',
                           'is_folder_header',
                           'folder_icon_tag',
                           'help_message',
                           'index_list',
                           'agent_email']:
                if key == "prompts":
                    self.prompts_json = json.dumps(value)
                elif key == "temperature":
                    setattr(self, key, float(value))
                else:
                    setattr(self, key, value)

        print("Saving agent, current doc indexes are: ", [d.dict() for d in doc_indexes])
        index_names = [i.strip() for i in astate.index_list.split(",")]
        enabled = []
        for index in index_names:
            for doc_index in doc_indexes:
                if doc_index.name == index:
                    enabled.append(DocIndexReference(name = index, index_id=doc_index.id))
                    continue
        self.enabled_indexes = json.dumps([ref.dict() for ref in enabled])
        astate.index_list = ",".join([i.name for i in enabled]) #push back to UI model in case an index wasnt found

        self.folder_id = folder_id
        self.updated_at = datetime.now(timezone.utc)
        self.make_agent_slug()

    def make_agent_slug(self):
        if self.agent_slug:
            return
        words = [w.strip() for w in self.name.lower().split(" ")]
        word_count = len(words)
        if word_count == 0:
            return        
        # Start with an equal distribution of characters per word
        max_length = 13
        initial_prefix_length = max_length // word_count
        remainder = max_length % word_count
        
        prefixes = []
        # First pass: assign initial lengths to each prefix
        for i in range(word_count):
            if len(words[i]) < initial_prefix_length:
                prefixes.append(words[i])
            else:
                prefixes.append(words[i][:initial_prefix_length])
        
        self.agent_slug = ''.join(prefixes) + str(random.randint(1,99))

    def get_agent_email_address(self) -> str:
        if not self.agent_slug:
            self.make_agent_slug()
        return f"{self.agent_slug}@mail.supercog.ai"

    # Match tools selected in the UI with those in the db. If a new tool
    # then create a new tool record. If a tool was removed then delete it.
    def resolve_tools(
            self,
            uitools: list["UITool"],
        ) -> Generator[tuple[Tool,bool], None, None]:

        keep_tools = set([t.tool_id for t in uitools if t.tool_id])
        for tool in uitools:
            if not tool.tool_id:
                real_tool = Tool(
                    tool_name=tool.name,
                    tool_factory_id=tool.tool_factory_id,
                    agent_id=self.id,
                    credential_id=tool.credential_id,
                    created_at=None,
                )
                yield (real_tool, True)
                keep_tools.add(str(real_tool.id))

        for real_tool in self.tools:
            if str(real_tool.id) not in keep_tools:
                yield (real_tool, False)

    def upload_image_to_s3(self):
        if self.avatar_blob:
            key = str(random.randint(1, 10000))
            object_name = f"avatar-{self.id}-{key}.png"
            url = upload_bytes_to_s3(object_name, self.avatar_blob, "image/png")
            self.avatar_url = url

    def to_yaml_dict(self, cred_names: dict[str,str]) -> dict:
        res = {}
        for k in ['name','id', 'welcome_message', 'description','system_prompt','model',
                  'trigger','trigger_arg','scope','avatar_url','prompts_json', 'memories_json']:
            res[k] = getattr(self, k)

        toolsdump = [
            {"tool_name":t.tool_name,
             "tool_factory_id": t.tool_factory_id,
             "credential_name": cred_names.get(t.credential_id or "", ""),
            } for t in self.tools
        ]
        res['tools'] = toolsdump
        return res

    @staticmethod
    def create_from_dict(opts: dict, session: Session, tool_info_fn: Callable) -> "Agent":
        if 'id' in opts:
            del opts['id']
        tools = opts.pop('tools')
        while session.exec(select(Agent).where(Agent.name == opts['name'])).first() is not None:
            opts['name'] = opts['name'] + "-copy"
        agent = Agent(**opts)
        session.add(agent)
        session.commit()
        session.refresh(agent)

        # Attempt to map exported tool descriptions to our local Tools
        for topts in tools:
            tool = ToolMapper(
                tool_factory_id=topts['tool_factory_id'], 
                credential_name=topts.get('credential_name'),
                agent_id=agent.id,
                created_at=None,
            )
            local_tool:dict = tool_info_fn(tool)
            real_tool = Tool(
                agent_id=agent.id,
                tool_factory_id=local_tool['tool_factory_id'],
                tool_name=local_tool['name'],
                credential_id=local_tool['credential_id'],
                created_at=None,
            )
            session.add(real_tool)
            session.commit()

        session.refresh(agent)
        return agent


class Lead(rx.Model, table=True):
    __tablename__ = "leads"
    id: str = Field(default_factory=get_uuid4, primary_key=True)
    email: str
    request: Optional[str] = Field(default=None, nullable=True)
    created_at: Optional[datetime] = Field(
        sa_column_kwargs=dict(server_default=func.current_timestamp())
    )


# Taken from Reflex local_auth example.  This stores a login session
# that links the Reflex client_token (generated per tab) to the User
# record.
    
class AuthSession(
    rx.Model,
    table=True,  # type: ignore
):
    """Correlate a session_id with an arbitrary user_id."""

    user_id: str = Field(index=True, nullable=False)
    session_id: str = Field(unique=True, index=True, nullable=False)
    expiration: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False),
    )

######### ADMIN SCRIPTS #########

def upload_blob_avatars(session):
    agents = session.exec(select(Agent)).all()
    for agent in agents:
        if agent.avatar_blob:
            print(agent.name)
            agent.upload_image_to_s3()
            session.add(agent)
            session.commit()

def clear_avatar_blobs(session):
    agents = session.exec(select(Agent)).all()
    for agent in agents:
        print(agent.name)
        agent.avatar_blob = b''
        session.add(agent)
        session.commit()

def setup_shared_folder(session, tenant_id) -> Folder:
    tenant = session.get(Tenant, tenant_id)
    existing = session.exec(select(Folder).where(Folder.tenant_id == tenant.id, Folder.name=="Shared", Folder.scope == "shared")).first()
    if existing:
        return existing # shared folder already exists
    shared_folder = Folder(name="Shared", scope="shared", tenant_id=str(tenant.id))
    shared_folder.set_slug()
    session.add(shared_folder)
    session.commit()
    session.refresh(shared_folder)
    for agent in session.exec(
        select(Agent).where(Agent.tenant_id == tenant.id, Agent.scope == "shared")
    ).all():
        agent.folder_id = shared_folder.id
        session.add(agent)
    session.commit()
    return shared_folder

# We are moving from a "domain shared" tenant model to one where each user gets
# their own Tenant by default. Users have to invite other users to join their
# tenant. So we load each User and create their Tenant and make them the owner of same.
#
# Then we need to update each Agent owned by the User to reference their Tenant.
def create_new_tenants(session):
    breakpoint()
    cred_update_sql = []
    secrets_update_sql = []
    for user in session.exec(select(User)).all():
        if len(user.memberships) > 0:
            continue # assume we've setup this user already
        print("Upgrading: ", user.id, user.emailval)
        tenant = Tenant(domain=user.email_domain, name=user.username + " Org")
        session.add(tenant)
        session.commit()
        session.refresh(tenant)
        old_tenant_id = user.tenant_id
        user.tenant_id = tenant.id
        session.add(user)
        session.commit()
        session.refresh(user)
        # Need to re-assign Agentsvc credentials to the new tenant
        cred_update_sql.append(
            f"UPDATE credentials SET tenant_id='{tenant.id}' WHERE tenant_id='{old_tenant_id}' and user_id='{user.id}';"
        )
        secrets_update_sql.append(
            f"UPDATE credentialsecret SET tenant_id='{tenant.id}' WHERE tenant_id='{old_tenant_id}' and user_id='{user.id}';"
        )
        # Re-assign user's folders to the new Tenant
        users_folder_ids = []
        for folder in Folder.get_user_folders(session, old_tenant_id, user.id):
            users_folder_ids.append(folder.id)
            folder.tenant_id = tenant.id
            session.add(folder)
        session.commit()
        share_folder = setup_shared_folder(session, tenant.id)
        member = TenantMember(tenant_id=tenant.id, user_id=user.id, role="owner")
        session.add(member)
        session.commit()
        session.refresh(member)
        for agent in session.exec(select(Agent).where(Agent.user_id == user.id)).all():
            agent.tenant_id = tenant.id
            if agent.folder_id and agent.folder_id not in users_folder_ids:
                # agent was probably in a Shared folder owned by the old Tenant
                # link it to the new Shared folder just so we dont lose it
                agent.folder_id = share_folder.id
            session.add(agent)
        session.commit()
        session.refresh(agent)

        # Re-anchor the User's folders to their new Tenant
        for folder in Folder.get_user_folders(session, tenant.id, user.id):
            folder.tenant_id = tenant.id
            session.add(folder)
        session.commit()
    print("Run this on monster_engine:")
    print("\n".join(cred_update_sql))
    print("Run this on monster_credentials:")
    print("\n".join(secrets_update_sql))

def remove_user(session, user_id=None, email=None):
    if user_id is not None:
        user = session.get(User, user_id)
    elif email is not None:
        user = session.exec(select(User).where(or_(User.email == email, User.gtoken_email==email))).first()
    if user:
        print("Confirm Remove this User?: ", user)
        val = input("Type 'yes' to confirm: ")
        if val != "yes":
            return
        for tenant_member in user.memberships:
            session.delete(tenant_member)
        user = session.exec(select(User).where(User.email == email)).first()

        for agent in session.exec(select(Agent).where(Agent.user_id == user.id)).all():
            print("Removing agent: ", agent.name)
            for tool in agent.tools:
                session.delete(tool)
            session.delete(agent)
        session.commit()

        session.delete(user)
        session.commit()
