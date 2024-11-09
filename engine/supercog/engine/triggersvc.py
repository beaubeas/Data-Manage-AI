import os
import asyncio
import inspect
import json
from pprint import pprint
from typing import Type, Optional, Callable, AsyncIterator

from sqlmodel import Session, select
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import rollbar
from rollbar.contrib.fastapi import add_to as rollbar_add_to

from .db import lifespan_manager

from supercog.shared.services import db_connect, get_service_host, serve, config
from supercog.shared.logging import logger
from supercog.shared.apubsub import pubsub, AGENT_EVENTS_CHANNEL
from .tools.slack_tool import run_slack_app

from .db import Agent, Credential
import supercog.engine.all_triggers
from supercog.engine.all_triggers import SNSTriggerable
from .triggerable import RunningState, Triggerable, TriggerModel
from supercog.engine.tools.scheduler import internal_get_jobs, internal_cancel_job

from supercog.shared.services import config

engine = db_connect("engine") # ick - 2 different engines!
SERVICE = "triggersvc"
fastapi_app = FastAPI(lifespan=lifespan_manager)
rb_token = os.environ.get("ROLLBAR_TOKEN")
if rb_token:
    rb_env = os.environ.get("ENV", "dev")
    print("CONNECTING TO ROLLBAR: ", rb_token[0:5], rb_env)
    rollbar.init(rb_token, environment=rb_env)
    rollbar_add_to(fastapi_app)

class TriggerService:
    # Service for managing triggers
    def __init__(self):
        self.triggers: list[Triggerable] = []
        self.tasks: list[asyncio.Task] = []
        self.keep_polling: list[bool] = [True]
        self.run_state = RunningState(True)

    def get_trigger_type(self, trigger: str) -> Type | None:
        # List all classes in 'your_module'
        for name, obj in inspect.getmembers(supercog.engine.all_triggers):
            if inspect.isclass(obj):
                if obj.handles_trigger(trigger):
                    return obj
        return None

    async def load_triggers(self) -> list[asyncio.Task]:
        tasks: list[asyncio.Task] = []

        with Session(engine) as session:
            credentials = session.exec(select(Credential)).all()
            agents = session.exec(select(Agent)).all()
            for agent in agents:
                if agent.trigger == 'Chat box':
                    continue
                kls = self.get_trigger_type(agent.trigger)
                if not kls:
                    logger.error(f"Unknown trigger type '{agent.trigger}' for Agent {agent.name}")
                    continue
                trigger = kls(agent.model_dump(), self.run_state)
                if not trigger.pick_credential(credentials):
                    logger.error(f"Couldn't find credential for Agent {agent.name} trigger '{agent.trigger}'")
                    continue
                print(f"Scheduling trigger {trigger.__class__} for agent: {agent.name}")
                self.tasks.append(asyncio.create_task(trigger.run()))
                self.triggers.append(trigger)

        return tasks

    async def reload_triggers(self, channel, event):
        if event['type'] == 'agent_saved':
            # FIXME: we should just reload the trigger for the saved agent
            print("Received REDIS signal, stopping current triggers...")
            await self.run_state.set_running(False)
            for t in self.tasks:
                await t
            await self.run_state.set_running(True)
            print("Reloading triggers")
            self.triggers.clear()
            await self.load_triggers()

    def dispatch_incoming_email(self, target_slug: str, email_msg: str):
        didrun = False
        for t in self.triggers:
            if t.agent_slug == target_slug:
                didrun = True
                t.create_run(email_msg)
        if not didrun:
            logger.error(f"Couldn't find any agent trigger for email to slug '{target_slug}'")


trigger_svc = TriggerService()

@fastapi_app.get("/help")
async def help():
    # Return the avail ToolFactories which describe all of our available tools
    return "Get info about running triggers"

#
# calls for APScheduler jobs
#

from typing import List, Dict, Any
    
@fastapi_app.get("/tenant/{tenant_id}/get_jobs")
async def get_jobs(tenant_id: str) ->List[Dict[str, Any]]:
    """ :return -- list of APScheduler jobs"""
    try:
        jobs = internal_get_jobs()
        print (jobs)
        return jobs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/tenant/{tenant_id}/cancel_job")
async def cancel_jobs(job_id: str) ->str:
    """ call the APScheduler cancel jobs"""
    try:
        internal_cancel_job(job_id)
        return(f"Job: {job_id} canceled")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


#
# Calls for generic Trigger functions.
#

@fastapi_app.get("/tenant/{tenant_id}/triggers")
async def get_triggers(tenant_id: str) -> list[TriggerModel]:
    """ :return -- list of triggers"""
    model = [t.get_model() for t in trigger_svc.triggers if t.tenant_id == tenant_id]
    print(f"--------> model - {model}")
    return model

@fastapi_app.get("/tenant/{tenant_id}/cancel_trigger")
async def cancel_trigger(tenant_id: str, agent_id: str) -> str:
    """
    Call the cancel function on the trigger for a specific tenant.
    
    Args:
    tenant_id (str): The ID of the tenant.
    agent_id (str):  The agent ID of the trigger to cancel.
    
    Returns:
    str: Confirmation message of cancellation.
    """
    try:
        for index, t in enumerate(trigger_svc.triggers):
            if t.tenant_id == tenant_id and t.agent_id == agent_id:
                del trigger_svc.triggers[index]  # Remove the trigger from the list
                await t.cancel()                 # Properly await the coroutine
                return f"Trigger for agent {agent_id} canceled and removed successfully."
        return f"Unable to find or cancel trigger for agent {agent_id}."
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.post("/email_handler")
async def email_handler(request: Request):
    processed = await SNSTriggerable.parse_sns_notification(request)
    if 'agent_slug' in processed:
        print("Dipatching message:\n", processed['email_msg'])
        trigger_svc.dispatch_incoming_email(processed['agent_slug'], processed['email_msg'])
    else:
        print("Result from SNS notification parsing: ", processed)

    return JSONResponse(status_code=status.HTTP_200_OK, content={"message": "Received"})


@lifespan_manager.add
async def lifespan(app: FastAPI) -> AsyncIterator:
    await trigger_svc.load_triggers()
    await pubsub.subscribe(AGENT_EVENTS_CHANNEL, trigger_svc.reload_triggers)
    if os.environ.get("DISABLE_SLACKBOT"):
        print("Slackbot is disabled by env")
    else:
        asyncio.create_task(run_slack_app())
    yield



    
if __name__ == "__main__":
    print("Starting FastAPI on ", config.get_port(SERVICE))
    serve(fastapi_app, SERVICE)
