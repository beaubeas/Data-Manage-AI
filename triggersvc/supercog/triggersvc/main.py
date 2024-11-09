
import time
import json
import base64
from threading import Thread
from fastapi import FastAPI, Depends, HTTPException, Path, status
from supercog.shared.services import config, serve, db_connect
from supercog.shared.models import RunCreate, AgentBase
from supercog.shared.pubsub import pubsub
from supercog.shared.credentials import creds_service

from .db import lifespan, get_session, Trigger
import supercog.triggersvc.db as db

TRIGGER_FORMAT = """
Email from: {from}
Subject: {subject}
###
{body}
###
"""

TRIGGER_EXAMPLE = """
Email from: scott@example.com
Subject: The flux capacitor is on the fritz
###
Marty - no matter how many times I have tried the "impact adjustment"
with the flux capacity, the Delorean won't start. Have fun stuck in 
the future.
--Doc
###
"""

app = FastAPI(lifespan=lifespan)

@app.get("/hello")
def hello():
    return {"message": "Hello from triggersvc"}


if __name__ == "__main__":
    serve(app, "triggersvc")

