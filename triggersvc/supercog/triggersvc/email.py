from sqlalchemy import Engine
from sqlmodel import SQLModel, Session, Field
from uuid import UUID, uuid4
from typing import Optional
from datetime import datetime

from supercog.shared.services import config, db_connect
from supercog.shared.models import RunCreate


"""
This is the imaplib solution for accessing gmail.
it works well with username password authentication
"""
import imaplib
import email

from email.parser import BytesParser
from email.policy import default
from email.header import decode_header

def get_email_body(message):
    if message.is_multipart():
        # Assume the first part is the text/plain body
        for part in message.walk():
            if part.get_content_type() == 'text/plain':
                return part.get_payload(decode=True).decode()
            elif part.get_content_type() == 'text/html':
                return part.get_payload(decode=True).decode()
        # If no suitable part was found
        return None
    else:
        # For non-multipart emails, just return the payload
        return message.get_payload(decode=True).decode()
    
 def pollForGmail(agent: Agent):
    """ poll for email messages for the user attached to this trigger
    
    Keyword arguments:
    agent: Agent

    description:
    This function will poll an email server for the arrival of email messages for a specific user.
    We use the simplegmail package to interface with gmail backends. 
    FIXME: We will need a more generic maybe SMTP package for interfacing to other types of email servers.
    Currently poll will pull the first message it finds in email that through filtering is determined not 
    to be a junk email. 
    FIXME: As a future enhancement we will may want to integrate the use of the LLM to filter the emails for appropriate
    candidate emails. However the simplegmail api exposes all of the builtin gmail filtering options which are not
    really easy for the LLM to access. The power of the LLM is in interpreting the text. So I think we will want a combination
    of both especially for sophisticate users.
    FIXME: Currently we hard code some filter strings for testing. If we continue to use this without LLM augmentation we
    will also want to be able to pass these filters down or in some way connect them to the intent of the Agent.ai string.

    return:
    We will embed a format_str into the trigger passed to the Agent when invoking the agent. This will
    eventually go into the generic {TRIGGER} variable in the prompt sent to the LLM for further processing.
    format_str:
    From: {from}
    Subject: {subject}
    Date: {Date}
    Messsage
    ###
    {body}
    ###
    """

    # Replace the following with your Gmail address and App Password
    username = 'alieralex@gmail.com'
    app_password = 'Rufino88!@#'

    # Connect to Gmail's IMAP server
    mail = imaplib.IMAP4_SSL('imap.gmail.com')

    # Authenticate
    mail.login(username, app_password)

    # Select the mailbox you want to check (INBOX, for example)
    mail.select('inbox')

    
    while (1)
        # Search for specific emails (in this case, all unread emails)
        # Use '(ALL)' to fetch all emails
        #status, messages = mail.search(None, 'UNSEEN')
        status, messages = mail.search(None, f'(SUBJECT "{agent.trigger_arg}")')

        if status == 'OK':
            # Convert messages to a list of email IDs
            messages = messages[0].split()
    
            # Fetch the latest 10 emails
            for num in messages[-10:]:
                typ, data = mail.fetch(num, '(RFC822)')
                for response_part in data:
                    if isinstance(response_part, tuple):
                        # Parse the email content
                        raw_email = email.message_from_bytes(response_part[1])
                        #raw_email = data[0][1]  # Get the raw email bytes
                        mime_message = BytesParser(policy=policy.default).parsebytes(raw_email)
                        email_body = get_email_body(mime_message)
                        format_str =
                        f'From: {mime_message["From"]}\n'+
                        f'From: {mime_message["To"]}\n'+
                        f'Subject: {mime_message["Subject"]}\n'+
                        f'Date: {{mime_message["Date"]}\n'+
          
                        #f'Message: ###\n{message.plain}\n###\n' +
                        f'Mime Message: ###\n{email_body}\n###\n'
                        # post it to the agents that are listening to it.
                        # Shouldn't we as a better design instantiate an agent object and the call run on it??
                        trigger.run_agent(
                            # where does tenant_id come from
                            agent.user_id
                            agent.id
                            )
        time.sleep(delay)
    mail.close()  # Close the mailbox 
    mail.logout() # Logout from the server
                    
# Decode the email subject
# subject, encoding = decode_header(msg["Subject"])[0]
# if isinstance(subject, bytes):
#  # If it's a bytes type, decode to str
#  subject = subject.decode(encoding)
#  from_header = decode_header(msg['From'])
#  from_email = email.utils.parseaddr(from_header[0][0].decode(from_header[0][1] if from_header[0][1] else 'utf-8'))[1]
    
  
