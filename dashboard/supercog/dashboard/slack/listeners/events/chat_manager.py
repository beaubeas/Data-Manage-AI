import os
from typing import Any
import json
import time
from logging import Logger
import logging
from uuid import uuid4

import requests
from slack_sdk.web.async_client import AsyncWebClient
from sqlmodel import Session, select, and_
import reflex as rx

from supercog.shared.apubsub import AgentEndEvent, AgentEvent, AgentOutputEvent, EventRegistry, pubsub
from supercog.shared.models import RunLogBase, PERSONAL_INDEX_NAME
from supercog.shared.services import config

from supercog.dashboard.models import Agent, Folder, SlackInstallation, Tenant, User, Tool
from supercog.dashboard.engine_client import EngineClient
from supercog.dashboard.import_export import import_agent_template_from_markdown
from supercog.dashboard.utils import SYSTEM_AGENTS_DIR

from supercog.dashboard.slack.utils.convo_utils import ChannelInfo
from supercog.dashboard.slack.utils.slack_urls import get_slack_install_url

SLACK_SIGNING_SECRET=config.get_global("SLACK_SIGNING_SECRET", required=False) or None

slack_logger = logging.getLogger("slack_app")


class ChatManager:
    # This class manages two mappings:
    #    Slack User --> EngineClient instance with the "supercog user JWT"
    #
    #    Slack convo thread --> Agent Run instance (tied to the right agent)
    #
    # Private convos
    #
    # This is the easy case, where the user has to have installed our Slack app, and we map all
    # convos to the default 'Slack Private Supercog' agent.
    #
    # Public convos
    #
    # This is tricker. If an installed user @ messages Supercog in a public channel, then we map
    # the convo to that user, but use a *shared* agent (tenant global) named after the channel to handle the chat.
    # If anyone else chimes in on that convo thread then they just participate in that Run.
    # 
    # If a non-installed user @ messages Supercog in a public channel, then we map the user "fake supercog user"
    # using their Slack user id as supercog user id "slk-{slack_user_id}". We have to determine the *tenant* by looking
    # for the install user for their Slack team and extracting the tenant, and then we use (or create) that tenant's public channel
    # agent to handle the convo. 
    # 
    # One tricky bit is displaying those "guest" users back on the Dashboard if someone
    # looks at the public agent Run history. Need to review handling of 'AgentInputEvent' in EditorState for that.

    def __init__(self):
        self.agent_clients: dict[str, EngineClient] = {}
        self.runs = {}
        self.user_infos = {} # Slack user Id to user info
        self.sent_ephemeral_message = False

    # This is the entry point method called by our Slack app
    async def call_agent_and_wait(
            self,
            logger: Logger,
            client: AsyncWebClient,
            channel_info: ChannelInfo,
            conversation_id: str,
            slack_user_id: str,
            slack_team_id: str,
            user_message: str,
            files: list[dict] = []
        ):
        self.sent_ephemeral_message = False

        slack_logger.debug(f"Slack call_agent_and_wait, slack user {slack_user_id}, msg: {user_message}, channel: {channel_info}")

        # determine the supercog user and auth
        agentsvc = await self.get_agentsvc(
            logger=logger,
            client=client,
            slack_user_id=slack_user_id,
            slack_team_id=slack_team_id,
            channel_info=channel_info,
            message_id=conversation_id,
        )

        # If no agentsvc, display the default install message
        if agentsvc is None:
            await self.send_install_message(
                client=client,
                slack_user_id=slack_user_id,
                channel_id=channel_info.channel_id,
            )
            return

        if conversation_id in self.runs:
            slack_logger.debug(f"Continue existing Run from convo {conversation_id}")
            run = self.runs[conversation_id]
            if files and len(files) > 0:
                user_message = await self.upload_slack_files_to_s3(
                    agentsvc=agentsvc, 
                    client=client, 
                    files=files, 
                    user_message=user_message,
                    index_files=True,
                    run_id=run['id'],
                )

            async for event in self.wait_for_agent_reply(
                agentsvc,
                run['id'],
                run['logs_channel'],
                user_message,
                slack_user_id,
                client
            ):
                yield event
        else:
            slack_logger.debug(f"Create a new run, lookup the agent first")
            # Lookup agent for this user

            with rx.session() as session:
                agent = await self.find_or_create_agent(
                    agentsvc, 
                    channel_info, 
                    session,
                    client,
                )
                if agent is None:
                    raise RuntimeError(f"No agent created for Slack User {slack_user_id}")
                run = agentsvc.create_run(
                    agentsvc.tenant_id,
                    agentsvc.user_id,
                    agent,
                    logs_channel="logs:" + agent.name[0:15] + uuid4().hex,
                    conversation_id=conversation_id,
                )
                self.runs[conversation_id] = run

                if files and len(files) > 0:
                    user_message = await self.upload_slack_files_to_s3(
                        agentsvc=agentsvc, 
                        client=client, 
                        files=files, 
                        user_message=user_message,
                        index_files=True,
                        run_id=run['id'],
                    )

                async for event in self.wait_for_agent_reply(
                    agentsvc,
                    run['id'],
                    run['logs_channel'],
                    user_message,
                    slack_user_id,
                    client
                ):
                    yield event

    async def wait_for_agent_reply(
            self,
            agentsvc: EngineClient,
            run_id: str,
            reply_channel: str,
            prompt:str,
            slack_user_id :str,
            client: AsyncWebClient,
            timeout=90):

        def capture_event(event: dict) -> str:
            runlog = RunLogBase.model_validate(event)
            agevent: AgentEvent = EventRegistry.get_event(runlog) # type: ignore
            if isinstance(agevent, AgentOutputEvent):
                return agevent.str_result or str(agevent.object_result) # type: ignore
            else:
                return ""

        channel = await pubsub.subscribe(reply_channel) # type: ignore
        start = time.time()
        # NOW send the prompt to the agent after we have created the run and subcribed the logs channel
        # Forward access token to the agent for use in the Slack tool

        agentsvc.send_input(
            run_id,
            prompt,
            run_data={"slackbot_token": client.token, "signing_secret": SLACK_SIGNING_SECRET}
        )

        while time.time() - start < timeout:
            message = await channel.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if message:
                try:
                    event = json.loads(message['data'])
                    runlog = RunLogBase.model_validate(event)
                    agevent: AgentEvent = EventRegistry.get_event(runlog) # type: ignore
                    yield agevent
                    if isinstance(agevent, AgentEndEvent):
                        message = await channel.get_message(ignore_subscribe_messages=True, timeout=0.5)
                        if message is None:
                            await channel.unsubscribe()
                            return
                        else:
                            # Seems like more messages, so keep going
                            event = json.loads(message['data'])
                            yield capture_event(event)
                except Exception as e:
                    # FIXME: Send to rollbar
                    print("BAD Agent event: ", e)

        await channel.unsubscribe()

    async def download_slack_file(self, client: AsyncWebClient, file_info: dict) -> tuple[bytes, str, str]:
        """Download file from Slack"""
        # Get file URL with authentication
        url_private = file_info['url_private']

        headers = {'Authorization': f'Bearer {client.token}'}
        download_response = requests.get(url_private, headers=headers)
        if download_response.ok:
            content = download_response.content
            return (
                content,
                file_info['title'],
                file_info.get('mimetype', 'application/octet-stream')
            )
        else:
            raise Exception(f"Failed to download file: {download_response.status_code}")

    async def upload_slack_files_to_s3(
            self, 
            agentsvc: EngineClient, 
            client: AsyncWebClient, 
            files: list[dict], 
            user_message: str,
            index_files: bool=False,
            run_id: str|None=None,
        ) -> str:
        # FIXME: At a minimum we should be able to use S3 CopyObject to copy from Slack bucket to our bucket. This would work
        # by support "file_upload_by_url" on the Agentsvc.

        # Pass index_files=True to add files to the default RAG index of the Agent which you must specify via
        # run_id.
        for file_info in files:
            try:
                # Download file from Slack
                file_content, filename, content_type = await self.download_slack_file(
                    client, file_info
                )

                # Upload to backend
                await agentsvc.upload_slack_file(
                    "uploads",
                    filename,
                    file_content,
                    content_type,
                    index_file=index_files,
                    run_id=run_id,
                )

                slack_logger.debug(f"Successfully uploaded slack file {filename}")

                # Add the file to the message so the agent knows where to look
                user_message = f"uploaded file: uploads/{filename}\n{user_message}"
            except Exception as e:
                print(f"Error uploading slack file {file_info.get('name')}: {str(e)}")
                continue

        return user_message


    async def get_channel_name(self, client: AsyncWebClient, channel_id: str):
        response = await client.conversations_info(channel=channel_id)
        return response.get("channel", {}).get("name", "??")

    async def get_install_tenant(self, slack_team_id: str|None=None) -> Tenant | None:
        if slack_team_id is None:
            return None
        
        with rx.session() as session:
            tenant: Tenant = session.exec(
                select(Tenant).where(Tenant.slack_team_id == slack_team_id)
            ).first()
            return tenant

    async def get_first_install_user(self, slack_team_id: str|None, session: Session) -> User|None:
        if slack_team_id is None:
            return None
        earliest_installation = session.exec(
            select(
                SlackInstallation).where(SlackInstallation.team_id == slack_team_id
            ).order_by(
                SlackInstallation.installed_at.asc() # type: ignore
            )
        ).first()
        if not earliest_installation:
            return None
            
        # Get the user associated with this installation
        return session.exec(
            select(User).where(User.slack_user_id == earliest_installation.user_id)
        ).first()
    
    async def find_or_create_agent(
            self,
            agentsvc: EngineClient,
            channel_info:  ChannelInfo,
            session: Session,
            client: AsyncWebClient,
        ) -> Agent|None:
        # Find or create the right agent to back a chat in Slack. In private channels the 
        # user_id should be an installed user and the agent will be private to them.
        # For a public channel we will return a shared agent, owned by the Tenant but also by
        # the original installation user, but shared in the Tenant.

        if channel_info.is_public:
            # Find the Tenant for this Slack team
            tenant = await self.get_install_tenant(channel_info.team_id)
            if tenant is None:
                return None # signal no installation

            # We use a Shared agent, named after the Slack channel
            agent_id = Agent.calc_system_agent_id(
                tenant.id,
                None,
                channel_info.channel_id
            )
            agent = session.get(Agent, agent_id)
            if agent is None:
                # place agent in the shared "Slack Channels" folder
                folder = await self.get_shared_channel_folder(tenant.id, session)
                install_user = await self.get_first_install_user(channel_info.team_id, session)
                if install_user is None:
                    return None
                
                # Create the agent. Attribute it to the original install user
                channel_name = channel_info.channel_name
                if not channel_name:
                    channel_name = await self.get_channel_name(client, channel_info.channel_id)

                agent_name = channel_name or channel_info.channel_id

                index = agentsvc.create_doc_index(
                    tenant.id,
                    install_user.id, # so the index is editable by the install owner
                    index_name=agent_name,
                    scope="shared",
                )
                agent = await self._create_slack_agent(
                    agent_id, 
                    tenant.id, 
                    install_user.id, 
                    agent_name,
                    folder.id,
                    index_name=index['name'],
                    index_id=index['id'],
                    session=session,
                    scope="shared",
                )
                # A little strange cause the Agentsvc will have the "fake" Slack credentials, but we are saving an agent
                # to be owned by the install user. Not sure if this will work.
                agentsvc.save_agent(agent)

            return agent
        else:
            agent_id = Agent.calc_system_agent_id(agentsvc.tenant_id, agentsvc.user_id, config.SPECIAL_AGENT_SLACK_PRIVATE)
            slack_logger.debug(f"Looking for Slack agent with id: {agent_id}")
            agent = session.get(Agent, agent_id)
            if agent is None:
                index = agentsvc.create_doc_index(
                    agentsvc.tenant_id,
                    agentsvc.user_id,
                    index_name=PERSONAL_INDEX_NAME,
                    scope="private",
                )
                agent = await self._create_slack_agent(
                    agent_id, 
                    agentsvc.tenant_id, 
                    agentsvc.user_id, 
                    config.SPECIAL_AGENT_SLACK_PRIVATE,
                    None,
                    index_name=index['name'],
                    index_id=index['id'],
                    session=session,
                )
                agentsvc.save_agent(agent)
            return agent

    async def _create_slack_agent(
            self, 
            agent_id, 
            tenant_id, 
            user_id, 
            name, 
            folder_id, 
            index_name,
            index_id,
            session, 
            scope: str = "private"
        ) -> Agent:
        md_path = os.path.join(SYSTEM_AGENTS_DIR, "14_slack_agent.md")
        markdown_agent = open(md_path, "r").read()
        # FIXME: Would be safer to load tool factories from the Agentsvc in case our template
        # adds other tools
        tool_factories = [
            {
            "id" : config.DYNAMIC_TOOLS_AGENT_TOOL_ID,
            "system_name": "Auto Dynamic Tools",
            "logo_url" :"/bolt-icon.png",
            }
        ]
        template = import_agent_template_from_markdown(markdown_agent, tool_factories)
        if template is None:
            raise RuntimeError("Error loading Slack agent template")
        
        agent = Agent(
            id=agent_id,
            name=name,
            tenant_id=tenant_id,
            user_id=user_id,
            folder_id=folder_id,
            # template info
            model=template.model, 
            avatar_url=template.avatar_url,
            system_prompt=template.system_prompt, 
            welcome_message=template.welcome_message,
            max_chat_length=template.max_chat_length,
            input_mode="fit",
            trigger="Chat box",
            updated_at=None,
            scope=scope,
        )
        agent.enable_rag_index(index_name, index_id)
        session.add(agent)
        session.commit()
        session.refresh(agent)
        for tool_dict in template.tools:
            tool = Tool(
                tool_name=tool_dict.name,
                tool_factory_id=tool_dict.tool_factory_id,
                agent_id=agent.id,
                created_at = None,
                credential_id=None,
            )
            session.add(tool)
        session.commit()
        session.refresh(agent) # to get the tools
        return agent


    async def get_shared_channel_folder(self, tenant_id, session) -> Folder:
        slug = Folder.name_to_slug(config.SLACK_PUBLIC_AGENTS_FOLDER)
        slack_folder = Folder.lookup_shared_folder(session, tenant_id, slug)
        if slack_folder is None:
            with rx.session() as session:
                slack_folder = Folder(
                    tenant_id=tenant_id,
                    name=config.SLACK_PUBLIC_AGENTS_FOLDER,
                    slug=slug,
                    scope="shared",
                )
                session.add(slack_folder)
                session.commit()
                session.refresh(slack_folder)
        return slack_folder

    async def send_install_message(
        self,
        client: AsyncWebClient,
        slack_user_id: str,
        channel_id: str,
    ):
        slack_install_url = get_slack_install_url()
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Hello :wave:"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "It looks like you tried to message me but don't have Supercog installed in Slack."
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Install Supercog"
                        },
                        "style": "primary",
                        "value": "install_supercog_slack_app",
                        "url": slack_install_url,
                        "action_id": "install_supercog_slack_app"
                    }
                ]
            }
        ]

        await client.chat_postEphemeral(
            channel=channel_id,
            user=slack_user_id,
            text="It looks like you tried to message me but don't have Supercog installed in Slack. Please install the Supercog Slack app to interact with me.",
            blocks=blocks
        )

        self.sent_ephemeral_message = True

    async def get_slack_user_info(self, slack_user_id: str) -> tuple[Any, Any, Any]:
        slack_user = self.user_infos[slack_user_id]
        slack_email = slack_user.get("user", {}).get("profile", {}).get("email")
        timezone = slack_user.get("user", {}).get("tz")
        name = slack_user.get("user", {}).get("real_name", "")
        return slack_email, name, timezone

    # If there is not user associated with this, grab original message user_id
    async def get_agentsvc(
        self,
        logger: Logger,
        client: AsyncWebClient,
        slack_user_id: str,
        slack_team_id: str,
        channel_info: ChannelInfo,
        message_id: str
    ) -> EngineClient | None:
        slack_user_prefix = "slk"

        existing_agentsvc = self.agent_clients.get(slack_user_id)
        is_guest_user = existing_agentsvc.user_id.startswith(f"{slack_user_prefix}_") if existing_agentsvc is not None else False

        if existing_agentsvc is not None and not is_guest_user:
            return self.agent_clients[slack_user_id]
        
        if is_guest_user:
            # If it is a guest user and an installation exists for that user wipe the agent_clients state for it
            with rx.session() as session:
                slack_installation = session.exec(
                    select(SlackInstallation).where(and_(SlackInstallation.user_id == slack_user_id, SlackInstallation.team_id == slack_team_id))
                ).one_or_none()

                if slack_installation is not None:
                    self.agent_clients.pop(slack_user_id, None)
        
        with rx.session() as session:
            # Add the user info if it does not already exist
            if slack_user_id not in self.user_infos:
                self.user_infos[slack_user_id] = await client.users_info(user=slack_user_id)

            # First find the slack installation for the user_id and team_id
            slack_installation = session.exec(
                select(SlackInstallation).where(and_(SlackInstallation.user_id == slack_user_id, SlackInstallation.team_id == slack_team_id))
            ).one_or_none()

            # If there is no slack installation, find the one for the original message
            if slack_installation is None:
                original_message_result = await client.conversations_history(
                    channel=channel_info.channel_id,
                    inclusive=True,
                    oldest=message_id,
                    limit=1
                )

                original_message = original_message_result.get("messages", [])
                if len(original_message) != 1:
                    logger.error(f"Could not find slack message with ts {message_id}")
                    return

                original_user_id = original_message[0].get("user")
                if not original_user_id:
                    logger.error(f"Could not find slack user for message with ts {message_id}")
                    return

                slack_installation = session.exec(
                    select(SlackInstallation).where(and_(SlackInstallation.user_id == original_user_id, SlackInstallation.team_id == slack_team_id))
                ).one_or_none()

            if slack_installation is not None:
                if slack_installation.user_id in self.agent_clients:
                    # Use the original message's user's agent so a run can be continued
                    return self.agent_clients[slack_installation.user_id]
                else:
                    # Create a new agentsvc with the slack installation's user
                    user = session.exec(
                        select(User).where(User.slack_user_id == slack_installation.user_id)
                    ).one_or_none()

                    # Find the tenant associated with this slack team
                    tenant = session.exec(
                        select(Tenant).where(Tenant.slack_team_id == slack_installation.team_id)
                    ).one_or_none()

                    if user is None or tenant is None:
                        logger.error(f"Could not find slack user or tenant for slack user {slack_installation.user_id} and slack team {slack_installation.team_id}")
                        return

                    agentsvc = EngineClient()
                    slack_email, name, timezone = await self.get_slack_user_info(slack_user_id)

                    agentsvc.user_login(
                        tenant.id,
                        user.id,
                        name = name,
                        user_email=slack_email or user.emailval,
                        timezone=timezone
                    )

                    self.agent_clients[slack_user_id] = agentsvc
                    return agentsvc
            else:
                # This is the case of a non-installed user messaging the agent. We allow it as long
                # _someone_ has installed the app. In that case we generate a "fake user" for the Slack
                # user to interact with the agent.
                agentsvc = EngineClient()
                # Add the user email if it exists
                slack_email, name, timezone = await self.get_slack_user_info(slack_user_id)
                # Find the Tenant for this Slack team
                tenant = await self.get_install_tenant(slack_team_id)
                if tenant is None:
                    return None # will signal to user to install the app

                agentsvc.user_login(
                    tenant.id,
                    f"{slack_user_prefix}_{slack_user_id}",
                    name = name,
                    user_email=slack_email,
                    timezone=timezone
                )
                self.agent_clients[slack_user_id] = agentsvc
                return agentsvc


