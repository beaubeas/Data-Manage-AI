from typing import Any, Coroutine
from sqlmodel import select, Session, and_

from slack_sdk.oauth.installation_store.async_installation_store import AsyncInstallationStore, Installation

from supercog.dashboard.models import SlackInstallation
from supercog.shared.services import db_connect

class SupercogInstallationStore(AsyncInstallationStore):
    async def async_save(self, installation: Installation):
        with Session(db_connect("dashboard")) as sess:
            existing_installation = sess.exec(
                select(SlackInstallation).where(and_(SlackInstallation.user_id == installation.user_id, SlackInstallation.team_id == installation.team_id))
            ).one_or_none()

            if existing_installation:
                existing_installation.update_from_slack_installation(installation)
            else:
                existing_installation = SlackInstallation.from_slack_installation(installation)
                
            sess.add(existing_installation)
            sess.commit()
        
    
    async def async_find_installation(
        self,
        *,
        enterprise_id: str | None,
        team_id: str | None,
        user_id: str | None = None,
        is_enterprise_install: bool | None = False
    ) -> Coroutine[Any, Any, Installation | None]:
        result = None
        with Session(db_connect("dashboard")) as sess:
            if is_enterprise_install and enterprise_id:
                result = sess.exec(
                    select(SlackInstallation).where(SlackInstallation.enterprise_id == enterprise_id)
                ).one_or_none()
            elif user_id and team_id:
                result = sess.exec(
                    select(SlackInstallation).where(and_(SlackInstallation.user_id == user_id, SlackInstallation.team_id == team_id))
                ).one_or_none()
            elif team_id:
                # Grab the most recent install: https://tools.slack.dev/python-slack-sdk/api-docs/slack_sdk/oauth/installation_store/async_installation_store.html
                # "If the user_id is absent, this method may return the latest installation in the workspace / org.""
                result = sess.exec(
                    select(SlackInstallation).where(SlackInstallation.team_id == team_id).order_by(SlackInstallation.installed_at.desc())
                ).first()
    
        if result is not None:
            return result.to_slack_installation()
        
        return None
        
