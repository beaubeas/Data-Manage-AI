import reflex as rx
from sqlmodel import select, or_, and_

from slack_sdk.web.async_client import AsyncWebClient

from supercog.dashboard.slack.app import slack_oauth_callback
from supercog.dashboard.slack.utils.slack_urls import get_slack_install_url, get_slack_deep_link_url

from supercog.shared.logging import logger

from .models import SlackInstallation, Tenant, TenantMember, User
from .global_state import GlobalState

class SlackState(GlobalState):
    finished_installing_slack: bool
    slack_error: str

    @rx.var
    def slack_code(self) -> str:
        return self.router.page.params.get("code", "")
    
    def on_page_load(self):
        self.finished_installing_slack = False
        self.slack_error = ""
        
        yield SlackState.attempt_slack_install()

    def finish_install(self):
        self.finished_installing_slack = True

    def call_install_slack(self):
        return rx.redirect(get_slack_install_url())
    
    def call_deep_link_to_slack(self):
        return rx.redirect(get_slack_deep_link_url())
    
    @rx.background
    async def attempt_slack_install(self):
        if not self.slack_code:
            return

        if not self.is_hydrated:
            return
        
        response = await slack_oauth_callback(self.slack_code)

        if "result" not in response or response["result"] != "success":
            logger.info("Unable to install Slack: Slack authentication failed (likely stale query param code)")
            async with self:
                self.slack_error = "Unable to authenticate with Slack."
            return [GlobalState.remove_query_params]
        
        # Get the slack installation that was just created and the tenant for the team id if it exists
        slack_installation: SlackInstallation | None = None
        slack_team_id: str | None = None
        tenant: Tenant | None = None
        try:
            with rx.session() as session:
                slack_installation = session.exec(
                    select(SlackInstallation).where(and_(SlackInstallation.user_id == response["slack_user_id"], SlackInstallation.team_id == response["slack_team_id"]))
                ).one_or_none()

                if slack_installation is None:
                    logger.error(f"Unable to install Slack: no slack installation found with slack user id {response['slack_user_id']} and slack team id {response['slack_team_id']}")
                    async with self:
                        self.slack_error = "No record of Slack installation found."
                    return [GlobalState.remove_query_params]

                # Set the slack_team_id for use in the redirect later
                slack_team_id = slack_installation.team_id

                tenant = session.exec(
                    select(Tenant).where(Tenant.slack_team_id == slack_installation.team_id)
                ).one_or_none()

                supercog_user_id = self.user_id if self.is_authenticated else None
                supercog_user = None
                # If no supercog_user_id look up the user email for the install
                if not supercog_user_id:
                    slack_client = AsyncWebClient(token=slack_installation.bot_token)
                    slack_user_response = await slack_client.users_info(user=slack_installation.user_id)
                    slack_user_email = slack_user_response.get("user", {}).get("profile", {}).get("email")
                    slack_user_name = slack_user_response.get("user", {}).get("profile", {}).get("real_name")

                    supercog_user = session.exec(
                        select(User).where(or_(User.email == slack_user_email, User.gtoken_email == slack_user_email))
                    ).one_or_none()

                    # If there still is no user, create one
                    if supercog_user is None:
                        supercog_user = User(
                            email=slack_user_email,
                            name=slack_user_name,
                            enabled=True,
                            tenant_id="notset",
                        )
                        session.add(supercog_user)
                        session.commit()
                        session.refresh(supercog_user)
                        supercog_user_id = supercog_user.id
                else:
                    supercog_user = session.exec(
                        select(User).where(User.id == self.user_id)
                    ).one_or_none()

                if supercog_user is None:
                    logger.error(f"Unable to install Slack: Supercog user was unable to be found or created")
                    async with self:
                        self.slack_error = "No Supercog user found."
                    return [GlobalState.remove_query_params]

                supercog_user_id = supercog_user.id
                
                if tenant is None:
                    # Get the name of the slack team
                    slack_client = AsyncWebClient(token=slack_installation.bot_token)
                    slack_team_response = await slack_client.team_info(team=slack_installation.team_id)
                    slack_team_name = slack_team_response.get("team", {}).get("name") or supercog_user.username
                    tenant = Tenant(
                        domain=supercog_user.email_domain,
                        name=f"{slack_team_name} Slack Org"
                    )
                    session.add(tenant)
                    session.commit()
                    session.refresh(tenant)

                # We should now have a supercog user, tenant, and slack installation. Connect them
                if tenant is not None:
                    supercog_user.slack_user_id = slack_installation.user_id
                    supercog_user.tenant_id = tenant.id
                    tenant.slack_team_id = slack_installation.team_id
                    tenant_member = tenant.lookup_membership(supercog_user.id)
                    if tenant_member is None:
                        # Set to owner if no other tenant members, otherwise set to member
                        role = "owner" if len(tenant.tenant_members) == 0 else "member"
                        tenant_member = TenantMember(
                            tenant_id=tenant.id,
                            user_id=supercog_user.id,
                            role=role
                        )
                    session.add(supercog_user)
                    session.add(tenant)
                    session.add(tenant_member)
                    session.commit()
                    session.refresh(supercog_user)
                    session.refresh(tenant)
                else:
                    logger.error(f"Unable to install Slack: Supercog tenant was unable to be found or created")
                    async with self:
                        self.slack_error = "No Supercog tenant found."
                    return [GlobalState.remove_query_params]
        
            logger.info(f"Installed Slack for user {supercog_user_id}")

            return [rx.redirect(get_slack_deep_link_url(slack_team_id)), SlackState.finish_install()]
        except Exception as e:
            logger.error(f"Unable to install Slack: Exception occured {e}")
            async with self:
                self.slack_error = "An unexpected error occured."
            return [GlobalState.remove_query_params]

