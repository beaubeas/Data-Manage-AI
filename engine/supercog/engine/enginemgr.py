# The EngineManager manages all the running ChatEngine (agent) instances.
# You must have saved the agent first, then call:
#
# EngineManager.create_run -> start a new agent run
# EngineManager.continue_run -> send the next user input
#
# both methods call EngineManager.dispatch_input which invokes the agent
# via the ChatEngine.respond method. That method yields AgentEvents, and those
# are then wrapped in RunLog events and published to Redis.

import asyncio
from datetime import datetime, timedelta
from uuid import UUID
import os
import time
from typing import Optional, Callable
import traceback
import asyncio
import redis.asyncio as redis
import json
import uuid
import sys
import time
import signal
from typing import ClassVar, Literal
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field
import pandas as pd

from fastapi import HTTPException
from sqlmodel import Session
import rollbar

from supercog.shared import start_timeit, end_timeit
from supercog.shared.services import config
from supercog.shared.services import db_connect
from supercog.shared.models import ToolBase
from supercog.shared.apubsub import (
    pubsub, AGENT_EVENTS_CHANNEL, 
    AgentEvent,
    AgentErrorEvent,
    AgentLogEventTypes, 
    RunCreatedEvent,
    AgentInputEvent,
    AgentOutputEvent,
    AgentEndEvent,
    AddMemoryEvent,
    AgentSavedEvent,
    AssetTypeEnum,
)

from supercog.shared.logging import logger
from supercog.shared.utils import (
    upload_file_to_s3, 
    get_file_mimetype, 
)

from .chatengine import ChatEngine
from .chat_logger import chat_logger

from .db import Run, RunLog, Agent, session_context
from .db import lifespan as db_lifespan, reset_db_connections
from .run_context import RunContext
from .jwt_auth import User

from .filesystem import (
    get_user_directory,
    get_agent_filesystem, 
    list_modified_files, 
)

EventCallback = Callable[[AgentEvent], None]

IDLE_TIMEOUT = int(config.get_option("AGENT_WORKER_IDLE", default=120))  # Seconds before we exit from no activity

class AgentTask(BaseModel):
    action: str
    user: dict
    run: dict 
    run_input: dict = {}   
    headers: dict
    query_params: dict

    ACTION_CREATE_RUN: ClassVar[Literal["create_run"]] = "create_run"
    ACTION_PROMPT: ClassVar[Literal["prompt"]] = "prompt"

    def get_user(self):
        return User(**self.user)
