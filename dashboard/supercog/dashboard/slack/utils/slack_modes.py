from supercog.shared.services import config

def is_events_mode() -> bool:
    SLACK_CLIENT_ID=config.get_global("SLACK_CLIENT_ID", required=False) or None
    SLACK_CLIENT_SECRET=config.get_global("SLACK_CLIENT_SECRET", required=False) or None
    SLACK_SIGNING_SECRET=config.get_global("SLACK_SIGNING_SECRET", required=False) or None
    SLACK_REDIRECT_URL=config.get_global("SLACK_REDIRECT_URL", required=False) or None

    return bool(SLACK_CLIENT_SECRET) and bool(SLACK_CLIENT_ID) and bool(SLACK_SIGNING_SECRET) and bool(SLACK_REDIRECT_URL)

def is_socket_mode() -> bool:
    if is_events_mode():
        return False
    
    SLACK_AI_BOT_TOKEN=config.get_global("SLACK_AI_BOT_TOKEN", required=False) or None
    SLACK_AI_APP_TOKEN=config.get_global("SLACK_AI_APP_TOKEN", required=False) or None

    return bool(SLACK_AI_BOT_TOKEN) and bool(SLACK_AI_APP_TOKEN)

def slack_disabled() -> bool:
    return not is_events_mode() and not is_socket_mode()