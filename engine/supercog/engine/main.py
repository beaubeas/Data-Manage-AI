# The FastAPI app for the Agents service. Implements all the API endpoints.
# Calls for agent execution go through the EngineManager class, which in
# turn creates ChatEngine instances to run the agents.
#
# main.py - FastAPI endpoints
# db.py - defines our persisten models
# EngineManager - manges all the running agent instances
# ChatEngine - implements a single agent instance
# ChatLogger - records published agent events to the RunLogs table
#
# everything else is tools

import base64
from datetime import datetime, timezone, timedelta
import logging
import asyncio
import aiofiles
import json
import io
import os
import platform
import signal
import inspect
from typing import Callable, Dict, Any, Optional
from pprint import pprint
import traceback
from fastapi import FastAPI, Depends, HTTPException, Path, status, Request, UploadFile, File, BackgroundTasks
from flask import redirect
from pydantic import BaseModel
from typing import List, Optional
from sqlmodel import SQLModel, Field, Session, create_engine, select, or_
from uuid import UUID, uuid4
from sqlalchemy.sql import func
from datetime import datetime
import mimetypes
from sqlalchemy import text

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse, Response
import pandas as pd

# Allow us to mount a Flask app for FlaskDance oauth
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.middleware.cors import CORSMiddleware
import rollbar
from rollbar.contrib.fastapi import add_to as rollbar_add_to

from supercog.shared.services import config, serve, db_connect
from supercog.shared.models import (
    RunCreate, 
    RunUpdate,
    RunLogBase, 
    AgentBase, 
    CredentialBase, 
    Datum, 
    DocIndexBase,
    DocSourceConfigCreate,
    PERSONAL_INDEX_NAME,
)

from supercog.shared.apubsub import pubsub, AGENT_EVENTS_CHANNEL, AgentSavedEvent, RunUpdatedEvent
from supercog.shared.credentials import secrets_service
from supercog.shared.utils import (
    get_boto_client, 
    upload_file_to_s3, 
    calc_s3_url, 
    create_presigned_url,
    wait_for_deletion,
    download_s3_file,
)

from supercog.shared.logging import logger

from .oauth_flask import oauth_app
import supercog.engine.oauth_flask
from .file_utils import read_pdf, read_eml, is_audio_file

from .db import get_session, get_noexpiry_session, Agent, Run, RunLog, lifespan_manager, DocSourceConfig
import supercog.engine.db as db
from .enginemgr import EngineManager
from .jwt_auth import requires_jwt, requires_jwt_or_triggersvc, User
from .agent_dispatcher import AgentDispatcherClass, AgentTask
from .run_context import RunContext
from .rag_utils import get_user_personal_index, get_ragie_partition

# This import is really slow. Probably langchain?
from .all_tools import ToolFactory, TOOL_FACTORIES, FACTORY_MAP
from .doc_source_factory import DocSourceFactory
from .filesystem import (
    get_user_directory,
    delete_user_file,
    get_agent_filesystem,
)
from .tool_factory import TOOL_REGISTRY

from supercog.engine.tools.website_docs import WebsiteDocSource
from supercog.engine.tools.google_drive import GoogleDriveDocSource
from supercog.engine.doc_source_factory import DocSourceFactory

# Need this import to register chat_logger with the FastAPI app
from .chat_logger import activate_chatlogger
activate_chatlogger()

from .agent_learning import AgentLearning

# RAGIE
from ragie import Ragie

ragie = Ragie(
    auth=config.get_global('RAGIE_API_KEY', required=False) or "",
)



AVAIL_MODELS = [
    "o1-preview",
    "o1-mini",
    "gpt-4o-mini",
    'gpt-4o',
    'gpt-4o-2024-05-13',
    "gpt-4-turbo",
    "gpt-4-32k",
    "gpt-4",
    "gpt-4-vision-preview",
    "gpt-4-1106-preview",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k",
#    "mistral:latest",
    "claude-3-5-sonnet-20240620",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "llama-3.1-405b-reasoning",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-8b-8192",
    "llama3-groq-70b-8192-tool-use-preview",
    "default:gpt-4o-mini",
]

class ReflectionResponse(BaseModel):
    facts:       List[str]
    analysis:    str
    token_usage: dict
    
class RunInput(BaseModel):
    input: str
    run_data: Optional[Dict[str, Any]] = None

app = FastAPI(lifespan=lifespan_manager)
rb_token = os.environ.get("ROLLBAR_TOKEN")
if rb_token:
    rb_env = os.environ.get("ENV", "dev")
    print("CONNECTING TO ROLLBAR: ", rb_token[0:5], rb_env)
    rollbar.init(rb_token, environment=rb_env)
    rollbar_add_to(app)
else:
    print("!! WARNING, No ROLLBAR_TOKEN set")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://app.supercog.ai",
        "https://app.supercog.ai",
        "app.supercog.ai",
        "https://engine.supercog.ai",
        "engine.supercog.ai",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SERVICE = "engine"
enginemgr = EngineManager([])
dispatcher = AgentDispatcherClass(enginemgr)

@lifespan_manager.add
async def get_dispatcher(app: FastAPI):
    await dispatcher.connect()
    yield


agent_learning = AgentLearning()
STARTUP_TIME = datetime.now(timezone.utc).isoformat()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/admin/runs")
async def admin_list_runs(
    *, 
    session: Session = Depends(get_session), 
    user: User = Depends(requires_jwt)
    ):
    # query runs, but join to agents table to get the agent name
    # select on the run.id, run.user_id and agent.name
    sql = "select run.*, agents.name as name from run join agents on run.agent_id = agents.id"
    sql += " ORDER BY run.created_at DESC LIMIT 10"
    result = session.execute(text(sql)).fetchall()
    run_res = [row._mapping for row in result]
    print(run_res)
    agents = enginemgr.list_running_engines(session) # bad param

    sha = "?"
    if os.path.exists("/code/GIT_SHA"):
        try:
            sha = open("/code/GIT_SHA").read().strip()
        except:
            sha = "failed to get"
    address = os.getenv("FLY_PRIVATE_IP", "")
    if sha:
        sha = f"{sha[0:7]} - {sha[-7:]}"
    else:
        sha = "<not set>"

    return {
        "agents": agents, 
        "runs": run_res, 
        "info": {
            "git_sha": sha, 
            "start_time": STARTUP_TIME, 
            "address":address
        }
    }

@app.get("/tenant/{tenant_id}/tool_factories", response_model=List[ToolFactory])
async def get_tools(*, tenant_id: str, user: User = Depends(requires_jwt)):
    # Load the dynamic tools. They will get put into TOOL_FACTORIES for return
    TOOL_REGISTRY.load_registry_from_filesystem(tenant_id)
    return TOOL_FACTORIES

@app.get("/models", response_model=List[str])
async def get_models():
    # Example list of models, replace with actual logic to fetch models
    return AVAIL_MODELS

@app.post("/agents", response_model=AgentBase)
async def save_agent(*, 
                     session: Session = Depends(get_session), 
                     user: User = Depends(requires_jwt_or_triggersvc),
                     run_id: Optional[str] = None,
                     agent_base: AgentBase):
    # We allow both creating and updating agents via the same endpoint here,
    # for simplicity, rather than using a separate PATCH endpoint.
    # The logic is that the Dashboard will POST a copy of the agent too us
    # whenver it is changed on the FE by the user. Later the Dashboard (or
    # a trigger) can post to RUNS to actually run the agent.
    vals = agent_base.model_dump()
    print(vals)
    agent_db = db.Agent.model_validate(vals)
    logger.info("Received POST agent: ", agent_db)
    existing = session.get(db.Agent, agent_db.id)
    if existing:
        for key, value in agent_db.model_dump().items():
            setattr(existing, key, value)
        agent_db = existing
    session.add(agent_db)
    session.commit()
    session.refresh(agent_db)
    await pubsub.publish(
        AGENT_EVENTS_CHANNEL, 
        AgentSavedEvent(agent_id=agent_db.id, user_id=agent_db.user_id, run_id=run_id),
    )
    return agent_db


