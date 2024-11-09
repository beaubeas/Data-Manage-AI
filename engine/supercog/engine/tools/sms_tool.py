import json
import smtplib
from typing import Any, Callable
from supercog.engine.tool_factory import ToolFactory, ToolCategory

class SMSTool(ToolFactory):
    sender_email: str=""
    email_password: str=""
    def __init__(self):
        super().__init__(
            id = "sms_connector",
            system_name = "SMS",
            logo_url=super().logo_from_domain("iphonehacks.com"),
            category=ToolCategory.CATEGORY_LIVE,
            auth_config = {
                "strategy_token": {
                    "sender_email":   "Sender's email",
                    "email_password": "Sender's email password",
                    "help": "Enter your email credentials to use as sender of text message",
                }
            },
            help="""
Use this tool to send SMS message by email to a list of popular cell service providers.
"""
        )


    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions(self.send_sms_via_email)

    # The API Key e1da3681467246ffa14ba070e612ac58  is Alexo@supercog.ai's key for abstractapi to find carriers 
    def send_sms_via_email(
        self,
        phone_number,
        carrier="tmobile",
        subject="",
        message="",
        smtp_server="smtp.gmail.com",
        smtp_port=587
        ) -> dict:
        """ Sends a message to the indicated sms recipient.
        recipient_phone_number       -- 10 digit phone number
        message                      -- the message to send via SMS
        smtp_server="smtp.gmail.com" -- Use smpt lib to send an email to t-mobile's server
        smtp_port=587                -- default port
        SMS carriers supply an email gateway to send SMS messages to their subscribers. 
        This is a feature intended for companies that need bulk access to SMS.
        However it has been abused by spamers and so carriers are checking for spammers or at worse 
        discontinuing the service. Here we save a list of the popular carriers and their gateways.
        """
        self.sender_email   =self.credentials["sender_email"]
        self.email_password =self.credentials["email_password"]        #email_password ='qhbeupqxfvplbgtp'

        #    FIXME: currently you have to pass in the carrier name, would be nice to detrmine it 
        #           from the phone number.
        try:
            import smtplib
        except ImportError:
            return {"status": "error", "message": "SMTP lib packages are not installed."}

        # to add a carrier check: https://avtech.com/articles/138/list-of-email-to-sms-addresses/

        if carrier == 'tmobile' or carrier == 'T-Mobile Usa, Inc.':
            recipient = f"{phone_number}@tmomail.net" # tmobile provider
        elif carrier == 'AT&T' or  carrier == 'att':
            # for MMS: <10-digit-number>@mms.att.net
            recipient = f"{phone_number}@txt.att.net"
        elif carrier == 'verizon':
            recipient = f"{phone_number}@vtext.com"
        elif carrier == 'Claro':
            recipient = f"{phone_number}@vtext.com"
        elif carrier == 'sprint':
            recipient = f"{phone_number}@sprintpaging.com"
        elif carrier == 'sprintpcs':
            recipient = f"{phone_number}@messaging.sprintpcs.com"
        else:
            return {"status": "error", "message": f"Carrier {carrier} not supported. Please check spelling"}
        try: 
            server = smtplib.SMTP(smtp_server, smtp_port)  # Set up the SMTP server
            server.starttls()  # Upgrade the connection to secure
            server.login(self.sender_email, self.email_password)
            # Prepare the email headers and body
            message +=" (sent by supercog.ai)"
            email_headers = [
                f"From: {self.sender_email}",
                f"To: {recipient}",
                f"Subject: {subject}",
                "",
                message
            ]
            email_message = "\r\n".join(email_headers)
            # Send the email
            server.sendmail(self.sender_email, recipient, email_message)

            server.quit()
            return {"status": "success", "message": "Message sent."}
        except:
            return {"status": "error", "message": str(e)}
            
