import json
import requests
from typing import Callable, Dict, Any

from supercog.engine.tool_factory import ToolFactory, ToolCategory

class DiscordTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="discord",
            system_name="Discord",
            logo_url="https://logo.clearbit.com/discord.com",
            auth_config={
				"strategy_token": {
					"webhook_url": "Discord channel webhook URL",
					"help": (
						"To create a Discord webhook URL, follow these steps:\n"
						"1. Go to the channel settings in Discord.\n"
						"2. Click on 'Integrations'.\n"
						"3. Click on 'Create Webhook'.\n"
						"4. Copy the webhook URL and paste it here."
					)
				}
            },
            category=ToolCategory.CATEGORY_SAAS,
            help="""
Send rich messages to a Discord channel using webhooks.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.send_message,
            self.send_message_with_embed,
        ])

    def _discord_request(self, webhook_url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper method to make Discord webhook requests.
        """
        headers = {"Content-Type": "application/json"}
        response = requests.post(webhook_url, data=json.dumps(data), headers=headers)
        if response.status_code == 204:
            return {"status": "success", "message": "Message sent successfully"}
        else:
            return {"status": "error", "message": f"Failed to send message. Status code: {response.status_code}"}

    def send_message(self, message: str, color_hex: str = "FFDDAA") -> Dict[str, Any]:
        """
        Send a message to Discord.
        """
        webhook_url = self.credentials['webhook_url']

        # Convert hex color to decimal
        color_decimal = int(color_hex, 16)

        data = {
            "content": f"\nfrom _Supercog_",
            "embeds": [{
                "title": f"From: {self.run_context.agent_name}",
                "description": message,
                "color": color_decimal
            }]
        }
        return self._discord_request(webhook_url, data)
    
    def send_message_with_embed(self, message: str, embed_title: str, embed_description: str, 
                                embed_color_hex: str = "FFDDAA") -> Dict[str, Any]:
        """
        Send a message with an embed to Discord.
        :param message: The message to send
        :param embed_title: The title of the embed
        :param embed_description: The description of the embed
        :param embed_color: The color of the embed (default: green)
        :return: Status of the operation
        """
        webhook_url = self.credentials['webhook_url']

        # Convert hex color to decimal
        color_decimal = int(embed_color_hex, 16)

        data = {
            "content": message + f"\nfrom _Supercog_",
            "embeds": [{
                "title": embed_title,
                "description": embed_description,
                "color": color_decimal
            }]
        }
        return self._discord_request(webhook_url, data)

    def test_credential(self, cred, secrets: dict) -> str:
        """
        Test that the given credential secrets are valid.
        Return None if OK, otherwise return an error message.
        """
        try:
            webhook_url = secrets.get("webhook_url")
            if not webhook_url:
                return "Webhook URL is missing"

            test_message = "This is a test message from Supercog"
            data = {
                "content": test_message
            }
            response = self._discord_request(webhook_url, data)
            
            if response["status"] == "success":
                return None
            else:
                return f"Invalid Discord webhook URL. Error: {response['message']}"

        except Exception as e:
            return str(e)