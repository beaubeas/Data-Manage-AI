import asyncio
import json
import requests
import time
import hashlib
import os
from datetime import datetime, UTC
from pydantic import BaseModel


import rollbar

from .db import Credential
from supercog.shared.apubsub import pubsub
from supercog.shared.services import db_connect, get_service_host
from supercog.shared.models import RunLogBase
from supercog.shared.apubsub import EventRegistry, AgentEvent, AgentOutputEvent

engine = db_connect("engine") # ick - 2 different engines!
BASE = get_service_host("engine")

class RunningState:
    def __init__(self, initial_value: bool):
        self.flag = initial_value
        self.lock = asyncio.Lock()  # Protects access to `flag`

    async def set_running(self, value: bool):
        async with self.lock:
            self.flag = value

    async def is_running(self) -> bool:
        async with self.lock:
            return self.flag

class TriggerModel(BaseModel):
    tenant_id: str
    user_id: str
    agent_name: str
    agent_id: str
    agent_slug: str
    trigger: str
    trigger_arg: str
    created_at: datetime
    last_run: datetime|None

md5_hash= lambda s: hashlib.md5(s.encode('utf-8')).hexdigest()
TRIGGER_PASSKEY = md5_hash(os.environ['DATABASE_URL'])

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class Triggerable:

    # Base class for implementing new types of triggers
    def __init__(self, agent_dict: dict, run_state) -> None:
        self.agent_id = agent_dict['id']
        self.agent_name = agent_dict['name']
        self.agent_slug = agent_dict['agent_slug']
        self.tenant_id = agent_dict['tenant_id']
        self.user_id = agent_dict['user_id']
        self.trigger = agent_dict['trigger']
        self.trigger_arg = agent_dict['trigger_arg']
        self.run_state = run_state
        self.created_at: datetime = datetime.now(UTC)
        self.last_run: datetime|None = None

    async def run(self):
        # Poll for events and dispatch them (run agents)
        pass
    
    async def cancel(self):
        # Poll for events and dispatch them (run agents)
        pass
    
    def pick_credential(self, credentials: list[Credential]) -> bool:
        # find a credential you can use for the trigger
        return True

    def get_model(self) -> TriggerModel:
        return TriggerModel(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            agent_name = self.agent_name,
            agent_id = self.agent_id,
            agent_slug = self.agent_slug,
            trigger = self.trigger,
            trigger_arg = self.trigger_arg,
            created_at=self.created_at,
            last_run=self.last_run,
        )

    def client_headers(self) -> dict:
        return {
                "Authorization": f"Bearer {TRIGGER_PASSKEY}"
        }

    def create_run(self, message: str | dict):
        self.lat_run = datetime.now(UTC)
        if isinstance(message, dict):
            message = json.dumps(message, cls=DateTimeEncoder)

        run_data = {
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "input": message,
            "input_mode": "text",
            "turn_limit": 5,
            "timeout": 180,
            "result_channel": "test_results",
            "logs_channel": "logs",
        }
        response = requests.post(BASE + "/runs", json=run_data, 
                                 params={"user_email": "admin@supercog.ai"},
                                 headers=self.client_headers())
        if response.status_code != 200:
            msg = f"Error POSTing run for '{self.agent_name}': {response.text}"
            rollbar.report_message(msg, extra_data={"agent_id": self.agent_id, "query":message})
            raise RuntimeError(msg)
        return response.json()

    def continue_run(self, run_id, input_val):
        r = requests.post(BASE + f"/runs/{run_id}/input", json={"input": input_val}, headers=self.client_headers())
        if r.status_code != 200:
            msg = f"Error continuing run for '{self}': {r.text}"
            rollbar.report_message(msg, extra_data={"agent_id": self.agent_id})


    async def wait_for_agent_reply(self, reply_channel: str, timeout=90):
        def capture_event(event: dict) -> str:
            runlog = RunLogBase.model_validate(event)
            agevent: AgentEvent = EventRegistry.get_event(runlog)
            if isinstance(agevent, AgentOutputEvent):
                return agevent.str_result or str(agevent.object_result)
            else:
                return ""

        channel = await pubsub.subscribe(reply_channel) # type: ignore
        start = time.time()
        reply = ""
        while time.time() - start < timeout:
            message = await channel.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if message:
                print(message)
                try:
                    event = json.loads(message['data'])
                    yield capture_event(event)
                    if event.get("type") == "end":
                        message = await channel.get_message(ignore_subscribe_messages=True, timeout=0.5)
                        if message is None:
                            return
                        else:
                            # Seems like more messages, so keep going
                            event = json.loads(message['data'])
                            yield capture_event(event)
                except Exception as e:
                    print(e)


