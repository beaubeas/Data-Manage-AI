import base64
from typing import Optional
import json
from fastapi import Request
from pydantic import BaseModel, Field

from email import message_from_bytes
from bs4 import BeautifulSoup

from supercog.engine.triggerable import Triggerable

class SNSNotification(BaseModel):
    Type: Optional[str] = Field(None)
    MessageId: Optional[str] = Field(None)
    TopicArn: Optional[str] = Field(None)
    Message: Optional[str] = Field(None)  # This will be a JSON string
    Timestamp: Optional[str] = Field(None)
    SignatureVersion: Optional[str] = Field(None)
    Signature: Optional[str] = Field(None)
    SigningCertURL: Optional[str] = Field(None)
    UnsubscribeURL: Optional[str] = Field(None)
    SubscribeURL: Optional[str] = Field(None, description="URL to confirm subscription (only in SubscriptionConfirmation messages)")
    Token: Optional[str] = Field(None, description="Token used for confirming subscriptions (only in SubscriptionConfirmation messages)")

# A Triggerable based on SNS notifications (currently just email)
class SNSTriggerable(Triggerable):
    def __init__(self, agent_dict: dict, run_state) -> None:
        super().__init__(agent_dict, run_state)
        self.run_state = run_state
        print("Waiting for SNS notification trigger for agent slug: ", self.agent_slug)

    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        return trigger.startswith("Email")

    def pick_credential(self, credentials: list) -> bool:
        return True #No credentials needed

    @classmethod
    async def parse_sns_notification(cls, request: Request) -> dict:
        data = await request.json()
        notification = SNSNotification.model_validate(data)
        
        # Handle subscription confirmation
        if notification.Type == 'SubscriptionConfirmation':
            # Here you might want to actually visit the SubscribeURL provided by SNS to confirm the subscription
            # For security purposes, ensure the request is coming from SNS
            print("Confirm subscription URL: ", notification.SubscribeURL)
            # You might use an HTTP client to GET the SubscribeURL
            return {}
        
        # Handle notification
        elif notification.Type == "Notification":
            # Process the notification message as needed
            message = json.loads(notification.Message or "{}")

            # Extract email headers and content
            headers = message['mail']['commonHeaders']
            subject = headers['subject']
            to_addresses = headers['to']  # This will be a list of email addresses
            from_address = headers['from'][0]

            # Optional: Extract other parts of the email
            # If the full content is also sent, you may have additional fields to decode

            agent_email = to_addresses[0]
            agent_slug = agent_email.split('@')[0]
            print("Address to slug: ", agent_slug)
            content = message['content']
            decoded_bytes = base64.b64decode(content)
            decoded_content = decoded_bytes.decode('utf-8') 
            print("Decoded message:\n", decoded_content)
            mime_message = message_from_bytes(decoded_bytes)
                
            html_content = ""

            if mime_message.is_multipart():
                for part in mime_message.walk():
                    # Check if the content type is HTML
                    if part.get_content_type() == 'text/html':
                        html_content = part.get_payload(decode=True).decode(part.get_content_charset())
                        break

            soup = BeautifulSoup(html_content, 'html.parser')
            plain_text = soup.get_text(separator=' ', strip=True)

            email_msg = f"""
    Subject: {subject}
    From: {from_address}
    To: {agent_email}
    Message:\n{plain_text}\n------
    """
            return {"agent_slug": agent_slug, "email_msg": email_msg}
        else:
            return {"error": f"Unknown SNS message type: {notification.Type}"}
