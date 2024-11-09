import json
import time
import requests
from typing import Callable, Any, Optional
from supercog.engine.tool_factory import ToolFactory, ToolCategory

from google.oauth2.credentials import Credentials as GoogleOauth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import google_auth_oauthlib.helpers
import google.auth.exceptions
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from google.auth.exceptions import RefreshError

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

from simplegmail import Gmail
from simplegmail.message import Message

from .utils import markdown_to_html
from supercog.shared.utils import Colors
from supercog.shared.services import config
from supercog.shared.logging import logger

from bs4 import BeautifulSoup

# If modifying these scopes, delete the file token.json.
#SCOPES = ['https://www.googleapis.com/auth/gmail.send']
#SCOPES = config.get_global("GSUITE_SCOPES").split(",")
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

class SimplerGmail(Gmail):
    def __init__(self, service):
        self._service = service
        self.creds = {}

    @property
    def service(self):
        return self._service

    def parse_messages(self, message_refs: list) -> list[Message]:
        return self._get_messages_from_refs("me", message_refs, parallel=False)

class GAuthCommon:
    def get_scopes(self) -> list[str]:
        raise RuntimeError("Subclass must provide SCOPES")
    
    def get_oauth_client_id_and_secret(self) -> tuple[str|None, str|None]:
        return config.get_global("GSUITE_CLIENT_ID"), config.get_global("GSUITE_CLIENT_SECRET")
        
    def prepare_creds(self, cred, secrets: dict) -> dict:
        # Attempt to refresh our GSuite access token if it looks expired
        logger.info(f"Refreshing GSuite OAuth tokens for credential '{cred.name}', user: {cred.user_id}")

        old_tokens = json.loads(secrets["tokens"])
        tokens: GoogleOauth2Credentials = GAuthCommon.setup_credentials(
            old_tokens, self.get_scopes(),
            self.get_oauth_client_id_and_secret(),
        )
        if tokens.expired and tokens.refresh_token:
            try: 
                tokens.refresh(GoogleAuthRequest())
                # We are using this in the Dashboard but this version uses the toke's built-in
                # 'refresh' method.
                old_tokens['expires_at'] = time.mktime(tokens.expiry.timetuple())
                old_tokens['access_token'] = tokens.token

                secrets["tokens"] = json.dumps(old_tokens)
                cred.stuff_secrets(json.dumps(secrets)) # this saves the new values
            except google.auth.exceptions.RefreshError as e:
                # Our credential including refresh token is bad
                raise RuntimeError(f"Can't refresh GMail API token: {e}")

        return secrets        

    @staticmethod
    def setup_credentials(tokens: dict, scopes: list[str],
                          client_id_and_secret: tuple[str|None,str|None]) -> GoogleOauth2Credentials:
        # Ok, we are jumping through a bunch of hoops to avoid using Google's custom
        # 'creds.json' config file, for better or worse. Instead you only need to 
        # set GSUITE_CLIENT_ID and GSUITE_CLIENT_SECRET in the global config.
        # During Connection creation we will run the User through the Oauth2 flow
        # and save their tokens in the Connection credentials. Those values will
        # be pass to our tool in the `crds_pk` dict.
        #
        # We do some magic-fu to wrangle the static settings and the user tokens
        # into a usable `google.oauth2.credentials.Credentials` object and then
        # build our Gmail service with that.
        #
        # The 'prepare_creds' method will be called before our Agent is launched
        # and that is our opportunity to refresh our credentials if they are expired.
        client_config = {
            "web": {
                "client_id": client_id_and_secret[0],
                "client_secret": client_id_and_secret[1],
                "redirect_uris": ["http://localhost:3000/"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://accounts.google.com/o/oauth2/token"
            }
        }
        print("Using scopes: ", scopes)
        session, _ = google_auth_oauthlib.helpers.session_from_client_config(
            client_config, scopes
        )
        # Some cross-lib funkiness that expects expires_at to be an int instead of float
        if 'expires_at' in tokens:
            tokens['expires_at'] = int(float(tokens['expires_at']))
        session.token = tokens
        real_creds: GoogleOauth2Credentials = google_auth_oauthlib.helpers.credentials_from_session(
            session, client_config["web"]
        )
        return real_creds


class GmailAPITool(ToolFactory, GAuthCommon):
    def __init__(self):
        super().__init__(
            id = "gmailapi_connector",
            system_name = "GmailAPI",
            logo_url=super().logo_from_domain("google.com"),
            category=ToolCategory.CATEGORY_EMAIL,
            auth_config = {
                "strategy_oauth": {
                    "help": """
Login to Google to connect your account.
"""
                }
            },
            oauth_scopes=SCOPES,
        )

    def get_scopes(self) -> list[str]:
        return SCOPES

    def get_oauth_client_id_and_secret(self) -> tuple[str|None, str|None]:
        return config.get_global("GMAIL_CLIENT_ID"), config.get_global("GMAIL_CLIENT_SECRET")
    
    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.send_email,
            self.search_for_emails,
            self.get_email_details,
        ])
    
    def search_for_emails(self, q: str, number_of_results: int = 10) -> str:
        """ Searches for email messages. Provide the GMail API advanced search syntax in the 'q' parameter. """
        try:
            # Build our 'service' client with our auth tokens
            service = self.get_service()
            gmail = SimplerGmail(service)
            Colors.printc("Got gmail connected", Colors.BRIGHT_YELLOW)

            r = service.users().messages().list(
                userId='me', 
                q=q,
                maxResults=number_of_results
            ).execute()
            #Colors.printc("Got messages", Colors.BRIGHT_YELLOW)

            message_refs = r.get('messages', [])
            msgs: list[Message] = gmail.parse_messages(message_refs)
            #Colors.printc("Parsed messages", Colors.BRIGHT_YELLOW)

            answer = ""
            for msg in msgs:
                answer += msg.date + "\n"
                answer += f"From: {msg.sender}\n"
                answer += f"Subject: {msg.subject}\n"
                answer += f"Snippet: {msg.snippet}\n"
                answer += f"ID: {msg.id}\n"
                answer += f"ThreadID: {msg.thread_id}\n"
                answer += "----------\n"
            print(answer)
            return answer

        
        except RefreshError as e:
            Colors.printc(f"Error refreshing token: {e}", Colors.RED)
            return f"Error refreshing token: {e}"
        except Exception as e:
            Colors.printc(f"An error occurred: {e}", Colors.RED)
            return f"An error occurred: {e}"   

    def get_email_details(self, email_id: str, thread_id: str):
        """ Get the details of an email message and convert HTML to plain text """
        service = self.get_service()
        gmail = SimplerGmail(service)

        msg = service.users().messages().get(
            userId='me', 
            id=email_id,
            format="full"
        ).execute()
        msg: Message = gmail._build_message_from_ref("me", msg)

        # Assuming the email's body is in HTML format
        html_body = msg.html
        soup = BeautifulSoup(html_body or "", 'html.parser')
        text_body = soup.get_text()

        #msg['payload']['body']['data'] = text_body
        #return json.dumps(msg)
        return text_body
    
    def send_email(
        self, 
        to: str, 
        subject: str, 
        body_plain_text: str|None=None,
        body_markdown: str|None=None,
        image_url: Optional[str] = None
        ) -> str:
        """ Send an email message. Provide body as either plain text or markdown text. """
        # construct our mime message
        if body_markdown:
            body_html = markdown_to_html(body_markdown)
            body_plain_text = body_markdown
        elif body_plain_text:
            body_html = GmailAPITool.wrap_text_as_html(body_plain_text)
        else:
            body_plain_text = "No message"

        msg = GmailAPITool.create_message(
            "me", 
            to, 
            subject, 
            body_html,
            body_plain_text, 
            image_url
        )
        # build our 'service' client with our auth tokens
        service = self.get_service()
        
        message = (service.users().messages().send(userId="me", body=msg)
                .execute())
        return f"Mail sent, and message Id is {message['id']}"

    @staticmethod
    def wrap_text_as_html(text: str) -> str:
        return f"<html><body>{text}</body></html>"
    
    @staticmethod
    def create_message(sender, to, subject, message_html, message_text, image_url):
        message = MIMEMultipart('alternative')
        message['to'] = to
        message['from'] = sender
        message['subject'] = subject
        text_msg = MIMEText(message_text)
        message.attach(text_msg)
        if image_url:
            msg = MIMEText(f'{message_html}<br><img src="cid:image1">', 'html')
            message.attach(msg)
            r = requests.get(image_url)
            if r.status_code == 200:
                msgImage = MIMEImage(r.content)
                msgImage.add_header('Content-ID', '<image1>')
                message.attach(msgImage)
            else:
                logger.error(f"Failed to fetch image from {image_url}")
        else:
            msg = MIMEText(message_html, 'html')
            message.attach(msg)

        return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}

    def get_service(self):
        if 'tokens' in self.credentials:
            tokens = json.loads(self.credentials['tokens'])
        return build(
            'gmail', 
            'v1', 
            credentials=GmailAPITool.setup_credentials(tokens, SCOPES, self.get_oauth_client_id_and_secret())
        )
