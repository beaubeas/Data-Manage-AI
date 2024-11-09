from typing import Optional
from slack_sdk.oauth import AuthorizeUrlGenerator

from supercog.shared.services import config

SLACK_SCOPES=[
    "app_mentions:read",
    "assistant:write",
    "channels:history",
    "channels:read",
    "chat:write",
    "chat:write.customize",
    "chat:write.public",
    "commands",
    "files:read",
    "files:write",
    "groups:history",
    "groups:read",
    "im:history",
    "im:read",
    "links.embed:write",
    "links:read",
    "links:write",
    "team:read",
    "users:read",
    "users:read.email",
]

def get_slack_install_url():
    SLACK_CLIENT_ID=config.get_global("SLACK_CLIENT_ID", required=False) or None
    SLACK_REDIRECT_URL=config.get_global("SLACK_REDIRECT_URL", required=False) or None

    if not SLACK_CLIENT_ID or not SLACK_REDIRECT_URL:
        return ""
    
    authorize_url_generator = AuthorizeUrlGenerator(
        client_id=SLACK_CLIENT_ID,
        scopes=SLACK_SCOPES,
        user_scopes=[],
        redirect_uri=SLACK_REDIRECT_URL
    )

    return authorize_url_generator.generate("")

def get_slack_deep_link_url(team_id: Optional[str] = None):
    SLACK_APP_ID=config.get_global("SLACK_APP_ID", required=False) or None

    if not SLACK_APP_ID:
        return ""
    
    team_id_query_param = f"&team={team_id}" if team_id else ""

    return f"https://slack.com/app_redirect?app={SLACK_APP_ID}{team_id_query_param}"
    
