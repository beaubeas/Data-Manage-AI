import asyncio
import reflex as rx
import pandas as pd

from .costs import calc_tokens_cents
from .models import Tenant, User, TenantMember

from .global_state import GlobalState

class SettingsState(GlobalState):
    # Existing credentials so we can update them
    user_secrets: list[tuple[str,str]] = []
    _secrets_to_delete: list[str] = []
    _new_secret_rows: set[int] = set()
    secrets_changed: bool = False
    tenant_name: str = ""
    avail_tenants: list[str] = []
    is_admin = False
    tenant_members: list[dict[str,str]] = []
    add_member_modal_open: bool = False
    new_member_email: str = ""
    new_member_role: str = "member"
    selected_tenant: str = ""

    # Usage related
    agent_data: pd.DataFrame = pd.DataFrame()
    model_data: pd.DataFrame = pd.DataFrame()

    def settings_page_load(self):
        if self.user.is_anonymous():
            return

        self.is_admin = False
        
        with rx.session() as sess:
            user = sess.get(User, self.user.id)
            if user:
                self.avail_tenants = []
                for member in user.memberships:
                    avail = f"{member.tenant.name} - {member.tenant.id}"
                    if member.tenant.id == user.tenant_id:
                        self.selected_tenant = avail
                    self.avail_tenants.append(avail)

                tenant = sess.get(Tenant, user.tenant_id)
                if tenant:
                    self.tenant_name = tenant.name
                    self.is_admin = user.is_tenant_admin(tenant.id)
                    self.tenant_members = [
                        {"email": member.user.emailval, "user_id": member.user.id, "role": member.role} 
                        for member in tenant.tenant_members
                    ]

        self.user_secrets = [(k, v) for k, v in self._agentsvc.user_secrets(self.user.tenant_id, self.user.id).items()]
        if len(self.user_secrets) == 0:
            self.add_secret()
        self.load_folders()
        self.load_usage()

    def load_usage(self):
        def format_cost(model, inputs, outputs):
            costs = calc_tokens_cents(model, inputs, outputs)
            cost = (costs[0] + costs[1])/100.0
            return f"${cost:.2f}"

        daily_stats = self._agentsvc.get_daily_usage(self.user.tenant_id, self.user.id)
        if "agents" in daily_stats and daily_stats["agents"]:
            self.agent_data = pd.DataFrame(daily_stats["agents"])
            if "agent_id" in self.agent_data.columns:
                self.agent_data.drop("agent_id", axis=1, inplace=True)
        else:
            self.agent_data = pd.DataFrame()

        if "models" in daily_stats and daily_stats["models"]:
            self.model_data = pd.DataFrame(daily_stats["models"])
            self.model_data["cost"] = self.model_data.apply(
                lambda row: format_cost(row["model"], row["input_tokens"], row["output_tokens"]),
                axis=1
            )
        else:
            self.model_data = pd.DataFrame()

    def set_username(self, value: str):
        if str(value) != "":
            with rx.session() as sess:
                self.user.name = value
                sess.add(self.user)
                sess.commit()
                sess.refresh(self.user)
                self.user = self.user

    def add_secret(self):
        self.user_secrets.append(("",""))

    def add_special_secret(self, key):
        if len(self.user_secrets) == 0:
            self.user_secrets.append((key, ""))
        else:
            if self.user_secrets[-1][0] == "":
                self.user_secrets[-1] = (key, "")
            else:
                self.user_secrets.append((key, ""))
        
    def save_secret_key(self, key: str, index: int):
        self.user_secrets[index] = (key, self.user_secrets[index][1])
        self._new_secret_rows.add(index)
        self.secrets_changed = True

    def save_secret_value(self, value: str, index: int):
        self.user_secrets[index] = (self.user_secrets[index][0], value)
        self._new_secret_rows.add(index)
        self.secrets_changed = True
    
    def delete_secret(self, index: int):
        self._secrets_to_delete.append(self.user_secrets[index][0])
        self.user_secrets.pop(index)
        self.secrets_changed = True
        
    def save_secrets(self):
        for key in self._secrets_to_delete:
            self._agentsvc.delete_secret(self.user.tenant_id, self.user.id, key)

        secrets = {self.user_secrets[row][0].strip(): self.user_secrets[row][1].strip() for row in self._new_secret_rows}
        if secrets:
            self._agentsvc.save_secrets(self.user.tenant_id, self.user.id, secrets)
        self._secrets_to_delete.clear()
        self._new_secret_rows.clear()
        self.secrets_changed = False

    def select_tenant(self, tenant_name_id: str):
        tenant_name, tenant_id = tenant_name_id.split(" - ")
        with rx.session() as sess:
            user = sess.get(User, self.user.id)
            if user:
                user.tenant_id = tenant_id
                sess.add(user)
                sess.commit()
                sess.refresh(user)
                self.user = user
                self.tenant_name = tenant_name
                # reload folders
                return SettingsState.settings_page_load

    def update_tenant_name(self, value: str):
        with rx.session() as sess:
            tenant = sess.get(Tenant, self.user.tenant_id)
            if tenant:
                tenant.name = value
                sess.add(tenant)
                sess.commit()
                sess.refresh(tenant)
                self.settings_page_load()

    def toggle_add_member_model(self):
        self.add_member_modal_open = not self.add_member_modal_open

    async def add_org_member(self):
        with rx.session() as sess:
            user = sess.get(User, self.user.id)
            if not user or not user.is_tenant_admin(user.tenant_id):
                return # safety perms check
        
        self.add_member_modal_open = False
        yield
        msg = ""
        with rx.session() as sess:
            existing = User.user_by_email(sess, self.new_member_email)
            if existing:
                membership = existing.lookup_membership(user.tenant_id)
                if membership is not None:
                    membership.role = self.new_member_role
                    sess.add(membership)
                else:
                    membership = TenantMember(
                        tenant_id=user.tenant_id, 
                        user_id=existing.id, 
                        role=self.new_member_role
                    )
                    sess.add(membership)
                sess.commit()
                msg = "Existing user added to the organization."
            else:
                msg = f"This person should sign up first, then you can add them to the Org." 
                #Invite email was sent to: {self.new_member_email}."
        await asyncio.sleep(0.5)
        self.settings_page_load()
        yield rx.window_alert(msg)

    def delete_org_member(self, user_id: str):
        with rx.session() as sess:
            user = sess.get(User, self.user.id)
            if not user or not user.is_tenant_admin(user.tenant_id):
                return # safety perms check

        if self.user:
            if user_id == self.user.id:
                return # don't remove yourself!
            with rx.session() as sess:
                tenant = sess.get(Tenant, self.user.tenant_id)
                if tenant:
                    membership = tenant.lookup_membership(user_id)
                    sess.delete(membership)
                    sess.commit()
                    self.settings_page_load()

    def update_member_role(self, user_id: str, new_role: str):
        with rx.session() as sess:
            current_user = sess.get(User, self.user.id)
            if not current_user or not current_user.is_tenant_admin(current_user.tenant_id):
                return  # safety perms check

            if user_id == current_user.id:
                return  # Prevent changing own role

            tenant = sess.get(Tenant, current_user.tenant_id)
            if tenant:
                membership = tenant.lookup_membership(user_id)
                if membership and membership.role != "owner":
                    membership.role = new_role
                    sess.add(membership)
                    sess.commit()
        
        self.settings_page_load()