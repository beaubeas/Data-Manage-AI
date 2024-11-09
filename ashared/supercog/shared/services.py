import os
from dotenv import dotenv_values
from pathlib import Path
from typing import Any

KNOWN_SERVICES = {
    "engine",
    "triggersvc",
    "credentials",
    "ragservice",
    "dashboard",
}

SERVICE_PORTS = {
    "engine": 8080,
    "triggersvc": 8002,
    "ragservice": 9000,
    "dashboard": 3000,
}

class Config:
    DYNAMIC_TOOLS_AGENT_TOOL_ID = "auto_dynamic_tools"
    SPECIAL_AGENT_SUPERCOG_NAME = "Supercog"
    SPECIAL_AGENT_SLACK_PRIVATE = "Slack Private Supercog" # must match the name inside the Slack agent template in /system_agents
    SLACK_PUBLIC_AGENTS_FOLDER = "Slack Channels"

    def __init__(self) -> None:
        self.env = {}

    def get_port(self, service_name: str) -> int:
        return SERVICE_PORTS[service_name]

    def get_browser_api_key(self) -> str | None:
        return self.get_global("SERP_API_KEY")
    
    def get_tavily_api_key(self) -> str | None:
        return self.get_global("TAVILY_API_KEY")
    
    def get_rapidapi_key(self) -> str | None:
        return self.get_global("RAPIDAPI_KEY")
    
    def get_global(self, key: str, required=True) -> str | None:
        val = self.env.get(key, os.environ.get(key))
        if val is None and required:
            raise RuntimeError(f"Missing required config setting: {key}")
        return val
    
    def get_option(self, key: str, default=None) -> Any:
        val = self.env.get(key, os.environ.get(key))
        return val or default
    
    def is_dev(self) -> bool:
        return self.get_global("ENV") == "dev"
    
    def is_prod(self) -> bool:
        return self.get_global("ENV") == "prod"
    
    def get_email_sender(self) -> str:
        c = self.get_global("EMAIL_SENDER", required=False)
        if c:
            return c
        else:
            return "Supercog Admin <admin@mail.supercog.ai>"

config = Config()

def running_in_docker():
    return os.path.exists('/.dockerenv')

def serve(fast_api_app, name: str):
    import uvicorn
    host = config.get_global("HOST", False) or "0.0.0.0"
    uvicorn.run(fast_api_app, host=host, port=config.get_port(name), log_level="debug")

def db_connection_string(service_name: str) -> str:
    dbname = os.environ.get('DATABASE_NAME', f"monster_{service_name}")
    # We allow database specific connection strings, to support DO connection pools which
    # can only talk to a single database.
    specific = config.get_global(f"{service_name.upper()}_DATABASE_URL", False)
    if specific is not None:
        return specific
    dburl = config.get_global('DATABASE_URL')
    idx = dburl.rfind('/')
    if idx > 0:
        dburl = dburl[:idx+1]
        return dburl + dbname

def db_connect(service_name: str):
    from sqlalchemy import create_engine

    # Connect to postgres
    return create_engine(db_connection_string(service_name), pool_size=2)

def get_service_host(service_name: str) -> str:
    envval = config.get_global(f"{service_name.upper()}_URL", False)
    if envval:
        return envval
    return f"http://localhost:{config.get_port(service_name)}"

def get_public_service_host(service_name: str) -> str:
    # Returns a hostname/port for accessing service from outside
    # of production. We are using this for backend-based Oauth
    # flows. This could return direct ports, or probably better for
    # HTTPS we always return 80 but we have a reverse proxy config
    # in Nginx.
    host = get_public_service_domain(service_name)

    return (
        f"http://{host}:{config.get_port(service_name)}" 
        if config.is_dev() 
        else f"https://{host}"
    )

def get_public_service_domain(service_name: str) -> str:
    if config.is_dev():
        return "localhost" 
    else:
        if service_name == "dashboard":
            service_name = "app"
        return f"{service_name}.supercog.ai"

def _get_session():
    from sqlmodel import Session
    service = Path.cwd().name
    engine = db_connect(service)
    return Session(engine)

# DB SETUP
# create database monster_engine;
# create database monster_eventsvc;
# create database monster_credentials;
