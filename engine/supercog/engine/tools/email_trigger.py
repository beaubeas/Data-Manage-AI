import asyncio
from fastapi import FastAPI, Depends, HTTPException, Path, status

from supercog.shared.services    import config, serve, db_connect
from supercog.shared.models      import RunCreate, AgentBase
from supercog.shared.pubsub      import pubsub
from supercog.shared.credentials import secrets_service

from sqlmodel import SQLModel, Field, Session, create_engine, select


from supercog.engine.db       import session_context
from supercog.shared.services  import config, db_connect
from sqlmodel                import Session

from pytz import utc

import re

class EmailTriggerable(Triggerable):
    def __init__(self, agent_dict: dict, run_state) -> None:
        super().__init__(agent_dict, run_state)

        # The email trigger needs credentials to run.
        # What we do below is search the trigger name for those credentials
        # When we create the list of trigger names for the user to select
        # in the GUI, we store the credential in parens after the system name.
        # our Gmail system name already has parens in it so we look for the
        # second set of parens.
        matches = re.findall(r'\(([^)]+)\)', self.trigger)
        if len(matches) >= 2:
            second_paren_contents = matches[1]  # 'Gmail for demos'
            self.cred_name = second_paren_contents
        else:
            print(f"search of trigger {self.trigger} yeilded {matches}")

    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        return trigger.startswith("Gmail (app password)")

    async def run(self):
        # Poll for events and dispatch them (run agents)
        print("Gmail Credentials: ",self.email_address, self.app_password)
        result = await pollForGmail(self.trigger_arg,
                                    self.tenant_id,
                                    self.user_id,
                                    self.agent_id,
                                    "Gmail",  # FIXME: hardcoded to gmail for now. This will become a part of credentials for this connection eventually.
                                    self.email_address,
                                    self.app_password)
        return result


    def pick_credential(self, credentials) -> bool:
        # find a credential you can use for the trigger
        for cred in credentials:
            if (
                cred.name == self.cred_name and 
                (cred.user_id == self.user_id or (
                    cred.tenant_id == self.tenant_id and
                    cred.scope == "shared"
                ))
            ):
                secrets = cred.retrieve_secrets()
                if 'email_address' not in secrets:
                    print("Email cred {cred.name} has no email_address secret")
                    return False
                self.email_address = secrets['email_address']
                if 'app_password' not in secrets:
                    print("Email cred {cred.name} has no app_password secret")
                    return False
                self.app_password = secrets['app_password']
                return True
        return False


