from typing import List, Dict
from logging import Logger

from slack_bolt.async_app import AsyncBoltContext
from slack_sdk.web.async_client import AsyncWebClient

async def respond_to_url_verification(
    payload: dict,
    logger: Logger,
):
    if not "challenge" in payload:
        logger.exception("No challenge in payload for url_verification")
        return
    
    challenge = payload["challenge"]

    return {"challenge": challenge}
