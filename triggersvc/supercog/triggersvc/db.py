from fastapi import FastAPI
from sqlalchemy import Engine
from sqlmodel import SQLModel, Session, Field
from uuid import UUID, uuid4
from typing import Optional
from datetime import datetime

from supercog.shared.services import config, db_connect
from supercog.shared.models import RunCreate

SERVICE_NAME = "triggersvc"
engine: Engine =  None

# PUT YOUR MODELS HERE

# Remove this. Add a real mode into ahsared/monster/shared/models.py
TriggerModelFromSharedWhichActsAsEventContract = SQLModel

class Trigger(TriggerModelFromSharedWhichActsAsEventContract, table=True):
    id: Optional[UUID] = Field(default_factory=uuid4, primary_key=True)

from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine #critical!
    engine = db_connect(SERVICE_NAME)
    yield   

def get_session():
    with Session(engine) as session:
        yield session