class EngineManager:
    # Manages creating and running ChatEngine instances which are instances of
    # executing agents.

    # Map of user id's to running engines. We should clone this map via Redis, but note
    # that requires we can pickle the full ChatEngine object.
    RUNNING_ENGINES: dict[UUID, ChatEngine] = {} 
    END_EVENT = {"type": "end"}

    def __init__(self, tenant_id_list: list[str]):
        self.tenant_id_list = tenant_id_list
        self.group_name = 'consumer_group'
        self.consumer_name = f'consumer_{"-".join(tenant_id_list)}'
        self.heartbeat_interval = 5  # seconds
        self.shutdown_event = asyncio.Event()
        self.redis = None
        self.dbengine = db_connect("engine") 
        self.last_event = time.time()
        self.subscribed: bool = False
        # Locks for each chatengine to prevent concurrent access, which can happen if you
        # modify an agent while it is running a request.
        self.chatengine_mod_locks: dict[str, asyncio.Lock] = {}

    @asynccontextmanager
    async def acquire_chatengine_lock(self, chatengine: ChatEngine):
        lock = self.chatengine_mod_locks.get(str(chatengine.id))
        if lock is None:
            lock = asyncio.Lock()
            self.chatengine_mod_locks[str(chatengine.id)] = lock
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()            

    async def handle_agent_meta_event(self, channel, event: dict):
        print("Agent changed event: ", event)
        
        if event['type'] == AgentLogEventTypes.AGENT_SAVED:
            with Session(self.dbengine) as session:
                agent = session.get(Agent, event['agent_id'])
                if agent is not None:
                    await self.update_agent(session, agent, event['run_id'])
        elif event['type'] == AgentLogEventTypes.RUN_UPDATED:
            # At the moment we only support updating the list of tools for the run
            with Session(self.dbengine) as session:
                run = session.get(Run, event['run_id'])
                if run is not None:
                    await self.update_run_tools(event['run_id'], run.tools)

    async def subscribe_meta_events(self):
        if not self.subscribed:
            self.subscribed = True
            await pubsub.subscribe(AGENT_EVENTS_CHANNEL, self.handle_agent_meta_event)

    def list_running_engines(self, session):
        engines = [ce.info() for ce in self.RUNNING_ENGINES.values()]

        for info in engines:
            agent = session.get(Agent, info['agent_id'])
            if agent:
                info['agent_name'] = agent.name
                info['model'] = agent.model
                info['system_prompt'] = agent.system_prompt

        return engines
    
    async def create_run(
            self, 
            session: Session, 
            agent: Agent, 
            run_db: Run, 
            user: User,
            synchronous: bool=False) -> Run:
        await self.subscribe_meta_events()
        # ! need the new run_id to create the ChatEngine (which stores it in the RunContext)
        chatengine = ChatEngine()
        await chatengine.set_agent(
            agent, 
            run_db.tenant_id, 
            run_db.user_id,
            str(run_db.id),
            run_db.scope,
            run_db.logs_channel,
            run_db.tools,
            user.email,
        )
        run_db.chatengine_id = chatengine.id
        session.add(run_db)
        session.commit()
        session.refresh(run_db)

        await pubsub.publish(
            AGENT_EVENTS_CHANNEL, 
            RunCreatedEvent(agent_id=agent.id, run_id=str(run_db.id), user_id=run_db.user_id)
        )

        self.RUNNING_ENGINES[chatengine.id] = chatengine  
        print("********** SAVED CHATENGINE UNDER ID: ", chatengine.id)
        if run_db.input is not None:
            if synchronous:
                await self.dispatch_input(run_db, chatengine, run_db.input, user)
            else:
                asyncio.create_task(self.dispatch_input(run_db, chatengine, run_db.input, user))

        return run_db

    async def continue_run(
            self, 
            session: Session, 
            rundb: Run, 
            run_input: str,
            user: User, 
            run_data: Optional[dict] = None,
            attached_file: Optional[str|None] = None,
            synchronous: bool = False,
        ):
        await self.subscribe_meta_events()

        print("Continuing Run with chatengine ID: ", rundb.chatengine_id)
            
        if rundb.chatengine_id is None or rundb.chatengine_id not in self.RUNNING_ENGINES:
            # There is no ChatEngine in memory for this run, but maybe we ran
            # the chat before. Let's load any chat history and refresh the
            # chatengine with it.
            chatengine = ChatEngine()
            agent = session.get(Agent, rundb.agent_id)
            if agent is None:
                raise HTTPException(status_code=404, detail=f"Agent {rundb.agent_id} not found")
            await chatengine.set_agent(
                agent, 
                rundb.tenant_id, 
                rundb.user_id,
                str(rundb.id),
                rundb.scope,
                rundb.logs_channel,
                rundb.tools,
            )
            logs = await chat_logger.retrieve_run_history(str(rundb.id))
            chatengine.reload_chat_history(logs)
            rundb.chatengine_id = chatengine.id
            self.RUNNING_ENGINES[chatengine.id] = chatengine
            session.add(rundb)
            session.commit()
            session.refresh(rundb)
        else:
            print("------------- ChatEngine already exists")
            chatengine: ChatEngine = self.RUNNING_ENGINES[rundb.chatengine_id]

        if attached_file:
            # Make sure the agent has a tool to read the file uploaded in the chat
            await chatengine.attach_file_reading(attached_file)

        if run_data:
            chatengine.run_context.update_env_vars(run_data)

        if synchronous:
            await self.dispatch_input(rundb, chatengine, run_input, user)
        else:
            asyncio.create_task(self.dispatch_input(rundb, chatengine, run_input, user))

    async def cancel_run(
            self,
            session: Session,
            rundb: Run,
    ):
        if rundb.chatengine_id and rundb.chatengine_id in self.RUNNING_ENGINES:
            chatengine = self.RUNNING_ENGINES[rundb.chatengine_id]
            await chatengine.cancel_agent()
       

    async def update_agent(self, session: Session, agent: Agent, run_id: str):
        # The user has modified the agent, so update the definition but only for 
        # the "current run" the user has open in the dashboard.
        for chatengine in self.RUNNING_ENGINES.values():
            if chatengine.agent_id == agent.id and chatengine.run_context.run_id == run_id:
                async with self.acquire_chatengine_lock(chatengine):
                    await chatengine.update_agent(agent)

    async def update_run_tools(self, run_id: str, run_tools: list[dict]):
        for chatengine in self.RUNNING_ENGINES.values():
            if chatengine.run_context.run_id == run_id:
                async with self.acquire_chatengine_lock(chatengine):
                    await chatengine.update_run_tools(run_tools)

    async def update_user_secrets(self, tenant_id: str, user_id: str, secrets: dict):
        # Update the user's secrets in all running chat engines
        for chatengine in self.RUNNING_ENGINES.values():
            if chatengine.tenant_id == tenant_id and chatengine.user_id == user_id:
                await chatengine.update_agent_secrets(secrets)

    async def list_dataframes(self, rundb: Run) -> list[str]:
        if rundb.chatengine_id and rundb.chatengine_id in self.RUNNING_ENGINES:
            chatengine = self.RUNNING_ENGINES[rundb.chatengine_id]
            return chatengine.tools_inmem_state.keys()
        return []
    
    async def get_dataframe(self, rundb: Run, df_name: str):
        if rundb.chatengine_id and rundb.chatengine_id in self.RUNNING_ENGINES:
            chatengine = self.RUNNING_ENGINES[rundb.chatengine_id]
            if df_name in chatengine.tools_inmem_state:
                return chatengine.tools_inmem_state[df_name]
        return None

    async def delete_dataframe(self, rundb: Run, df_name: str):
        if rundb.chatengine_id and rundb.chatengine_id in self.RUNNING_ENGINES:
            chatengine = self.RUNNING_ENGINES[rundb.chatengine_id]
            if df_name in chatengine.tools_inmem_state:
                del chatengine.tools_inmem_state[df_name]
    
    async def list_tables(self, session, rundb: Run) -> list[str]:
        return []

    async def query_table(self, session: Session, rundb: Run, table_name: str) -> pd.DataFrame:
        # FIXME
        return None

    async def delete_table(self, session: Session, rundb: Run, table_name: str) -> str:
        # FIXME
        pass

    @staticmethod
    def create_publish_function(run: Run, user_id: str, lc_run_id: Optional[str]=None):
        async def mypublish(event_class, **fields):
            # get 'role' from fields and remove it
            role = fields.pop("role", "agent")
            fields |= {"agent_id":run.agent_id, "run_id":str(run.id or ""), "user_id":user_id}
            if lc_run_id is not None:
                fields |= {"lc_run_id": str(lc_run_id)}
            event = event_class(**fields)
            run_log = RunLog.from_agent_event(event, role=role)
            run_log.scope = run.scope
            run_log.version = 3
            logger.debug(run_log, f"[{run.logs_channel}]")
            ctx = start_timeit(f"REDIS PUBLISH: {str(run_log.model_dump())[0:50]}")
            await pubsub.publish(
                run.logs_channel or "logs", 
                run_log.model_dump(),
            )
            end_timeit(ctx)
        return mypublish

    async def report_unhandled_error(self, task: AgentTask, exception):
            event = AgentErrorEvent(
                agent_id=task.run["agent_id"],
                user_id=task.user.get("user_id", ""), 
                message=str(exception)
            )
            run_log = RunLog.from_agent_event(event)
            run_log.version = 3
            logs_channel = task.run.get("logs_channel", "logs")

            logger.debug(run_log, f"[{logs_channel}]")
            await pubsub.publish(logs_channel, run_log.model_dump())

    async def dispatch_input(
            self, 
            run: Run, 
            chatengine: ChatEngine, 
            question: str,
            user: User,
        ):
        # Make sure no previous cancel flag is set
        async with self.acquire_chatengine_lock(chatengine):
            await self.dispatch_input_with_lock(run, chatengine, question, user)

    async def dispatch_input_with_lock(
            self, 
            run: Run, 
            chatengine: ChatEngine, 
            question: str,
            user: User,
        ):
        await chatengine.process_pending_agent_updates()
        
        mypublish = self.create_publish_function(run, user.user_id)

        print("###### SENDING INPUT EVENT FOR question: ", question)
        await mypublish(AgentInputEvent, prompt=question, role="user")

        # File uploads will have already been saved, so open our "file mod" window a bit for this
        start_time = datetime.now() - timedelta(seconds=30)

        async def check_run_canceled():
            if chatengine.agent_is_canceled():
                print("Run canceled!!")
                await mypublish(AgentOutputEvent, str_result="Request canceled")
                await mypublish(AgentEndEvent)
                return True

        async def log_function(batch: AgentEvent|list[AgentEvent]):
            if not isinstance(batch, list):
                batch = [batch]

            if await check_run_canceled():
                # abort our tool function
                raise RuntimeError("Function aborted by cancel request")
            
            if len(batch) > 1 and batch[0].type == AgentLogEventTypes.OUTPUT:
                batch = AgentOutputEvent.coalese_output_events(batch)

            for event in batch:
                try:
                    await self.process_agent_event(chatengine, run, event)
                    await mypublish(event.__class__, **event.model_dump())
                except TypeError as e:
                    print("SKIPPING bad event: ", e)

        print("###### Setup Agent filesystem")
        with get_agent_filesystem(run.tenant_id, run.user_id):
            output_events: list[AgentOutputEvent] = []
            batch_size = 25
            async for event in chatengine.respond(question, log_function, check_run_canceled, user):
                # Add the question and answer to the current chat.
                if await check_run_canceled():
                    break
                if event.type == AgentLogEventTypes.OUTPUT:
                    output_events.append(event)
                if event.type != AgentLogEventTypes.OUTPUT or len(output_events) > batch_size:
                    if output_events:
                        await log_function(output_events)
                        output_events = []
                    if event.type != AgentLogEventTypes.OUTPUT:
                        await log_function([event])

            if output_events:
                await log_function(batch=output_events)

        logger.debug("channel ", run.logs_channel, " **EVENT** ")
        logger.info(f"[{run.logs_channel}] -> END")

        # Send asset created events for any files created
        self.gather_file_assets(chatengine.run_context, run.tenant_id, run.user_id, start_time)
        async for asset_event in chatengine.run_context.get_queued_asset_events():
            await log_function(asset_event)

        await mypublish(AgentEndEvent)
        
        self.upload_agent_files(run.tenant_id, run.user_id, start_time)
        print("###### AGENT DONE FOR question: ", question)


    async def process_agent_event(self, chatengine: ChatEngine, run: Run, event: AgentEvent):
        # Special processing for select AgentEvents
        if isinstance(event, AddMemoryEvent):
            logger.debug("EngineMgr, AddMemory event: ", event)
            # Add the memory to the chat engine's memory
            with session_context() as session:
                agent: Agent|None = session.get(Agent, run.agent_id)
                if agent:
                    mems = agent.add_fact_as_memory(event.fact)
                    logger.debug("new memories: ", mems)                   
                    session.add(agent)
                    session.commit()
                    session.refresh(agent)
                    await chatengine.update_agent(agent)

    def get_file_asset_type(self, file):
        return AssetTypeEnum.TABLE

    def gather_file_assets(self, run_context: RunContext, tenant_id, user_id, start_time):
        # Send Asset events for any files created by the agent
        user_dir = get_user_directory(tenant_id, user_id)
        for file in list_modified_files(start_time, tenant_id, user_id):
            folder = os.path.dirname(file)
            folder = os.path.relpath(folder, user_dir)
            name = os.path.basename(file)
            full_name = os.path.join(folder, name)
            run_context.queue_asset_event(full_name, self.get_file_asset_type(file), name)

    def upload_agent_files(self, tenant_id, user_id, start_time):
        # Upload any files created by the agent to the user's directory
        user_dir = get_user_directory(tenant_id, user_id)
        for file in list_modified_files(start_time, tenant_id, user_id):
            folder = os.path.dirname(file)
            folder = os.path.relpath(folder, user_dir)
            if folder == ".":
                folder = ""
            self.upload_user_file_to_s3(tenant_id, user_id, file, folder=folder)

    def upload_user_file_to_s3(self, tenant_id, user_id, file_path, folder=""):
        bucket = config.get_global("S3_FILES_BUCKET_NAME")

        folder = f"{user_id}/{folder}"    
        if not folder.endswith("/"):
            folder = folder + "/"
        file_name = os.path.basename(file_path)
        object_name = f"{tenant_id}/{folder}{file_name}"
        print(f"Uploading {file_path} as {object_name}")
        return upload_file_to_s3(
            file_path, 
            bucket, 
            object_name,
            get_file_mimetype(file_name),
        )

    async def connect(self):
        self.redis = await pubsub.get_client()

        for tenant_id in self.tenant_id_list:
            stream_name = f'agents:{tenant_id}'
            try:
                await self.redis.xgroup_create(stream_name, self.group_name, mkstream=True)
            except redis.ResponseError:
                # Group already exists
                pass

    async def send_heartbeat(self):
        while not self.shutdown_event.is_set():
            heartbeat_key = f"heartbeat:{self.consumer_name}"
            await self.redis.setex(heartbeat_key, 10, json.dumps({
                'timestamp': time.time(),
                'streams': self.tenant_id_list
            }))
            try:
                #print("SENDING HEARTBEAT", self)
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=self.heartbeat_interval)
            except asyncio.TimeoutError:
                continue
        await self.redis.close()

    async def remove_heartbeat(self):
        heartbeat_key = f"heartbeat:{self.consumer_name}"
        await self.redis.delete(heartbeat_key)
        print(f"Removed heartbeat for {self.consumer_name}")

    async def process_tasks_until_canceled(self):
        if not self.redis:
            await self.connect()

        heartbeat_task = asyncio.create_task(self.send_heartbeat())

        try:
            while not self.shutdown_event.is_set() and (self.last_event + IDLE_TIMEOUT) > time.time():
                try:
                    streams = {f'agents:{t}': '>' for t in self.tenant_id_list}
                    messages = await asyncio.wait_for(
                        self.redis.xreadgroup(self.group_name, self.consumer_name, streams, count=1),
                        timeout=1.0
                    )
                    
                    for stream, tasks in messages:
                        for task_id, task in tasks:
                            task_data = json.loads(task["task"])
                            self.last_event = time.time()
                            await self._process_task(task_data)
                            self.last_event = time.time()
                            await self.redis.xack(stream, self.group_name, task_id)
                
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"Error processing task: {e}")
                    await asyncio.sleep(0.2)
            print("AGENT IDLE, SHUTTING DOWN")
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            await self.remove_heartbeat()

    async def _process_task(self, task_data, synchronous=True):
        try:
            task = AgentTask.model_validate(task_data)
            print("Async task: ", task.action) 
            self.last_event = time.time()
            with Session(self.dbengine) as session:
                try:
                    if task.action == AgentTask.ACTION_CREATE_RUN:
                        run_db = session.get(Run, task.run["id"])
                        agent = session.get(Agent, run_db.agent_id)
                        if agent is not None:
                            await self.create_run(
                                session, 
                                agent, 
                                run_db, 
                                task.get_user(), 
                                synchronous=synchronous
                            )
                    elif task.action == AgentTask.ACTION_PROMPT:
                        run_db = session.get(Run, task.run["id"])
                        # We run agent tasks synchronously
                        await self.continue_run(
                            session, 
                            run_db, 
                            task.run_input["input"], 
                            task.get_user(),
                            task.run_input.get("run_data", {}),
                            synchronous=synchronous,
                        )
                    else:
                        raise RuntimeError(f"Unknown task action: {task.action} and task: {task}")
                except Exception as e:
                    error_id = uuid.uuid4().hex
                    rollbar.report_exc_info(extra_data={"user": task.user, "error_id": error_id})
                    logger.error(f"Cannot run agent: {e}. Error number: {error_id}", traceback.format_exc())
                    raise HTTPException(status_code=500, detail=f"Cannot run agent. Error number: {error_id}")

        except Exception as e:
            traceback.print_exc()
            await self.report_unhandled_error(task, e)

        await asyncio.sleep(1)

    def shutdown(self):
        print("Shutting down...")
        self.shutdown_event.set()

    async def task_loop(self):
        # Set up signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda s, f: signal_handler(self))
        
        print(f"Starting task consumer for streams: {', '.join(self.tenant_id_list)}...")
        chat_logger.reconnect()
        async for i in db_lifespan(None):
            await self.process_tasks_until_canceled()

    @staticmethod
    def reset_db_connections():
        # This is meant to be called by AgentDispatcher after it works a new worker, so that it can reconnect
        # it's db connections which will be shared/closed by the new worker. This code is only here as a pair
        # 'task_loop' above which is called when the forked worker starts.
        chat_logger.reconnect()
        reset_db_connections()


def signal_handler(consumer):
    print("Received exit signal. Initiating shutdown...")
    consumer.shutdown()
    sys.exit(0)

if __name__ == "__main__":
    # Run the engine manager
    tenant_id_list = ["test"]
    manager = EngineManager(tenant_id_list)
    asyncio.run(manager.task_loop())
