import arrow
import os
import reflex as rx
import pandas as pd
from uuid import UUID
from datetime import datetime, timezone

from .global_state import GlobalState

def convert_uuid_to_string(value):
    if isinstance(value, UUID):
        return str(value)
    return value

class AdminState(GlobalState):
    agents_df: pd.DataFrame = pd.DataFrame([])
    runs_df: pd.DataFrame = pd.DataFrame([])
    agents_info : pd.DataFrame = pd.DataFrame([])

    agents_sha: str = ""
    agents_start_time: str = ""
    agents_address: str = ""

    @rx.var
    def git_sha(self) -> str:
        sha = None
        if os.path.exists("/app/GIT_SHA"):
            sha = open("/app/GIT_SHA").read().strip()
        if not sha and os.path.exists("GIT_SHA"):
            sha = open("GIT_SHA").read().strip()
        if sha:
            return f"{sha[0:7]} - {sha[-7:]}"
        else:
            return "<not set>"
        
    def admin_page_load(self):
        print("Admin is: ", self.user_is_admin)
        if not self.user_is_admin:
            return rx.redirect("/agents")
        
        admin_info = self._agentsvc.get_admin_info(self.user.tenant_id)

        if admin_info:
            agents, runs, info = admin_info

            sha = info.get("git_sha", "")
            if "start_time" in info:
                start_time = arrow.get(info.get("start_time")).humanize()
            else:
                start_time = "?"
            address = info.get("address", "")
            self.agents_info = pd.DataFrame([
                {"name": "Agents SHA", "value": sha},
                {"name": "Dashboard SHA", "value": self.git_sha},
                {"name": "Agents Start Time", "value": start_time},
                {"name": "Agents Address", "value": address},
            ])

            df = pd.DataFrame(agents)
            self.agents_df = df

            df = pd.DataFrame(runs)
            df['id'] = df['id'].apply(lambda x: str(x))
            df['created_at'] = df['created_at'].apply(lambda x: arrow.get(x).humanize())
            df = df[['tenant_id','user_id','id','name','created_at','status']]

            self.runs_df = df