# A "Run"'s lifecycle is an active session with a given user, which could
# include multiple turns of interaction. You MUST call POST /agents first
# to send the definition for the agent before you run it.
@app.post("/runs", response_model=Run)
async def create_run(*, 
                session: Session = Depends(get_session), 
                user: User = Depends(requires_jwt_or_triggersvc),
                run: RunCreate,
                request: Request):
    
    # First check if there is an existing run based on the conversation_id
    if run.conversation_id:
        existing_run = session.exec(
            select(Run).where(Run.conversation_id == run.conversation_id)
        ).one_or_none()

        if existing_run:
            return existing_run

    run_db = Run.model_validate(run)

    agent = session.get(db.Agent, run_db.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {run_db.agent_id} not found")

    run_db.model = agent.model
    run_db.tools = [t.model_dump() for t in agent.tool_list]

    session.add(run_db)
    session.commit()
    session.refresh(run_db)

    job = AgentTask(
        action=AgentTask.ACTION_CREATE_RUN,
        user =dict(user),
        run = run_db.model_dump(),
        headers = dict(request.headers),
        query_params=dict(request.query_params),
    )
    await dispatcher.enqueue_task(run_db.tenant_id, job)

    return run_db


@app.post("/runs/{run_id}/input")
async def run_input(*, 
                    session: Session = Depends(get_noexpiry_session), 
                    user: User = Depends(requires_jwt_or_triggersvc),
                    run_id: UUID, 
                    attached_file: Optional[str|None] = None,
                    run_input: RunInput,
                    request: Request):
    run_db = session.get(Run, run_id)
    if run_db is None:
        raise HTTPException(status_code=404, detail="Run not found")

    job = AgentTask(
        action=AgentTask.ACTION_PROMPT,
        user =dict(user),
        run = run_db.model_dump(),
        run_input = run_input.model_dump(),
        headers = dict(request.headers),
        query_params=dict(request.query_params),
    )
    await dispatcher.enqueue_task(run_db.tenant_id, job)

    return {"status": "success", "message": "Input dispatched"}


@app.get("/tenant/{tenant_id}/runs", response_model=List[Run])
async def list_runs(*, 
                    session: Session = Depends(get_session), 
                    user: User = Depends(requires_jwt),
                    tenant_id: str):
    today_date = datetime.now().date()

    query = select(Run).where(
        Run.tenant_id == tenant_id,
        func.date(Run.created_at) == today_date
    )
    return session.exec(query).all()

@app.get("/tenant/{tenant_id}/agents/{agent_id}/runs", response_model=List[Run])
async def list_agent_runs(*, 
        session: Session = Depends(get_session), 
        user: User = Depends(requires_jwt),
        tenant_id: str,
        agent_id: str,
        user_id: str):

    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    query = select(Run).where(
        Run.tenant_id == tenant_id,
        Run.agent_id == agent_id,
        or_(Run.scope == "shared", Run.user_id == user_id)
    ).limit(100).order_by(Run.created_at.desc())
    return session.exec(query).all()

# Agent usage stats
@app.get("/tenant/{tenant_id}/daily_stats")
async def get_daily_stats(*, 
        session: Session = Depends(get_session), 
        user: User = Depends(requires_jwt),
        tenant_id: str,
        user_id: str):
    # Returns rolled up usage, by agent, for last 24 hours
    now = datetime.utcnow()

    # Calculate the time 24 hours ago
    twenty_four_hours_ago = now - timedelta(hours=24)

    # Create the query
    agent_query = (
        select(
            Run.agent_id,
            Agent.name.label("agent_name"),
            func.sum(Run.input_tokens).label("input_tokens"),
            func.sum(Run.output_tokens).label("output_tokens")
        )
        .join(Agent, Run.agent_id == Agent.id)
        .where(
            Run.last_interaction >= twenty_four_hours_ago,
            Run.tenant_id == tenant_id,
            Run.user_id == user_id,
        ).group_by(
            Run.agent_id, Agent.name
        )
    )
    result1 = [row._asdict() for row in session.exec(agent_query).all()]

    model_query = select(
        Run.model,
        func.sum(Run.input_tokens).label("input_tokens"),
        func.sum(Run.output_tokens).label("output_tokens")
    ).where(
        Run.last_interaction >= twenty_four_hours_ago,
        Run.tenant_id == tenant_id,
        Run.user_id == user_id,
    ).group_by(
        Run.model
    )
    result2 = [row._asdict() for row in session.exec(model_query).all()]
    print(result2)
    return {"agents": result1, "models": result2}

@app.get("/tenant/{tenant_id}/agents/{agent_id}/run/{run_id}/datums", response_model=List[Datum])
async def get_datums(*, 
        session: Session = Depends(get_session), 
        user: User = Depends(requires_jwt),
        tenant_id: str,
        agent_id: str,
        run_id: str,
        user_id: str,
        directory: str = None):  # Optional directory parameter

    include_nonfiles = directory is None
    if user_id != user.user_id:
        raise HTTPException(status_code=403, detail="Unknown user")
    
    user_dir = get_user_directory(tenant_id, user_id)

    if directory is None:
        directory = '.'  # Default to the root of the tenant/user-specific directory
    # Normalize the path whether it's provided or default to '.'
    base_path = os.path.join(user_dir, os.path.normpath(directory))

    # Prevent directory traversal
    if '..' in base_path.split(os.path.sep):
        raise HTTPException(status_code=400, detail="Invalid directory path")

    if not os.path.exists(base_path):
        raise HTTPException(status_code=404, detail="Directory not found")

    print("Base Path:", base_path)  # Debugging output
    files = os.listdir(base_path)
    datums = []
    for f in files:
        full_path = os.path.join(base_path, f)
        print("Checking:", full_path, "Is File:", os.path.isfile(full_path), "Is Dir:", os.path.isdir(full_path))  # More Debugging
        is_dir = os.path.isdir(full_path)
        is_file = os.path.isfile(full_path)

        # Use ternary expression to maintain concise structure
        mime_type = "text/plain" if is_file else "inode/directory"
        
        # Determine MIME type for files based on file extension
        if is_file:
            mime_type, _ = mimetypes.guess_type(full_path)
            if mime_type is None:
                mime_type = "text/plain"  # Fallback for unknown types

        datum = Datum(
                category="files",
                name=f,
                mime_type=mime_type,
                is_directory=is_dir
            )
        datums.append(datum)

    if run_id != "0" and include_nonfiles:
        rundb = session.exec(
            select(Run).where(
                Run.tenant_id == tenant_id,
                Run.agent_id == agent_id,
                Run.user_id == user_id,
                Run.id == run_id,
            )
        ).first()
        if rundb is None:
            raise HTTPException(status_code=404, detail="Run not found")

        # See if we have any dataframes
        dataframes = await enginemgr.list_dataframes(rundb)
        datums.extend([
            Datum(
                category="dataframes",
                name=df,
                mime_type="table",
            ) for df in dataframes
        ])

        # Find Duckdb tables
        try:
            tables = await enginemgr.list_tables(session, rundb)
            datums.extend([
                Datum(
                    category="tables",
                    name=table,
                    mime_type="table",
                ) for table in tables
            ])
        except Exception as e:
            traceback.print_exc()            

    return datums

def get_directory_contents(file_path: str) -> dict:
    """Get the contents of a directory."""
    def get_file_details(file_path):
        stats = os.stat(file_path)
        
        # Use st_mtime for last modified time
        modified_time = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        # Use st_birthtime for creation time on macOS
        if platform.system() == 'Darwin':  # 'Darwin' is the system name for macOS
            created_time = datetime.fromtimestamp(stats.st_birthtime).strftime("%Y-%m-%d %H:%M:%S")
        elif platform.system() == 'Windows':
            created_time = datetime.fromtimestamp(stats.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_time = "Not available on this OS"
        return {
            "name": os.path.basename(file_path),
            "size": stats.st_size,
            "created": created_time,
            "modified": modified_time,
            "is_dir": os.path.isdir(file_path)
        }

    directory_contents = os.listdir(file_path)
    details = [get_file_details(os.path.join(file_path, item)) for item in directory_contents]
    details.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

    content = "Directory contents:\n\n"
    content += "| Name | Type | Size | Created | Modified |\n"
    content += "|------|------|------|---------|----------|\n"
    for item in details:
        item_type = "Directory" if item["is_dir"] else "File"
        size = "N/A" if item["is_dir"] else f"{item['size']:,} bytes"
        content += f"| {item['name']} | {item_type} | {size} | {item['created']} | {item['modified']} |\n"

    return {"type": "directory", "content": content}

from datetime import datetime as dt
from botocore.exceptions import ClientError


def get_media_file_info(tenant_id: str,
                        user_id: str,
                        file_path: str,
                        file_name: str,
                        file_type: str,
                        drive: str = 'default') -> dict:
    """Get file information from S3 or local storage."""
    logger.debug(f"*****Getting file info for {file_name}")
    folder = os.path.dirname(file_name)
    filename = os.path.basename(file_name)
    folder = f"{user_id}:{folder}"

    s3 = get_boto_client('s3')
    bucket_name = config.get_global("S3_FILES_BUCKET_NAME") or ""

    user_id, folder = folder.split(":")
    if folder:
        s3_folder = f"{user_id}/{folder}"
    else:
        s3_folder = user_id
    object_name = f"{tenant_id}/{s3_folder}/{filename}"

    try:
        # Attempt to get S3 file info
        logger.debug(f"Attempting to get S3 file info for:\nBucket: {bucket_name}\nObject: {object_name}")
        s3_info = s3.head_object(Bucket=bucket_name, Key=object_name)
        logger.debug(f"\nS3 file info retrieved successfully\n\n{s3_info}\n\n")
        
        # Generate presigned URL
        presigned_url = create_presigned_url(s3, bucket_name, object_name)
        
        return {
            "s3_url":        presigned_url.get("url"),
            "size":          s3_info['ContentLength'],
            "created":       None,
            "modified":      s3_info['LastModified'].isoformat(),
            "mime_type":     s3_info.get('ContentType', 'application/octet-stream'),
        }
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.debug(f"File not found in S3, checking local storage")
            # If S3 fails, get local file info
            if os.path.exists(file_path):
                stats = os.stat(file_path)
                mime_type, _ = mimetypes.guess_type(file_path)
                logger.debug(f"Local file info retrieved successfully")

                # If it's a video file, upload it to S3
                if file_type == 'video':
                    logger.debug(f"Uploading video file to S3: {file_path}")
                    s3_url = upload_file_to_s3(file_path, bucket_name, object_name, mime_type)
                    # Generate presigned URL for the newly uploaded file
                    presigned_url = create_presigned_url(s3, bucket_name, object_name)
                    return {
                        "s3_url": presigned_url.get("url"),
                        "size": stats.st_size,
                        "created": dt.fromtimestamp(stats.st_ctime).isoformat(),
                        "modified": dt.fromtimestamp(stats.st_mtime).isoformat(),
                        "mime_type": mime_type or 'application/octet-stream',
                    }
                else:
                    return {
                        "s3_url": "",
                        "size": stats.st_size,
                        "created": dt.fromtimestamp(stats.st_ctime).isoformat(),
                        "modified": dt.fromtimestamp(stats.st_mtime).isoformat(),
                        "mime_type": mime_type or 'application/octet-stream',
                    }
            else:
                logger.error(f"File not found: {file_path}")
                raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
        else:
            # If there's a different S3 error, re-raise it
            logger.error(f"S3 error: {str(e)}")
            raise

def get_file_info_supercogFS(file_path: str) -> dict:
    """Get file information from the local filesystem."""
    try:
        stats = os.stat(file_path)
        # Use st_mtime for last modified time
        modified_time = datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        # Use st_birthtime for creation time on macOS
        if platform.system() == 'Darwin':  # 'Darwin' is the system name for macOS
            created_time = datetime.fromtimestamp(stats.st_birthtime).strftime("%Y-%m-%d %H:%M:%S")
        elif platform.system() == 'Windows':
            created_time = datetime.fromtimestamp(stats.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_time = "Not available on this OS"
        return {
            "type": "file",  # This might need to be adjusted based on your needs
            "mime_type": mimetypes.guess_type(file_path)[0] or "application/octet-stream",
            "s3_url": "",  # Empty string as it's not an S3 file
            "file_path": file_path,
            "raw_data": "",  # Empty string as we're not reading file content here
            "created": created_time,
            "modified": modified_time,
            "size": f"{stats.st_size / 1024:.2f} KB"
        }
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {str(e)}")
        return {
            "type": "file",
            "mime_type": "N/A",
            "s3_url": "",
            "file_path": file_path,
            "raw_data": "",
            "created": "N/A",
            "modified": "N/A",
            "size": "N/A"
        }
        
def handle_pdf_file(file_path: str) -> dict:
    """Handle PDF file and return its content."""
    try:
        pdf_text = read_pdf(file_path)
        return {"type": "pdf", "content": pdf_text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading PDF: {str(e)}")

def handle_email_file(file_path: str) -> dict:
    """Handle email file and return its content."""
    try:
        email_data = read_eml(file_path, "", None)  # Adjust parameters as needed
        return {"type": "email", "content": email_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading email: {str(e)}")

def handle_media_file(tenant_id: str, user_id: str, file_path: str, file_name: str) -> dict:
    """Handle media (audio, video, image) file and return its content."""
    try:
        logger.info(f"Handling media file: {file_name}")
        mime_type, _ = mimetypes.guess_type(file_path)
        logger.debug(f"MIME type: {mime_type}")

        media_type = "unknown"
        if mime_type:
            if mime_type.startswith('audio'):
                media_type = "audio"
            elif mime_type.startswith('video'):
                media_type = "video"
            elif mime_type.startswith('image'):
                media_type = "image"
        logger.debug(f"Determined media type: {media_type}")

        file_info =  get_media_file_info(tenant_id,
                                         user_id,
                                         file_path,
                                         file_name,
                                         media_type)
        logger.debug(f"File info: {file_info}")

        raw_data = None
        if not file_info.get('s3_url') and media_type != 'video':
            with open(file_path, 'rb') as media_file:
                raw_data = base64.b64encode(media_file.read()).decode('utf-8')
                logger.debug(f"Read {len(raw_data)} bytes from file")

        result = {
            "type":       media_type,
            "mime_type":  mime_type,
            "s3_url":     file_info.get('s3_url', ''),
            "file_path":  file_path,
            "raw_data":   raw_data,
            "created":    file_info.get('created', 'N/A'),
            "modified":   file_info.get('modified', 'N/A'),
            "size":       f"{file_info.get('size', 0) / 1024:.2f} KB"
        }
        logger.debug("Successfully prepared result dictionary")
        return result
    except HTTPException as he:
        logger.error(f"HTTP exception in handle_media_file: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Error in handle_media_file: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing media file: {str(e)}")

def detect_language(mime_type: str) -> str:
    mime_language_map = {
        "text/x-rustsrc": "rust",
        "text/x-python": "python",
        "text/x-cobol": "cobol",
        "text/x-java-source": "java",
        "application/x-apex": "java",
        "application/sql": "sql",
        "application/javascript": "javascript",
        "text/html": "html",
        "text/css": "css",
        "application/json": "json",
        "text/x-c": "c",
        "text/x-c++": "cpp",
        "text/x-go": "go",
        "text/x-php": "php",
        "text/x-shellscript": "bash",
        "text/x-markdown": "markdown",
        "text/plain": "plaintext",
        "text/x-perl": "perl",
        "text/x-ruby": "ruby",
        "application/x-powershell": "powershell",
        "text/x-scala": "scala",
        "text/x-swift": "swift",
        "application/xml": "xml",
        "text/x-yaml": "yaml",
        "text/x-tcl": "tcl",
        "text/x-vbscript": "vbscript",
        "text/x-haskell": "haskell",
        "text/x-lisp": "lisp",
        "text/x-erlang": "erlang",
        "text/x-kotlin": "kotlin",
        "text/x-scheme": "scheme",
        "text/x-julia": "julia",
        "application/x-sqlite3": "sqlite",
        "application/x-sh": "bash",  # Commonly used for shell scripts
        "application/x-zsh": "zsh",
        "application/x-batch": "batch",  # Batch files
        "text/x-jcl": "jcl",  # Job Control Language (JCL)
        "text/x-fortran": "fortran",
        "text/x-pascal": "pascal",
        "application/x-vbscript": "vbscript",
        "application/x-latex": "latex",
        "application/x-matlab": "matlab",
        "text/x-r": "r",
        "application/x-sas": "sas",
        "text/x-asm": "assembly",  # Assembly language support

        # Add more legacy or specific languages as needed
    }

    return mime_language_map.get(mime_type, "")  # Default to empty if not found

def get_mime_type(file_path: str) -> str:
    """
    Returns the MIME type of the file based on the file extension.
    If there is no extension, returns 'application/text'.
    If there is an extension but it cannot be determined, returns None.
    
    Keyword arguments:
    file_path -- full file path
    
    Returns:
    A string representing the MIME type of the file or None if it cannot be determined.
    """
    # Check if the file has an extension
    _, ext = os.path.splitext(file_path)

    # If there is no extension, return 'text/plain'
    if not ext:
        return 'text/plain'
    
    # Guess the MIME type based on the file extension
    mime_type, _ = mimetypes.guess_type(file_path, False)
    
    # Return the guessed MIME type (or None if it couldn't be determined)
    return mime_type

'''
# Standard MIME types mapping (file extensions to MIME types)
standard_mime_types = mimetypes.types_map

# Non-standard/common MIME types mapping
common_mime_types = mimetypes.common_types

# View all supported standard MIME types
print(standard_mime_types)
# View all supported non-standard (common) MIME types
  print(common_mime_types)
'''
mimetypes.add_type('text/x-cobol', '.cbl')
mimetypes.add_type('text/x-asm', '.asm')
mimetypes.add_type('text/x-jcl', '.jcl')
mimetypes.add_type('text/x-rustsrc', '.rs')
mimetypes.add_type('application/x-parquet', '.parquet')
mimetypes.add_type('application/sql', '.sql')
mimetypes.add_type('text/markdown', '.md')

def is_supported_text_mime_type(mime_type: str) -> bool:
    print(f"------------------> looking up type {mime_type} <--------------")
    
    supported_mime_types = [
        "text/plain", "application/javascript", "application/json", 
        "text/html", "text/css", "application/xml", "text/x-markdown",
        "text/x-rustsrc", "text/x-python", "text/x-cobol", "text/x-java-source",
        "application/sql", "text/x-c", "text/x-c++", "text/x-go", "text/x-php", 
        "text/x-shellscript", "text/x-perl", "text/x-ruby", "application/x-powershell", 
        "text/x-scala", "text/x-swift", "text/x-yaml", "text/x-tcl", "text/x-vbscript", 
        "text/x-haskell", "text/x-lisp", "text/x-erlang", "text/x-kotlin", 
        "text/x-scheme", "text/x-julia", "application/x-sqlite3", "application/x-sh", 
        "application/x-zsh", "application/x-batch", "text/x-jcl", "text/x-fortran", 
        "text/x-pascal", "application/x-latex", "application/x-matlab", "text/x-r",
        "application/x-sas", "text/x-asm",
        "text/markdown", 
    ]
    '''
    def list_supported_extensions() -> dict:
        # Returns a dictionary where keys are MIME types and values are file extensions
        supported_extensions = {}

        # Iterate over all registered MIME types and their extensions
        for ext, mime in mimetypes.types_map.items():
            if mime not in supported_extensions:
                supported_extensions[mime] = ext
        return supported_extensions

    # Print all supported MIME types and their extensions
    debug_mime_types = list_supported_extensions()
    for debug_mime_type, ext in debug_mime_types.items():
        print(f"MIME type: {debug_mime_type}, Extension: {ext}")
    '''
    # Correctly return whether the mime_type passed as a parameter is supported
    return mime_type in supported_mime_types

def handle_other_files(file_path: str, raw_data: str, file_type: str) -> dict:
    """Handle non-media files and return their content in a consistent format."""
    try:
        logger.info(f"Handling non-media file: {file_path} with type: {file_type}")
        file_info = get_file_info_supercogFS(file_path)
        logger.debug(f"File info: {file_info}")
        
        mime_type, _ = mimetypes.guess_type(file_path, False)
        logger.debug(f"MIME type: {mime_type}")

        # Handle the case where size might already be a formatted string
        size = file_info.get('size', 'N/A')
        if isinstance(size, (int, float)):
            size = f"{size / 1024:.2f} KB"
        elif not isinstance(size, str):
            size = 'N/A'

        result = {
            "type": file_type,
            "mime_type": mime_type or "application/octet-stream",
            "s3_url": "",
            "file_path": file_path,
            "raw_data": raw_data,
            "created": file_info.get('created', 'N/A'),
            "modified": file_info.get('modified', 'N/A'),
            "size": size
        }
        logger.debug(f"Successfully prepared result dictionary for {file_type} result: {result} ")
        return result
    except Exception as e:
        logger.error(f"Error in handle_other_files: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing {file_type} file: {str(e)}")




@app.get("/tenant/{tenant_id}/agents/{agent_id}/run/{run_id}/getdatum")
async def get_single_datum(*, 
        session: Session = Depends(get_session), 
        user: User = Depends(requires_jwt),
        tenant_id: str,
        agent_id: str,
        run_id: str,
        user_id: str,
        category: str,
        name: str):
    logger.info(f"get_single_datum called with tenant_id={tenant_id}, \
                agent_id={agent_id}, run_id={run_id}, user_id={user_id}, \
                category={category}, name={name}")
    try:
        if run_id != "0" and agent_id != "0":
            logger.debug("Querying for run in database")
            rundb = session.exec(
                select(Run).where(
                    Run.tenant_id == tenant_id,
                    Run.agent_id == agent_id,
                    Run.user_id == user_id,
                    Run.id == run_id,
                )
            ).first()
            if rundb is None:
                logger.warn(f"Run not found for run_id={run_id}")
                raise HTTPException(status_code=404, detail="Run not found")
        else:
            logger.debug("Skipping run query, using rundb=None")
            rundb = None

        logger.debug(f"Processing category: {category}")
        file_path = os.path.join(get_user_directory(tenant_id, user_id), name)
        
        if category == "tables":
            logger.debug("Querying table")
            table_df = await enginemgr.query_table(session, rundb, name)
            result = handle_other_files(file_path, table_df.to_csv(), "csv")
            return JSONResponse(content={"type": "csv", "content": result})

        elif category == "dataframes":
            logger.debug("Retrieving dataframe")
            df = await enginemgr.get_dataframe(rundb, name)
            if df is not None:
                result = handle_other_files(file_path, df.to_csv(), "csv")
                return JSONResponse(content={"type": "csv", "content": result})
            else:
                logger.warn(f"Dataframe {name} not found")
                raise HTTPException(status_code=404, detail=f"Dataframe {name} not found")

        elif category == "files":

            logger.debug(f"File path: {file_path}")
            if os.path.exists(file_path):
                logger.debug(f"File exists: {file_path}, {name}")
                if os.path.isdir(file_path):
                    dir_content = get_directory_contents(file_path)
                    result = handle_other_files(file_path, dir_content['content'], "dir")
                    return JSONResponse(content={"type": "dir", "content": result})

                mime_type = get_mime_type(file_path)
                logger.debug(f"Mime type: {mime_type}")

                if mime_type:
                    if mime_type.startswith(('audio', 'video', 'image')):
                        media_content = handle_media_file(tenant_id, user_id, file_path, name)
                        return JSONResponse(content={"type": media_content["type"], "content": media_content})
                    elif mime_type == 'application/pdf':
                        raw_data = read_pdf(file_path)
                        result = handle_other_files(file_path, raw_data, "pdf")
                        return JSONResponse(content={"type": "pdf", "content": result})

                    elif mime_type == 'message/rfc822':
                        raw_data = read_eml(file_path, "", None)
                        result = handle_other_files(file_path, json.dumps(raw_data), "email")
                        return JSONResponse(content={"type": "email", "content": result})
                    elif mime_type == "application/json":
                        with open(file_path, 'r') as file:
                            content = file.read()
                        try:
                            json_compliant_string = fix_json_string(content)
                            parsed_content = json.loads(json_compliant_string)
                            raw_data = json.dumps(parsed_content, indent=4)
                        except Exception as e:
                            logger.error(f"Error parsing JSON: {e}")
                            raw_data = content
                        result = handle_other_files(file_path, raw_data, "json")
                        return JSONResponse(content={"type": "json", "content": result})
                    elif is_supported_text_mime_type(mime_type):
                        try:
                            # Try reading the file using UTF-8 encoding
                            with open(file_path, 'r', encoding='utf-8') as file:
                                content = file.read()
                        except UnicodeDecodeError:
                            # If a UnicodeDecodeError occurs, try reading with a different encoding, like 'latin-1'
                            with open(file_path, 'r', encoding='latin-1') as file:
                                content = file.read()
                        language_type = detect_language(mime_type)
                        if language_type:
                            raw_data = f"```{language_type}\n{content}\n```"
                        else:
                            raw_data = content
                        result = handle_other_files(file_path, raw_data, "text")
                        return JSONResponse(content={"type": "text", "content": result})

                    elif mime_type == "text/csv":
                        df = pd.read_csv(file_path)
                        result = handle_other_files(file_path, df.to_csv(), "csv")
                        return JSONResponse(content={"type": "csv", "content": result})
                    elif mime_type in ["application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
                        df = pd.read_excel(file_path)
                        result = handle_other_files(file_path, df.to_csv(), "csv")
                        return JSONResponse(content={"type": "csv", "content": result})
                    elif mime_type == "application/x-parquet":
                        df = pd.read_parquet(file_path)
                        result = handle_other_files(file_path, df.to_csv(), "csv")
                        return JSONResponse(content={"type": "csv", "content": result})

                # If we reach here, it's an unknown type
                with open(file_path, 'rb') as file:
                    content = file.read()
                result = handle_other_files(file_path, content.decode('utf-8', errors='ignore'), "unknown")
                return JSONResponse(content={"type": "unknown", "content": result})
            else:
                logger.warn(f"File not found: {file_path}")
                raise HTTPException(status_code=404, detail=f"File {name} not found on SupercogFS")
        else:
            logger.warn(f"Unsupported category: {category}")
            raise HTTPException(status_code=404, detail=f"Datum {name} not found")
        
    except HTTPException as http_exc:
        # Re-raise HTTP exceptions (like 404) to be handled by FastAPI
        raise http_exc
    except Exception as e:
        logger.error(f"Error in get_single_datum: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.delete("/tenant/{tenant_id}/agents/{agent_id}/run/{run_id}/getdatum")
async def delete_single_datum(*, 
        session: Session = Depends(get_session), 
        user: User = Depends(requires_jwt),
        tenant_id: str,
        agent_id: str,
        run_id: str,
        user_id: str,
        category: str,
        name: str):
    rundb = session.exec(
        select(Run).where(
            Run.tenant_id == tenant_id,
            Run.agent_id == agent_id,
            Run.user_id == user_id,
            Run.id == run_id,
        )
    ).first()
    if category == "tables":
        await enginemgr.delete_table(session, rundb, name)
    elif category == "dataframes":
        await enginemgr.delete_dataframe(rundb, name)
    elif category == "files":
        file_path = os.path.join(get_user_directory(tenant_id, user_id), name)
        if os.path.exists(file_path):
            os.remove(file_path)
    else:
        print("Unknown category: ", category)

# Assets are generated as the agent is running, and they are cached into Redis.
@app.get("/asset/{tenant_id}/{user_id}/{asset_id}")
async def get_asset(*, 
        session: Session = Depends(get_session), 
        user: User = Depends(requires_jwt),
        tenant_id: str,
        user_id: str,
        asset_id: str):
    content, content_type = await RunContext.get_asset(tenant_id, user_id, asset_id)
    if content is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return Response(content=content, media_type=content_type)

@app.get("/runs/{run_id}/run_logs", response_model=List[RunLogBase])
async def list_run_logs(*,
        session: Session = Depends(get_session),
        user: User = Depends(requires_jwt),
        run_id: str,
        user_id: Optional[str] = None):
    
    query = get_run_logs(run_id, user_id)
    return session.exec(query).all()

@app.delete("/runs/{run_id}/run_logs")
async def delete_run_logs(
    *,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    run_id: str,
    user_id: Optional[str] = None
):
    run = session.exec(select(Run).where(Run.id == run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    query = get_run_logs(run_id, user_id)
    logs = session.exec(query).all()
    
    [session.delete(log) for log in logs] if logs else None
    session.commit()

@app.get("/runs/{run_id}/reflect", response_model=ReflectionResponse)
async def reflect(*,
        session: Session = Depends(get_session),
        user: User = Depends(requires_jwt),
        run_id: str,
        user_id: Optional[str] = None):
    logs = get_run_logs(run_id, user_id)
    logs = session.exec(logs).all()
    reflection_result = agent_learning.reflect(logs)
    return ReflectionResponse(
        facts=      reflection_result.facts,
        analysis=   reflection_result.analysis,
        token_usage=reflection_result.token_usage
    )
   # return ReflectionResponse(facts=facts, token_usage=token_usage)


@app.get("/runs/{run_id}", response_model=Run)
async def get_run(
    *, 
    session: Session = Depends(get_session), 
    user: User = Depends(requires_jwt),
    run_id: UUID
):
    print("JWT user: ", user)
    run = session.exec(select(Run).where(Run.id == run_id)).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    else:
        return run
    
def get_run_logs(run_id: str, user_id: Optional[str] = None):
    query = select(RunLog)
    if user_id:
        query = query.where(
            RunLog.run_id == run_id, 
            or_(
                RunLog.user_id == user_id, 
                RunLog.scope == "shared"
            )
        )
    else:
        query = query.where(
            RunLog.run_id == run_id,
            RunLog.scope == "shared"
        )
    query = query.order_by(RunLog.created_at.asc())
    return query

@app.patch("/runs/{run_id}", response_model=Run)
async def update_run(*, 
    session: Session = Depends(get_session), 
    user: User = Depends(requires_jwt),
    run_id: UUID, 
    run_update: RunUpdate,
    request: Request,
    ):
    logger.info("Patching Run: ", await request.json())
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run_data = run_update.model_dump(exclude_unset=True)
    for key, value in run_data.items():
        setattr(run, key, value)
    session.add(run)
    session.commit()
    session.refresh(run)

    await pubsub.publish(
        AGENT_EVENTS_CHANNEL, 
        RunUpdatedEvent(agent_id=run.agent_id, user_id=user.user_id, run_id=str(run.id)),
    )

    return run

@app.put("/runs/{run_id}/cancel")
async def cancel_run(
    *, 
    session: Session = Depends(get_session), 
    user: User = Depends(requires_jwt),
    run_id: UUID):
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = "cancelled"
    session.add(run)
    session.commit()
    session.refresh(run)
    await enginemgr.cancel_run(session, run)

    return {"status": "cancelled", "run_id": run_id}

@app.delete("/runs/{run_id}")
async def delete_run(
    *,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    run_id: UUID
):
    run = session.exec(select(Run).where(Run.id == run_id)).first() 
    if run:
        session.delete(run)
        session.commit()
    else:
        raise HTTPException(status_code=404, detail="Run not found")


@app.post("/tenant/{tenant_id}/credentials")
async def set_cred(*,
        session: Session = Depends(get_session),
        user: User = Depends(requires_jwt),
        cred_input: CredentialBase,
        ) -> db.Credential:
    cred = db.Credential.model_validate(cred_input)
    if cred.tool_factory_id in FACTORY_MAP:
        factory = FACTORY_MAP[cred.tool_factory_id]
        if isinstance(factory, DocSourceFactory):
            cred = db.DocSource.model_validate(cred_input)

    session.add(cred) #need the Cred ID in order to store the secrets
    session.commit()
    session.refresh(cred)

    # Now redact the secrets and send them to the secrets store
    cred.stuff_secrets(cred_input.secrets_json)
    session.add(cred)
    session.commit()
    session.refresh(cred)

    # Return new Credential with secrets redacted
    return cred

# Test that Credentials are valid. You can provide either Credential secrets
# like in POST /credentials or provide an ID for an existing credential.
@app.post("/tenant/{tenant_id}/credentials/test")
async def test_cred(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          cred_input: CredentialBase
          ) -> dict:
    cred = db.Credential.model_validate(cred_input)
    if cred.id is not None:
        query = select(db.Credential).where(
            db.Credential.tenant_id == cred.tenant_id,
            db.Credential.user_id == cred.user_id,
            db.Credential.id == cred.id)
        cred_db = session.exec(query).first()
        if cred_db is None:
            raise HTTPException(status_code=404, detail=f"Credential {cred.id} not found")
        secrets = cred_db.retrieve_secrets()
        secrets.update(json.loads(cred_input.secrets_json or "{}"))
        cred = cred_db
    else:
        secrets = json.loads(cred.secrets_json or "{}")

    print("Testing with SECRETS: ", secrets)
    tool_factory = next((tf for tf in TOOL_FACTORIES if tf.id == cred.tool_factory_id), None)
    if tool_factory is None:
        raise HTTPException(status_code=500, detail=f"No Tool found for cred, tool id '{cred.tool_factory_id}'")

    # This is all so that a tool (like AuthRESTTool) can do "test credentials" and
    # verify that env vars exist.
    env_var_list = secrets_service.list_credentials(cred.tenant_id, user.user_id, "ENV:", include_values=True)
    env_vars = {k[4:]: v for k, v in env_var_list}

    run_context = RunContext.create_squib_context(cred.tenant_id, user.user_id, env_vars)
    tool_factory.run_context = run_context

    # FIXME: I don't like that this is here or required, but I don't an alternative other than
    # to now allow tools to require the filesystem to test creds.    
    with get_agent_filesystem(cred.tenant_id, user.user_id):
        if inspect.iscoroutinefunction(tool_factory.test_credential):
            result = await tool_factory.test_credential(cred, secrets)
        else:
            result = tool_factory.test_credential(cred, secrets)

        if result is not None:
            return {"success": False, "message": result}
        else:
            return {"success": True, "message": "None"}

@app.get("/tenant/{tenant_id}/credentials")
async def list_creds(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          user_id: Optional[str] = None,
          ) -> list[dict]:
    if user_id is not None:
        query = select(db.Credential).where(
            db.Credential.tenant_id == tenant_id,
            or_(db.Credential.user_id == user_id, db.Credential.scope == 'shared')
        )
    else:
        query = select(db.Credential).where(
            db.Credential.tenant_id == tenant_id,
            db.Credential.scope == 'shared')

    return [r.model_dump() for r in session.exec(query).all()]

@app.get("/tenant/{tenant_id}/credentials/{credential_id}")
async def get_cred(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          user_id: str,
          credential_id: str,
          ) -> db.Credential:
    query = select(db.Credential).where(
        db.Credential.tenant_id == tenant_id,
        db.Credential.user_id == user_id,
        db.Credential.id == credential_id)
    cred = session.exec(query).first()
    if cred is not None:
        return cred
    else:
        raise HTTPException(status_code=404, detail=f"Credential {credential_id} not found")

@app.patch("/tenant/{tenant_id}/credentials/{credential_id}")
async def update_cred(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          credential_id: str,
          cred_input: CredentialBase
          ) -> db.Credential:
    cred: db.Credential = session.get(db.Credential, credential_id)

    if cred:
        for k, v in cred_input.model_dump().items():
            if k in ['id', 'secrets_json']:
                continue
            setattr(cred, k, v)

        # Now update any secrets and send them to the secrets store
        new_secrets = json.loads(cred_input.secrets_json or '{}')

        if new_secrets:
            secrets = cred.retrieve_secrets()
            secrets.update(new_secrets)
            cred.stuff_secrets(json.dumps(secrets))

        session.add(cred) #need the Cred ID in order to store the secrets
        session.commit()
        session.refresh(cred)

        # Return new Credential with secrets redacted
        return cred

@app.delete("/tenant/{tenant_id}/credentials/{credential_id}")
async def delete_cred(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          credential_id: str,
          user_id: str
          ):
    query = select(db.Credential).where(
        db.Credential.tenant_id == tenant_id,
        db.Credential.user_id == user_id,
        db.Credential.id == credential_id)
    cred = session.exec(query).first()
    if cred:
        cred.delete_secrets()
        session.delete(cred)
        session.commit()
    else:
        raise HTTPException(status_code=404, detail=f"Credential {credential_id} not found")

class SecretsHash(BaseModel):
    secrets: dict[str, str]

@app.post("/tenant/{tenant_id}/{user_id}/secrets")
async def set_secrets(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          user_id: str,
          secretsh: SecretsHash,
          agent_id: str|None=None,
          ) -> str:
    # Save some Env Vars for the user. We also go and update any running
    # agents owned by the user so the secret can be used immediately.
    for key, value in secretsh.secrets.items():
        key = f"ENV:{key}"
        secrets_service.set_credential(tenant_id, user_id, key, value)

    await enginemgr.update_user_secrets(tenant_id, user_id, secretsh.secrets)

    return "OK"


@app.delete("/tenant/{tenant_id}/{user_id}/secrets")
async def delete_secret(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          user_id: str,
          key: str,
          ) -> str:
    cred_id = f"ENV:{key}"
    secrets_service.delete_credential(tenant_id, user_id, cred_id)   
    return "OK"


@app.get("/tenant/{tenant_id}/{user_id}/secrets")
async def list_secrets(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          user_id: str,
          ) -> SecretsHash:
    secrets = {s[4:]:"**********" for s in secrets_service.list_credentials(tenant_id, user_id, "ENV:")}
    return SecretsHash(secrets=secrets)


@app.get("/tenant/{tenant_id}/{drive}/folders")
async def list_folders(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          drive: str,
          ) -> list[str]:
    """ 
        List the folders for a given tenant and 'drive'. Drive can
        be 'default' for the system file store, or the name of a "file system"
        credential like Google Docs.
    """

    s3 = get_boto_client('s3')
    prefix = f"{tenant_id}/"

    bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
  
    # Using '/' as a delimiter to simulate a folder structure
    delimiter = '/'

    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, Delimiter=delimiter)

    # Print out common prefixes, which represent "folders"
    folders = []
    if 'CommonPrefixes' in response:
        folders = []
        for folder in response['CommonPrefixes']:
            val = folder['Prefix']
            if val.startswith(prefix):
                val = val[len(prefix):]
            folders.append(val)
    else:
        print("No folders found under the specified prefix.")

    return folders


@app.get("/tenant/{tenant_id}/{drive}/files/{folder}")
async def list_files(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          drive: str,
          folder: str,
          ) -> list[dict]:
    """ List the files inside the given folder in the given drive. """

    s3 = get_boto_client('s3')
    prefix = f"{tenant_id}/{folder}/"

    bucket_name = config.get_global("S3_FILES_BUCKET_NAME") or ""
  
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    # Print out the files contained in the folder
    files: list[dict] = []
    if 'Contents' in response:
        files = []
        for file in response['Contents']:
            val = file['Key']
            last_modified = file['LastModified']
            if val.startswith(prefix):
                val = val[len(prefix):]
            url = calc_s3_url(s3, bucket_name, file['Key'])
            files.append({"name": val, "size": file['Size'], "url": url, "last_modified": last_modified})
    return sorted(files, key=lambda x: x['name'])

## NOTE!! The URL only differs from the files listing by using 'file/' instead of 'files/'
@app.get("/tenant/{tenant_id}/{drive}/file/{folder}")
async def get_file(*,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    tenant_id: str,
    drive: str,
    folder: str,
    filename: str
    ) -> dict:
    s3 = get_boto_client('s3')

    bucket_name = config.get_global("S3_FILES_BUCKET_NAME") or ""

    user_id, folder = folder.split(":")
    if folder:
        s3_folder = f"{user_id}/{folder}"
    else:
        s3_folder = user_id
    object_name = f"{tenant_id}/{s3_folder}/{filename}"
    print(object_name)

    # Make sure we have file locally - download it if not
    user_dir = get_user_directory(tenant_id, user_id)
    file_path = os.path.join(user_dir, folder or "", filename)
    if not os.path.exists(file_path):
        await download_s3_file(bucket_name, object_name, file_path)

    return create_presigned_url(s3, bucket_name, object_name)

# Upload a file to the cloud filesystem. If you specify index=True and a Run then we
# will retrieve the agent from the Run, and if the agent has a default RAG index then the
# file will be added to that index.
@app.post("/tenant/{tenant_id}/{drive}/files")
async def create_file(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          drive: str,
          folder: str,
          index: Optional[bool] = False,
          run_id: Optional[str] = None,
          file: UploadFile = File(...),
          background_tasks: BackgroundTasks,
          ) -> str:
    """ Create a file in the given drive and folder for the tenant."""
    bucket = config.get_global("S3_FILES_BUCKET_NAME")

    user_id, folder = folder.split(":")
    fname = os.path.join(folder, f"{file.filename}")
    object_name = f"{tenant_id}/{user_id}/{fname}"

    # Save the file to the user filesystem
    user_file = os.path.join(
        get_user_directory(tenant_id, user_id),
        fname,
    )

    async with aiofiles.open(user_file, "wb") as temp_file:
        while chunk := await file.read(10*1024):
            # Process your chunk here (e.g., saving to a destination, processing data)
            await temp_file.write(chunk)
        await temp_file.flush()

    print("Wrote user file: ", user_file)

    if index and run_id:
        mime_type, _ = mimetypes.guess_type(user_file, False)
        if mime_type is not None and not mime_type.startswith("image/"):
            # Index non image files
            run = session.get(Run, run_id)
            if run:
                agent = session.get(Agent, run.agent_id)
                if agent:
                    indices = agent.get_enabled_indexes()
                    if len(indices) > 0:
                        print("Queueing upload file to add to personal index")
                        await file.seek(0)
                        background_tasks.add_task(
                            add_index_file, 
                            session=session, 
                            user=user,
                            tenant_id=tenant_id, 
                            index_id=indices[0].index_id, 
                            user_id=user_id,
                            file=str(temp_file.name),
                        )
                    else:
                        logger.warn(f"No indexes enabled for agent {agent.id} - {agent.name}")
                else:
                    logger.warn(f"Agent not found for run {run_id}")
            else:
                logger.warn(f"Run not found for run {run_id}")

    elif index and run_id is None:
        rollbar.report_message(f"Indexing request for file {user_file} but run_id is None", "error")

    return upload_file_to_s3(
        temp_file.name, 
        bucket, 
        object_name,
        file.content_type,
    )

@app.delete("/tenant/{tenant_id}/{drive}/files/{folder}")
async def delete_file(*,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    tenant_id: str,
    drive: str,
    folder: str,
    filename: str
    ) -> str:
    """ Delete a file from the given folder in the given drive. """

    user_id, folder = folder.split(":")

    delete_user_file(tenant_id, user_id, filename, folder)
    s3 = get_boto_client('s3')
    bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
    if folder:
        folder = f"{user_id}/{folder}"
    else:
        folder = user_id
    object_name = f"{tenant_id}/{folder}/{filename}"

    response = s3.delete_object(Bucket=bucket_name, Key=object_name)
    if 'ResponseMetadata' in response and 'HTTPStatusCode' in response['ResponseMetadata']:
        if response['ResponseMetadata']['HTTPStatusCode'] == 204:
            wait_for_deletion(s3, bucket_name, object_name)
            return f"Deleted {object_name}"
    
    return f"File not found: {object_name}"

@app.delete("/tenant/{tenant_id}/{drive}/files/{folder}/batch")
async def delete_files(*,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    tenant_id: str,
    drive: str,
    folder: str,
    filenames: List[str]
    ) -> dict:
    """ Delete multiple files from the given folder in the given drive. """
    user_id, folder = folder.split(":")
    s3 = get_boto_client('s3')
    bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
    
    if folder:
        folder_path = f"{user_id}/{folder}"
    else:
        folder_path = user_id
    
    # Prepare the list of objects to delete
    objects_to_delete = [{'Key': f"{tenant_id}/{folder_path}/{filename}"} for filename in filenames]
    
    try:
        # Delete the objects
        response = s3.delete_objects(
            Bucket=bucket_name,
            Delete={'Objects': objects_to_delete}
        )
        
        # Process the response
        deleted = [obj['Key'] for obj in response.get('Deleted', [])]
        errors = [{'Key': obj['Key'], 'Code': obj['Code'], 'Message': obj['Message']} 
                  for obj in response.get('Errors', [])]
        
        # Delete files from user's record
        for filename in filenames:
            delete_user_file(tenant_id, user_id, filename, folder)
        
        return {
            "deleted": deleted,
            "errors": errors
        }
    
    except Exception as e:
        return {"error": str(e)}

## RAG endpoints

@app.post("/tenant/{tenant_id}/doc_indexes")
async def create_index(*,
        session: Session = Depends(get_session),
        user: User = Depends(requires_jwt),
        index_input: DocIndexBase,
        ) -> db.DocIndex:
    index = db.DocIndex.model_validate(index_input)
    existing = session.exec(
        select(db.DocIndex).where(
            db.DocIndex.tenant_id == index.tenant_id,
            db.DocIndex.user_id == index.user_id,
            db.DocIndex.name == index.name,
        )
    ).first()
    if existing is not None:
        return existing
    
    session.add(index) #need the Cred ID in order to store the secrets
    session.commit()
    session.refresh(index)
    return index

@app.patch("/tenant/{tenant_id}/doc_indexes/{index_id}")
async def update_index(*,
        session: Session = Depends(get_session),
        user: User = Depends(requires_jwt),
        index_id: str,
        index_update: dict,
        ) -> db.DocIndex:
    index = session.get(db.DocIndex, index_id)
    if index:
        for k, v in index_update.items():
            setattr(index, k, v)
        session.add(index) #need the Cred ID in order to store the secrets
        session.commit()
        session.refresh(index)
        return index
    else:
        raise HTTPException(status_code=404, detail=f"Index {index_id} not found")

@app.delete("/tenant/{tenant_id}/doc_indexes/{index_id}")
async def delete_index(*,
        session: Session = Depends(get_session),
        user: User = Depends(requires_jwt),
        index_id: str,
        ) -> dict:
    index = session.get(db.DocIndex, index_id)
    if index and index.user_id == user.user_id:
        session.delete(index)
        session.commit()
    else:
        raise HTTPException(status_code=403, detail=f"Not authorized")
    return {"result": "ok"}

@app.get("/tenant/{tenant_id}/doc_indexes")
async def list_indexes(*,
            session: Session = Depends(get_session),
            user: User = Depends(requires_jwt),
            tenant_id: str,
            user_id: str
            ) -> list[db.DocIndex]:
    # FIXME: Validate the JWT user is at least a member of the indicate Tenant
    query = select(db.DocIndex).where(
        db.DocIndex.tenant_id == tenant_id,
        or_(
            db.DocIndex.user_id == user_id,
            db.DocIndex.scope == 'shared',
        )
    )
    results = list(session.exec(query).all())
    if len(results) == 0:
        # Auto-create the user's personal index
        index = db.DocIndex(
            id = user.personal_index_id(),
            tenant_id=tenant_id,
            user_id=user_id,
            name=PERSONAL_INDEX_NAME,
            scope="private",
        )
        session.add(index)
        session.commit()
        results.append(index)
    return results


@app.get("/tenant/{tenant_id}/doc_indexes/{index_id}")
async def get_index(*,
            session: Session = Depends(get_session),
            user: User = Depends(requires_jwt),
            tenant_id: str,
            index_id: str
            ) -> db.DocIndex:
    query = select(db.DocIndex).where(
        db.DocIndex.tenant_id == tenant_id,
        db.DocIndex.id == index_id,
        or_(db.DocIndex.user_id == user.user_id, db.DocIndex.scope == 'shared')
    )
    res = session.exec(query).first()
    if res:
        return res
    else:
        raise HTTPException(status_code=404, detail=f"Index {index_id} not found")
    
@app.post("/tenant/{tenant_id}/doc_indexes/{index_id}/sources")
async def add_doc_source(
    *,
    tenant_id: str,
    index_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    config_input: DocSourceConfigCreate,  # Change to accept raw dict instead of model
    background_tasks: BackgroundTasks
) -> db.DocSourceConfig:
    # Check if the DocIndex exists and belongs to the tenant
    doc_index = session.exec(
        select(db.DocIndex).where(
            db.DocIndex.tenant_id == tenant_id,
            db.DocIndex.id == index_id
        )
    ).first()
    if not doc_index:
        raise HTTPException(status_code=404, detail="DocIndex not found")
    
    # Create the DocSourceConfig
    vals = config_input.model_dump()
    
    # Ensure provider_data is properly set
    provider_data = vals.get("provider_data")
    if isinstance(provider_data, dict):
        vals["provider_data"] = provider_data
    elif isinstance(provider_data, str):
        try:
            vals["provider_data"] = json.loads(provider_data)
        except json.JSONDecodeError:
            vals["provider_data"] = {"raw": provider_data}
    
    doc_source_config = db.DocSourceConfig.model_validate(vals)
    session.add(doc_source_config)
    session.commit()
    session.refresh(doc_source_config)

    # Make a background task to call get_documents
    background_tasks.add_task(process_documents, doc_source_config, index_id, user.user_id, user.tenant_id)

    return doc_source_config


async def process_documents(doc_source_config: DocSourceConfig, index_id: str, user_id: str, tenant_id: str):
    print("sleeping")
    await asyncio.sleep(2)
    print("Sleep is done")
    factory: DocSourceFactory = get_doc_source_factory_instance(doc_source_config)
    try:
        async for document in factory.get_documents(
            folder_id=None,
            tenant_id=tenant_id,
            index_id=index_id,
            **doc_source_config.provider_data,
        ):
            print(f"Indexing document: {document}")
            # TODO: Index the document
    except Exception as e:
        print(f"Error processing documents: {e}")
        raise  # Re-raise to ensure error is properly handled

@app.get("/tenant/{tenant_id}/doc_indexes/{index_id}/sources")
async def get_doc_sources(
    *,
    tenant_id: str,
    index_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt)
) -> List[DocSourceConfig]:
    # Check if the DocIndex exists and belongs to the tenant
    doc_index = session.exec(select(db.DocIndex).where(db.DocIndex.id == index_id)).first()
    if not doc_index:
        raise HTTPException(status_code=404, detail="DocIndex not found")
    
    # TODO: Add tenant check here if necessary
    
    # Retrieve all DocSourceConfigs for the given DocIndex
    query = select(DocSourceConfig).where(DocSourceConfig.doc_index_id == index_id)
    doc_source_configs = session.exec(query).all()
    return list(doc_source_configs)

def get_doc_source_factory_instance(doc_source: DocSourceConfig) -> DocSourceFactory:
    factory: DocSourceFactory = FACTORY_MAP.get(doc_source.doc_source_factory_id)
    if factory is None:
        raise HTTPException(status_code=404, detail="DocSource factory not found")
    return factory.__class__()

@app.get("/tenant/{tenant_id}/doc_indexes/{index_id}/sources/{source_id}/authorize")
async def get_doc_source_authorize_url(
    *,
    tenant_id: str,
    index_id: str,
    source_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt)
) -> dict:
    # Check if the DocIndex exists and belongs to the tenant
    doc_index = session.exec(
        select(db.DocIndex).where(
            db.DocIndex.id == index_id, 
            db.DocIndex.user_id == user.user_id
        )
    ).first()
    if not doc_index:
        raise HTTPException(status_code=404, detail="DocIndex not found")
    
    # TODO: Add tenant check here if necessary
    source: DocSourceConfig|None
    for candidate in doc_index.source_configs:
        if candidate.id == source_id:
            source = candidate
            break
    if not source:
        raise HTTPException(status_code=404, detail="DocSource not found")
    factory = get_doc_source_factory_instance(source)

    link = factory.get_authorize_url(
        tenant_id = tenant_id, 
        user_id=user.user_id, 
        index_id=index_id, 
        source_id=source_id
    )
    return {"authorize_url": link}

@app.post("/tenant/{tenant_id}/doc_indexes/{index_id}/sources/{source_id}/authorize_callback")
async def doc_source_authorize_callback(
    *,
    tenant_id: str,
    index_id: str,
    source_id: str,
    request: Request,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt)
) -> DocSourceConfig:
   # Invoked from the Dashboard after it receives an authorize callback from a DocSource provider 
    doc_source = session.exec(
        select(db.DocSourceConfig).where(
            db.DocSourceConfig.id == source_id,
            db.DocSourceConfig.doc_index_id == index_id, 
        )
    ).first()
    if not doc_source:
        raise HTTPException(status_code=404, detail="DocSource not found")
    doc_source.provider_data = await request.json()
    session.add(doc_source)
    session.commit()
    session.refresh(doc_source)

    factory: DocSourceFactory = get_doc_source_factory_instance(doc_source)
    await factory.authorize_callback(doc_source.provider_data)

    return doc_source


@app.delete("/tenant/{tenant_id}/doc_indexes/{index_id}/sources/{source_id}")
async def delete_doc_source(
    *,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    tenant_id: str,
    index_id: str,
    source_id: str,
) -> dict:
    # Check if the DocIndex exists and belongs to the tenant
    doc_index = session.exec(select(db.DocIndex).where(db.DocIndex.id == index_id)).first()
    if not doc_index:
        raise HTTPException(status_code=404, detail="DocIndex not found")
    
    # TODO: Add tenant check here if necessary
    
    # Check if the DocSourceConfig exists and belongs to the DocIndex
    doc_source_config = session.exec(
        select(DocSourceConfig)
        .where(DocSourceConfig.id == source_id)
        .where(DocSourceConfig.doc_index_id == index_id)
    ).first()
    
    if not doc_source_config:
        raise HTTPException(status_code=404, detail="DocSource not found")

    # Delete the DocSourceConfig
    session.delete(doc_source_config)
    session.commit()
    
    return {"message": "DocSource deleted successfully"}

@app.post("/tenant/{tenant_id}/doc_indexes/{index_id}/files")
async def add_index_file(*,
          session: Session = Depends(get_session),
          user: User = Depends(requires_jwt),
          tenant_id: str,
          index_id: str,
          user_id: str,
          file: UploadFile = File(...)
          ) -> str:
    """ Add a file to a DocIndex """
    if isinstance(file, str):
        file = UploadFile(
            filename=os.path.basename(file),
            file=open(file, "rb"),            
        )

    partition = get_ragie_partition(tenant_id, index_id)
    opts = {
        "file": {
            "file_name": file.filename,
            "content": file.file.read(),
        },
        "metadata": {
            "owner":user.email,
            "user_id": user_id,
            "tenant_id": tenant_id
        },
        "partition": partition,
    }
    print(f"Uploading file to Ragie partition {partition}: ", file.filename)
    r = ragie.documents.create(
        request = opts
    )
    print(r)
    return "doc added"

@app.get("/tenant/{tenant_id}/doc_indexes/{index_id}/page/{target_page}/files")
async def list_index_files(*,
            session: Session = Depends(get_session),
            user: User = Depends(requires_jwt),
            tenant_id: str,
            index_id: str,
            user_id: str,
            target_page: int,
            page_size: int = 10
            ) -> list[dict]:
    """ List the files in a DocIndex """
    res = ragie.documents.list(
        request = {"partition": get_ragie_partition(tenant_id, index_id)}
    )
    current_page = 1
    next_func = res.next
    while current_page < target_page and next_func and len(res.result.documents) == page_size:
        try:
            res = next_func()
            next_func = res.next
            current_page += 1
        except Exception as e:
            print(f"An error occurred: {e}")
            break

    if current_page == target_page:
        return [r.model_dump() for r in res.result.documents]
    else:
        return []

@app.delete("/tenant/{tenant_id}/doc_indexes/{index_id}/files/{doc_id}")
async def delete_index_files(*,
    session: Session = Depends(get_session),
    user: User = Depends(requires_jwt),
    tenant_id: str,
    index_id: str,
    doc_id: str,
    ):
    response = ragie.documents.delete(document_id = doc_id)
    return

@app.get("/tenant/{tenant_id}/doc_indexes/{index_id}/search")
async def search_index_files(*,
            session: Session = Depends(get_session),
            user: User = Depends(requires_jwt),
            tenant_id: str,
            index_id: str,
            user_id: str,
            query: str,
    ):
    """ Quick search in the DocIndex """

    response = ragie.retrievals.retrieve(
        request = {
            "query": query,
            "partition": get_ragie_partition(tenant_id, index_id),
            # "top_k": 10
        }
    )
    recs = [r.model_dump() for r in response.scored_chunks]
    pprint(recs)
    return recs


# DONE ENDPOINTS

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
	exc_str = f'{exc}'.replace('\n', ' ').replace('   ', ' ')
	logging.error(f"{request}: {exc_str}")
	content = {'status_code': 10422, 'message': exc_str, 'data': None}
	return JSONResponse(content=content, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

####################
### OAUTH FLOWS
####################

class OauthRequest(BaseModel):
    ut_id: str
    tool_factory_id: str
    # Options to the Oauth call (like customhost for Salesforce)
    options: dict[str,str]
    cred_name: str
    # Return URL to go back to the Dashboard
    return_url: str

@app.post("/run_oauth")
async def run_oauth(*,
    session: Session = Depends(get_session),
    oauth_request: OauthRequest):
    # Initiate an Oauth flow to create a new Oauth credential. You supply the
    # provider=[salesforce,google,etc...] and UserId and the ID of the tool 
    # factory which describes the Oauth flow.
    # We run the Oauth flow with the user and when it completes then we will
    # create a Credential for them to save their tokens. Finally we redirect
    # BACK to the caller with the new credential ID.

    # FIXME: Let ToolFactory provide all the Oauth blueprint settings. For now
    # these are hardcoded in the oauth_flask module.

    # FIXME: we should probably create the empty Credential right here while we have
    # it's parameters, and then just pass the credential ID through the oauth flow
    # session instead of all of these args.
    opts = (
        oauth_request.options | 
        {
            "ut_id": oauth_request.ut_id, 
            "return_url": oauth_request.return_url,
            "cred_name": oauth_request.cred_name,
            "tool_factory_id": oauth_request.tool_factory_id,
        }
    )
    # A bit of a hack. Take first segment of the tool_factory_id to get 
    # the "oauth provider" understood by oauth_flask.py.
    provider = get_oauth_provider(oauth_request.tool_factory_id)
    url = f"/login/start_{provider}?" + "&".join([f"{k}={v}" for k,v in opts.items()])
    print(url)
    return redirect(url)

def get_oauth_provider(tool_factory_id: str):
    if 'salesforce' in tool_factory_id:
        return "salesforce"
    else:
        # Pretty sure this hack is to allow different Google tools to suggest
        # they scopes they need, and then to re-use the same Google Oauth flow
        from .oauth_flask import google_blueprint

        tf = [tf for tf in TOOL_FACTORIES if tf.id == tool_factory_id][0]
        if tf.oauth_scopes:
            google_blueprint.scope = tf.oauth_scopes
        client_id, client_secret = tf.get_oauth_client_id_and_secret()
        print("Main Oauth flowing using this client ID: ", client_id)
        if client_id:
            google_blueprint.client_id = client_id
            google_blueprint._client_id = client_id
        if client_secret:
            google_blueprint.client_secret = client_secret

        return "google"
    
## Mount a Flask App which we use just to get the FlasKDance oauth library
# for oauth flows. We should just write that thing to work with FastAPI
def oauth_login_callback(
        ut_id: str, 
        cred_name: str, 
        tool_factory_id: str, 
        creds: dict, 
        user_info: dict
    ):
    user_id, tenant_id = ut_id.split(":")

    engine = db_connect(SERVICE)
    with Session(engine) as session:
        cred = session.exec(
            select(db.Credential).where(
                db.Credential.tenant_id == tenant_id,
                db.Credential.user_id == user_id,
                db.Credential.name == cred_name
            )
        ).first()
        if cred:
            print("Updating existing credential: ", cred.name)
            # Update existing credential
            cred.secrets_json=json.dumps({"tokens": creds.token, "userinfo": user_info})
        else:
            print("SAVING NEW CREDENTIAL: ", cred_name)
            print("User: ", ut_id, " creds: ", creds, " user_info: ", user_info)
            cred = db.Credential(
                name=cred_name,
                user_id=user_id,
                tenant_id=tenant_id,
                scope="private",
                tool_factory_id=tool_factory_id,
                secrets_json=json.dumps({"tokens": creds.token, "userinfo": user_info})
            )
        session.add(cred)
        session.commit()
        session.refresh(cred)

        # FIXME: We should have the secrets wrangling in some kind of model signal
        # inside Credential.
        cred.stuff_secrets(cred.secrets_json)
        session.add(cred)
        session.commit()
        session.refresh(cred)


supercog.engine.oauth_flask.LOGIN_CALLBACK = oauth_login_callback

# Mount our Flask app just used for oauth things
app.mount("/login", WSGIMiddleware(oauth_app))

def handle_sigterm(signum, frame):
    print("Parent received termination signal. Cleaning up children...")
    dispatcher.close()

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

if __name__ == "__main__":
    try:
        serve(app, SERVICE)
    except KeyboardInterrupt:
        print("Shutting down")
        

