from contextlib import contextmanager
from supercog.engine.tool_factory import ToolFactory, ToolCategory
import re
from datetime import datetime
import os
from urllib.parse import urlparse

import httpx

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_sdk.errors import SlackApiError

from supercog.shared.services import config
from supercog.shared.logging import logger
from supercog.engine.triggerable import Triggerable

from typing import Any, Callable


class SlackTool(ToolFactory):
    _user_map = {}

    def __init__(self, **kwargs):
        if kwargs:
            super().__init__(**kwargs)
        else:
            super().__init__(
                id = "slack_connector",
                system_name = "Slack",
                logo_url=super().logo_from_domain("slack.com"),
                category=ToolCategory.CATEGORY_SAAS,
                auth_config = {
                    "strategy_token": {
                        "slackbot_token": "The token for your Slack Bot",
                        "signing_secret": "The signing secret",
                        "help": "help markdown",
                    }
                },
                help="""
    Send messages to Slack, and read messages from Slack channels. [Docs](https://github.com/supercog-ai/community/wiki/Tool-Library-Docs#slack-tool)
    """,
            )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.send_slack_message,
            self.list_slack_channels,
            self.fetch_slack_messages,
            self.list_slack_users,
        ])

    @contextmanager
    def get_app(self):
        try:
            from slack_bolt import App
            from slack_sdk.errors import SlackApiError
        except ImportError:
            raise RuntimeError("Slack packages are not installed.")
        app = App(
            token=self.credentials.get("slackbot_token"),
            signing_secret=self.credentials.get("signing_secret")
        )
        yield app

    def get_channel_id_by_name(self, app, channel_name):
        # Call the conversations.list method using the WebClient
        response = app.client.conversations_list(
            exclude_archived=True,
            types="public_channel,private_channel"
        )
        channels = response['channels']
        
        for channel in channels:
            if channel['name'] == channel_name:
                return channel['id']
        
        return None

    async def send_slack_message(
        self,
        channel_name: str,
        message: str,
        audio_link: str = "",
    ) -> dict:
        """
        Sends a message to the indicated Slack channel.

        Args:
            channel_name (str): The name of the Slack channel to send the message to.
            message (str): The message to be sent.

        Returns:
            dict: A dictionary containing the status of the operation and a message.
        """
        with self.get_app() as app:
            if channel_name.startswith("#"):
                channel_name = channel_name[1:]

            channel_id = None
            try:
                # Call the conversations.list method using the WebClient
                for result in app.client.conversations_list():
                    for channel in result["channels"]:
                        if channel["name"] == channel_name:
                            channel_id = channel["id"]
                            print(f"Found channel ID: {channel_id}")
                            break
                    if channel_id:
                        break

                if channel_id is None:
                    return {"status": "error", "message": f"Slack channel '{channel_name}' not found."}

                blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": message + f"\nfrom _Supercog_"
                        },
                    },
                ]

                if audio_link:
                    response = await self._post_file_to_slack(app, channel_id, audio_link, comment=message)
                else:
                    # Send the message using chat_postMessage
                    response = app.client.chat_postMessage(
                        channel=channel_id,
                        text=message,
                        blocks=blocks
                    )

                if response["ok"]:
                    return {"status": "success", "message": "Message sent."}
                else:
                    return {"status": "error", "message": f"Failed to send message: {response.get('error', 'Unknown error')}"}

            except SlackApiError as e:
                return {"status": "error", "message": f"Slack API error: {str(e)}"}
        

    async def _post_file_to_slack(self, slack_app, channel_id, file_url, comment="") -> dict:
        # Use urlparse to extact file name from the URL
        parsed_url = urlparse(file_url)
        local_file = os.path.basename(parsed_url.path)
        # Gotta download the file first, using async httpx
        client = httpx.AsyncClient()
        with open(local_file, 'wb') as f:
            async with client.stream('GET', file_url) as response:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
        result = slack_app.client.files_upload_v2(
            channel=channel_id,
            initial_comment=comment,
            file=local_file,
        )
        # delete the local file
        os.remove(local_file)
        return result

    def list_slack_channels(self, match_name: str="") -> list[str]:
        """ Return all channels from Slack, or channels matching the 'match_name' parameter. """

        with self.get_app() as app:
            response = app.client.conversations_list(
                exclude_archived=True,
                types="public_channel,private_channel"
            )
            channels = response['channels']
            
            # Filter channels by the query
            matched_channels = [channel for channel in channels if match_name.lower() in channel['name'].lower()]
            return matched_channels

    def fetch_slack_messages(self, channel_name: str, count: int=10):
        """ Returns the most recent 'count' number of messages from the indicated channel. """
        with self.get_app() as app:
            channel_id = self.get_channel_id_by_name(app, channel_name)
            if not channel_id:
                return {"error": f"Channel not found '{channel_name}'"}

            try:
                # Call the conversations.history method using the WebClient
                response = app.client.conversations_join(channel=channel_id)
                if not response['ok']:
                    return f"Failed to join channel {channel_name}: {response['error']}"
                response = app.client.conversations_history(
                    channel=channel_id,
                    limit=count
                )
                messages = [
                    {
                        'user_id': msg['user'],
                        'user': self._lookup_user(msg['user']),
                        'text': self._substitute_user_names(msg['text']),
                        # Parse the timestamp to a human-readable format
                        'time': datetime.fromtimestamp(float(msg['ts'])).strftime('%Y-%m-%d %H:%M:%S'),
                        'bot_id': msg.get('bot_id'),
                        'blocks': self._substitute_user_names(str(msg.get('blocks'))),
                    } 
                    for msg in response['messages']
                ]
                # resolve users
                
                return messages
            
            except SlackApiError as e:
                return f"Error fetching messages: {e.response['error']}"
            
    def _lookup_user(self, user_id):
        if self._user_map == {}:
            self._user_map = {u['id']: u['name'] for u in self.list_slack_users()}

        return self._user_map.get(user_id, user_id)

    def _substitute_user_names(self, message: str):
        # Replace user IDs with user names
        for user_id in re.findall(r"<@(U[A-Z0-9]+)>", message):
            user_name = self._lookup_user(user_id)
            message = message.replace(f"<@{user_id}>", f"@{user_name}")
        return message

    def list_slack_users(self, match_name: str = "") -> list[dict]:
        """
        Return all users from Slack, or users matching the 'match_name' parameter.
        """
        with self.get_app() as app:
            try:
                users = []
                cursor = None
                while True:
                    response = app.client.users_list(limit=1000, cursor=cursor)
                    users.extend(response['members'])
                    cursor = response.get('response_metadata', {}).get('next_cursor')
                    if not cursor:
                        break

                # Filter users by the query
                if match_name:
                    matched_users = [
                        user for user in users
                        if match_name.lower() in user.get('name', '').lower() or
                        match_name.lower() in user.get('real_name', '').lower()
                    ]
                else:
                    matched_users = users

                # Return relevant user information
                return [
                    {
                        'id': user['id'],
                        'name': user['name'],
                        'real_name': user.get('real_name'),
                        'email': user.get('profile', {}).get('email'),
                        'is_bot': user['is_bot'],
                    }
                    for user in matched_users
                ]

            except SlackApiError as e:
                logger.error(f"Error fetching Slack users: {e}")
                return []

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """
        from slack_bolt import App

        try:
            app = App(
                token=secrets.get("slackbot_token"),
                signing_secret=secrets.get("signing_secret")
            )

            # Call the auth.test method to test the credentials
            response = app.client.auth_test()

            if response["ok"]:
                print("Connection tested OK!")
                return None
            else:
                return f"Failed to authenticate with Slack: {response['error']}"

        except SlackApiError as e:
            return f"Error testing Slack credentials: {e}"

        except Exception as e:
            return str(e)


TRIGGER_WORDS: dict[str, "SlackTriggerable"] = {}

class SlackTriggerable(Triggerable):
    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        return trigger.startswith("Slack")
    
    def __init__(self, agent_dict: dict, run_state) -> None:
        super().__init__(agent_dict, run_state)
        self.agent_dict = agent_dict
        print(f"[{self.agent_dict['name']}] >> SLACK TRIGGER: keyword: ", 
              self.agent_dict['trigger_arg'])
        TRIGGER_WORDS[agent_dict['trigger_arg']] = self

class SlackHandler:
    def __init__(self) -> None:
        self.app = AsyncApp(token=config.get_global("SLACK_BOT_TOKEN"))
        #self.app.event("app_mention")(self.handle_mention)
        self.app.event("message")(self.message)
        self.convo_thread_id = None
        self.thread_runs = {}

    def sent_to_us(self, message: dict, auth) -> bool:
        for user_id in re.findall(r"<@(U[A-Z0-9]+)>", message['text']):
            if user_id == auth['user_id']:
                return True
        else:
            return False

    def determine_agent(self, message: str) -> SlackTriggerable | None:
        print(f"Checking message '{message}' against keywords: ", TRIGGER_WORDS.keys())
        for keywords in TRIGGER_WORDS.keys():
            if keywords in message:
                return TRIGGER_WORDS[keywords]
        return None
    
    async def message(self, message, say):
        auth = await self.app.client.auth_test()
        print(message)
        print(TRIGGER_WORDS)
        if self.sent_to_us(message, auth) or message.get('thread_ts') in self.thread_runs:
            run = None
            if message.get('thread_ts') in self.thread_runs:
                run = self.thread_runs[message['thread_ts']]
                triggerable = run['_triggerable']
            else:
                triggerable = self.determine_agent(message['text'])
                # don't pass the trigger message to the agent
                message['text'] = 'start'
            if triggerable is None:
                say("Sorry. I don't recognize any agent listening for those words")
                return

            convo_thread_id = message.get('thread_ts', message.get('ts'))
            channel_id = message['channel']

            respond_msg = await say(thread_ts = convo_thread_id, text="thinking...")
            msg_ts = respond_msg['ts']
            if run is None:
                run = triggerable.create_run(message['text'])
                run["_triggerable"] = triggerable
                run["slack_thread_id"] = convo_thread_id
                self.thread_runs[convo_thread_id] = run
            else:
                triggerable.continue_run(run['id'], message['text'])
            full_reply = ""
            async for reply in triggerable.wait_for_agent_reply(run['logs_channel']):
                reply = reply.replace("\n", " ")
                full_reply += reply
                print("Sending update to slack: ", full_reply)
                await self.app.client.chat_update(                    
                    channel=channel_id,
                    ts=msg_ts,
                    text=full_reply, 
                    replace_original=True,
                )

# Simple subclass of our traditional Slack Tool that expects auth config to be
# provided dynamically from the Dashboard side Slack app via 'run_data' in the
# agent call.
class SlackAppSlackTool(SlackTool):
    def __init__(self):
        super().__init__(
            id = "slack_app_slack_tool",
            system_name = "Slack Tool",
            logo_url=super().logo_from_domain("slack.com"),
            category=ToolCategory.CATEGORY_SAAS,
            auth_config = { },
            help="""
Send messages to Slack, and read messages from Slack channels.
""",
        )

    @contextmanager
    def get_app(self):
        self.credentials["slackbot_token"] = self.run_context.get_env_var("slackbot_token") 
        self.credentials["signing_secret"] = self.run_context.get_env_var("signing_secret") 
        with super().get_app() as app:
            yield app

# Must call this from the main event handler (look in TriggerService)
async def run_slack_app():
    slack_handler = SlackHandler()
    handler = AsyncSocketModeHandler(slack_handler.app, config.get_global("SLACK_APP_TOKEN"))
    await handler.start_async()
