import redis.asyncio as redis
from typing import AsyncIterator, Optional, Sequence
import json
import os

from sqlmodel import Session, select

from fastapi import FastAPI
from fastapi_lifespan_manager import LifespanManager, State

from supercog.shared.pubsub import REDIS_HOST, REDIS_PORT
from supercog.shared.apubsub import pubsub
from supercog.shared.models import RunLogBase
from supercog.shared.services import db_connect
from supercog.shared.apubsub import AgentLogEventTypes, EventRegistry, TokenUsageEvent

from .db import lifespan_manager, RunLog, Run


MYDEBUG = os.environ.get('CHAT_LOG_DEBUG')

class ChatLogger:
    def __init__(self):
        self.client = None
        self.next_logs: dict[str, RunLog] = {}
        self.engine = db_connect("engine") 

    def reconnect(self):
        self.engine.dispose()
        self.engine = db_connect("engine")

    async def save_event(self, event, session: Session):
        # Always saves a new run_log record
        log = RunLog.model_validate(event)
        session.add(log)
        session.commit()

    async def update_token_usage(self, event, session: Session):
        if 'run_id' not in event:
            return
        # Might be worth just doing this as an update query
        run = session.get(Run, event['run_id'])
        runlog = RunLogBase.model_validate(event)
        agevent = EventRegistry.get_event(runlog)
        if run and isinstance(agevent, TokenUsageEvent):
            run.input_tokens += int(agevent.usage_metadata.get("input_tokens", 0))
            run.output_tokens += int(agevent.usage_metadata.get("output_tokens", 0))
            session.add(run)
            session.commit()

    async def start(self):
        print(f"########## STARTING CHAT LOGGER ############ {id(self)}")
        await pubsub.subscribe("logs*", self.receive_message)

    async def receive_message(self, event_type: str, event: dict):
        if MYDEBUG:
            print(f"[CHAT LOGGER EVENT {id(self)}] ", event)
        with Session(self.engine) as session:
            await self.save_event(event, session)
            if event_type == AgentLogEventTypes.TOKEN_USAGE:
                await self.update_token_usage(event, session)

    async def retrieve_run_history(self, run_id: str) -> Sequence[RunLog]:
        with Session(self.engine) as session:
            query = select(RunLog).where(
                RunLog.run_id == run_id
            ).order_by(
                RunLog.created_at.asc()
            )
            return session.exec(query).all()

    @staticmethod
    def generate_output(run: Run, message: str) -> RunLogBase:
        return RunLogBase(
            run_id=str(run.id or ""),
            agent_id=run.agent_id,
            user_id=run.user_id,
            scope="private",
            lc_run_id=None,
            content=message,
            type=AgentLogEventTypes.OUTPUT,
        )

    # FIXME: We should move this method into RunContext so other people don't have to import ChatLogger
    @staticmethod
    def generate_run_log(
        run_id: str|None, 
        agent_id: str, 
        user_id: str, 
        lc_event: dict,
        scope="private"
        ) -> RunLogBase:
        return RunLogBase(
                run_id=str(run_id or ""),
                agent_id=agent_id,
                user_id=user_id,
                scope=scope,
                lc_run_id=str(lc_event.get('run_id', f"{lc_event['type']} MISSING RUN ID")),
                content=str(lc_event.get('content', '')),
                type=lc_event['type'],
            )
       
chat_logger = ChatLogger()

def activate_chatlogger():
    @lifespan_manager.add
    async def startup(app: FastAPI) -> AsyncIterator[State]:
        await chat_logger.start()
        yield {"chat_logger": chat_logger}
    

