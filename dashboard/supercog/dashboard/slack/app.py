import logging
from fastapi import Request
import reflex as rx

from slack_sdk.oauth.installation_store import Installation
from slack_sdk.web.async_client import AsyncWebClient

from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from supercog.shared.services import config
from supercog.dashboard.slack.utils.slack_urls import SLACK_SCOPES

from .listeners import register_listeners
from .installation_store import SupercogInstallationStore
from .utils.slack_modes import is_events_mode, is_socket_mode

SLACK_AI_BOT_TOKEN=config.get_global("SLACK_AI_BOT_TOKEN", required=False) or None
SLACK_AI_APP_TOKEN=config.get_global("SLACK_AI_APP_TOKEN", required=False) or None
SLACK_CLIENT_ID=config.get_global("SLACK_CLIENT_ID", required=False) or None
SLACK_CLIENT_SECRET=config.get_global("SLACK_CLIENT_SECRET", required=False) or None
SLACK_SIGNING_SECRET=config.get_global("SLACK_SIGNING_SECRET", required=False) or None
SLACK_REDIRECT_URL=config.get_global("SLACK_REDIRECT_URL", required=False) or None

# Globals to be used after initialize_slack is called
event_app: AsyncApp | None
event_handler: AsyncSlackRequestHandler | None

import os
logger = logging.getLogger("slack_app")
if os.environ.get("DEBUG"):
    logging.getLogger("slack_bolt").setLevel(logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


async def run_slack_app_socket_mode(socket_handler: AsyncSocketModeHandler):
    await socket_handler.start_async()

async def slack_receive_event(req: Request):
    return await event_handler.handle(req)

async def slack_oauth_callback(code: str):
    client = AsyncWebClient()

    # Complete the installation by calling oauth.v2.access API method
    oauth_response = None
    try:
        oauth_response = await client.oauth_v2_access(
            client_id=SLACK_CLIENT_ID,
            client_secret=SLACK_CLIENT_SECRET,
            redirect_uri=SLACK_REDIRECT_URL,
            code=code
        )
    except Exception as e:
        logger.error(f"[Slack OAuth] API error:\n{e}")
        return {"result": "failure"}
    
    installed_enterprise = oauth_response.get("enterprise") or {}
    is_enterprise_install = oauth_response.get("is_enterprise_install")
    installed_team = oauth_response.get("team") or {}
    installer = oauth_response.get("authed_user") or {}
    incoming_webhook = oauth_response.get("incoming_webhook") or {}
    bot_token = oauth_response.get("access_token")
    # NOTE: oauth.v2.access doesn't include bot_id in response
    bot_id = None
    enterprise_url = None
    if bot_token is not None:
        auth_test = await client.auth_test(token=bot_token)
        bot_id = auth_test["bot_id"]
        if is_enterprise_install is True:
            enterprise_url = auth_test.get("url")

    installation = Installation(
        app_id=oauth_response.get("app_id"),
        enterprise_id=installed_enterprise.get("id"),
        enterprise_name=installed_enterprise.get("name"),
        enterprise_url=enterprise_url,
        team_id=installed_team.get("id"),
        team_name=installed_team.get("name"),
        bot_token=bot_token,
        bot_id=bot_id,
        bot_user_id=oauth_response.get("bot_user_id"),
        bot_scopes=oauth_response.get("scope"),  # comma-separated string
        user_id=installer.get("id"),
        user_token=installer.get("access_token"),
        user_scopes=installer.get("scope"),  # comma-separated string
        incoming_webhook_url=incoming_webhook.get("url"),
        incoming_webhook_channel=incoming_webhook.get("channel"),
        incoming_webhook_channel_id=incoming_webhook.get("channel_id"),
        incoming_webhook_configuration_url=incoming_webhook.get("configuration_url"),
        is_enterprise_install=is_enterprise_install,
        token_type=oauth_response.get("token_type"),
    )

    # Store the installation in our db
    await event_app.installation_store.async_save(installation)

    return {
        "result": "success",
        "slack_user_id": installer.get("id"),
        "slack_team_id": installed_team.get("id"),
    }

def initialize_slack(reflex_app: rx.App):
    global event_app, event_handler
    # If SLACK_CLIENT_SECRET and SLACK_CLIENT_ID slack defaults to using events mode, ignores
    # SLACK_AI_BOT_TOKEN. We hope onto that logic here. If they are specified (even if
    # SLACK_AI_BOT_TOKEN is as well) use events mode
    if is_events_mode():
        event_app = AsyncApp(
            signing_secret=SLACK_SIGNING_SECRET,
            oauth_settings=AsyncOAuthSettings(
                client_id=SLACK_CLIENT_ID,
                client_secret=SLACK_CLIENT_SECRET,
                installation_store=SupercogInstallationStore(),
                scopes=SLACK_SCOPES,
                redirect_uri=SLACK_REDIRECT_URL,
                install_path="/slack/install",
                redirect_uri_path="/home",
            ),
        )
        register_listeners(event_app)
        event_handler = AsyncSlackRequestHandler(event_app)

        # Add endpoints
        reflex_app.api.add_api_route("/slack/events", slack_receive_event, methods=["POST"])
        print("!!!! RUN SLACK APP EVENTS MODE")

    elif is_socket_mode():
        socket_app = AsyncApp(token=SLACK_AI_BOT_TOKEN)
        register_listeners(socket_app)

        try:
            socket_handler = AsyncSocketModeHandler(socket_app, SLACK_AI_APP_TOKEN)
            reflex_app.register_lifespan_task(run_slack_app_socket_mode, socket_handler=socket_handler)
            print("!!!! RUN SLACK APP SOCKET MODE")
        except:
            pass        

    else:
        print("!!!! DONT RUN SLACK APP")
