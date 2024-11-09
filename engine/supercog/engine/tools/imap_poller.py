from sqlalchemy import Engine
from sqlmodel import SQLModel, Session, Field, select
from uuid import UUID, uuid4
from typing import Optional
from datetime import datetime



import requests
import sys
import time
import re

from supercog.shared.services import config, db_connect
from supercog.shared.models import RunCreate
from supercog.shared.services import config, serve, db_connect

from supercog.engine.db import Agent, EmailMsgsProcessed

from supercog.shared.models import CredentialBase
from supercog.shared.logging import logger
from supercog.shared.services import get_service_host

from supercog.engine.db import session_context
from supercog.shared.services import config, db_connect
from sqlmodel import Session


import asyncio

"""
This is the imaplib solution for accessing gmail.
it works well with username password authentication
"""
import imaplib
import email
from email import policy
from email.parser import BytesParser
from email.policy import default
from email.header import decode_header

from bs4 import BeautifulSoup



BASE = get_service_host("engine")

def create_run(     tenant_id: str,
                    user_id: str,
                    agent_id: str,
                    format_str: str) -> dict:
    """
    create_run will post to the agent service to run an agent triggered by email with an email to process
    Keyword arguments:
    __________________________
    format_str -- The pertinent data from the email message to be processed.
    tenant_id  --
    user_id    --
    agent_id   --
    """
    run_data = {
                "tenant_id": tenant_id + "",
                "user_id": user_id + "",
                "agent_id": agent_id,
                "input_mode": "truncate",
                "input": format_str,
                "logs_channel": "email_logs",
                "result_channel": "test_results",
                "logs_channel": "test_logs",
                }
    response = requests.post(BASE + "/runs", json=run_data)
    return response.json()

def supports_custom_flags(mail):
    """
    Check for the 'PERMANENTFLAGS' capability. aka custom flags
    """
    typ, data = mail.response('CAPABILITY')
    if '\\*' in str(data) or 'PERMANENTFLAGS' in str(data):
        return 1 #"Custom flags are supported.
    if data is None:
        return 0 # in this case we were unable to read the CAPABILITIES for some reason. so we don't know if they're supported
    return 0 # ok we got a capability, but not the PERMANENT flags capability

def already_processed(email_id, agent_id, session):
    """
    search for this email in the database of already processed emails that we keep.
    return the processed flag and the agentId so we can filter based on the agent 
    """
    uid=str(int.from_bytes(email_id, 'big'))
    statement = select(EmailMsgsProcessed.processed,EmailMsgsProcessed.agent_id).where(EmailMsgsProcessed.uid == uid)

    result = session.exec(statement).first()
    print (result)
    if(result is None):
        processed =0
        agent_id = None;
    else:
        processed, agent_id = result
    return uid, processed, agent_id

######################################################################
# pollForGmail:
#    This function will poll an email server searching it's inbox for new emails. It will use the 
#    authentication of the user under whom the call is made.
#
#    Currently poll will pull all messages it finds in email that through filtering is determined not 
#    to be a junk email.
#
#    Currently using Imaplib which supports lots of different types of email servers. 
#    But the simplegmail api exposes all of the builtin gmail filtering options which are not
#    really easy for the LLM to access.
#
#    FIXME: As a future enhancement we  may want to integrate the use of the LLM to filter the
#           emails for appropriate candidate emails. This would be over and above email search.
#           Which means the Agent UI might have a few parts that take LLM prompts.
#           The power of the LLM is in interpreting the text of the message.
#           So I think we will want a combination of both especially for sophisticated users.
#
#    FIXME: Would be nice to work more like push model with a push from the mail server. 
#           Need to look deeper into the mail libraries
#
#    FIXME: prefilter the list of email_ids before we get into the main for loop poping off 
#           all already processed emails. making it one select statement to fetch all processed 
#           email_ids instead of each time through the loop
#    NOTE:  if we want to have custom flags can use:     supports_custom_flags(mail):
#    Return:
#    ___________
#    We will embed a format_str into the trigger passed to the Agent when invoking the agent. This will
#    eventually go into the generic {TRIGGER} variable in the prompt sent to the LLM for 
#    further processing.
#    format_str:
#        From: {from}
#        To: {to}
#        Subject: {subject}
#        Date: {Date}
#        Message:
#        ###
#        {body}
#        ###
#    Attachments:
#        - {filename1} (Size: {size1} bytes, Path: {path1})
#        - {filename2} (Size: {size2} bytes, Path: {path2})
async def pollForGmail(filter: str,
                       tenant_id: str,
                       user_id: str,
                       agent_name: str,
                       agent_id: str,
                       username: str,
                       app_password: str):
    """
    Poll for email messages for the user attached to this trigger
    filter       -- The filter on the users inbox. We currently force the filter to be on the subject line
    tenant_id    --
    user_id      --
    agent_id     --
    server       -- The email server. I.e. Gmail, Outlook, Yahoo
    username     -- email address for login
    app_password -- This can be the password or the app password.
    """
    imap_server = 'imap.gmail.com'
    port = 993
    delay = 60

    # Create agent-specific directory
    agent_dir = create_agent_directory(agent_name, agent_id)


    engine = db_connect("engine")

    mail = imaplib.IMAP4_SSL(imap_server, port)
    mail.login(username, app_password)
    mail.select('inbox', readonly=True)

    with Session(engine) as session:
        while True:
            status, data = mail.search(None, f'(SUBJECT "{filter}")')

            if status == 'OK':
                email_ids = data[0].split()
                total_emails = len(email_ids)
                print(f'Search inbox with filter: (SUBJECT "{filter}") found {total_emails} messages that match')

                while len(email_ids) > 0:
                    num_msgs_to_process = min(10, len(email_ids))

                    for email_id in email_ids[-num_msgs_to_process:]:
                        email_ids.pop()

                        uid = str(int.from_bytes(email_id, 'big'))
                        statement = select(EmailMsgsProcessed.processed, EmailMsgsProcessed.agent_id).where(EmailMsgsProcessed.uid == uid)
                        result = session.exec(statement).first()

                        if result and result[0]:  # Email already processed
                            continue

                        _, msg_data = mail.fetch(email_id, '(RFC822)')
                        email_body = msg_data[0][1]
                        email_message = email.message_from_bytes(email_body)

                        processed_email = process_email(email_message, agent_dir)

                        # Store processed email in database
                        email_msg_info = EmailMsgsProcessed(
                            uid=uid,
                            from_field=processed_email['sender'],
                            to_field=email_message['To'],
                            subject_field=processed_email['subject'],
                            processed=1,
                            agent_id=agent_id
                        )
                        session.add(email_msg_info)
                        session.commit()
                        session.refresh(email_msg_info)

                        # Prepare email content for agent
                        format_str = (
                            f"From: {processed_email['sender']}\n"
                            f"To: {email_message['To']}\n"
                            f"Subject: {processed_email['subject']}\n"
                            f"Date: {processed_email['date']}\n"
                            f"Message: ###\n{processed_email['body']}\n###\n"
                        )

                        if processed_email['attachments']:
                            format_str += "Attachments:\n"
                            for att in processed_email['attachments']:
                                format_str += f"- {att['filename']} (Size: {att['size']} bytes, Path: {att['path']})\n"

                        print(f"Sending email to Agent: {format_str[:100]}...")  # Truncated for brevity
                        create_run(tenant_id, user_id, agent_id, format_str)

            await asyncio.sleep(delay)

    mail.close()
    mail.logout()

def create_agent_directory(agent_name: str, agent_id: str) -> str:
    """
    Create and return the path to an agent-specific directory.

    This function creates a directory for an agent based on its name and ID.
    It ensures the directory name is safe for file systems by sanitizing the agent name.

    Args:
        agent_name (str): The name of the agent.
        agent_id (str): The unique identifier of the agent.

    Returns:
        str: The path to the created agent-specific directory.

    Note:
        If the directory already exists, this function will not recreate it,
        but will return the path to the existing directory.
    """
    safe_agent_name = re.sub(r'[^\w\-_\. ]', '_', agent_name)
    agent_dir_name = f"{safe_agent_name}_{agent_id}"
    agent_dir = os.path.join(os.getcwd(), agent_dir_name)
    os.makedirs(agent_dir, exist_ok=True)
    return agent_dir

def decode_email_header(header):
    """
    Decode email subject or sender information.
    """
    decoded_parts = decode_header(header)
    decoded_header = ""
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            decoded_header += part.decode(encoding or 'utf-8', errors='ignore')
        else:
            decoded_header += part
    return decoded_header

def get_safe_filename(filename, base_dir):
    """
    Ensure the filename is safe for all operating systems and doesn't overwrite existing files.
    """
    filename = os.path.basename(filename)
    safe_filename = re.sub(r'[^\w\-_\. ]', '_', filename)
    base, extension = os.path.splitext(safe_filename)
    counter = 1
    while os.path.exists(os.path.join(base_dir, safe_filename)):
        safe_filename = f"{base}_{counter}{extension}"
        counter += 1
    return safe_filename

def get_text_from_html(html_content):
    """Convert HTML content to plain text."""
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text()

def decode_email_body(part):
    """
    Decode the email body, handling different character encodings.
    """
    content = part.get_payload(decode=True)
    charset = part.get_content_charset()
    if charset:
        try:
            return content.decode(charset)
        except UnicodeDecodeError:
            return content.decode('utf-8', errors='ignore')
    return content.decode('utf-8', errors='ignore')

def process_email_part(part, body, attachments, base_dir):
    """
    Recursively process email parts to extract body and attachments.
    """
    if part.is_multipart():
        for subpart in part.get_payload():
            process_email_part(subpart, body, attachments, base_dir)
    else:
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition"))

        if content_type == "text/plain" and "attachment" not in content_disposition:
            body.append(decode_email_body(part))
        elif content_type == "text/html" and "attachment" not in content_disposition:
            html_content = decode_email_body(part)
            body.append(get_text_from_html(html_content))
        elif "attachment" in content_disposition or "inline" in content_disposition:
            filename = part.get_filename()
            if filename:
                attachment_data = part.get_payload(decode=True)
                safe_filename = get_safe_filename(filename, base_dir)
                file_path = os.path.join(base_dir, safe_filename)
                with open(file_path, 'wb') as f:
                    f.write(attachment_data)
                attachments.append({
                    'filename': safe_filename,
                    'path': file_path,
                    'size': len(attachment_data)
                })

def process_email(email_message, base_dir):
    """
    Process an email message, extracting subject, sender, date, body, and attachments.
    """
    subject = decode_email_header(email_message['subject'])
    sender = decode_email_header(email_message['from'])
    date = email_message['date']

    body_parts = []
    attachments = []
    process_email_part(email_message, body_parts, attachments, base_dir)

    body = "\n".join(body_parts)

    return {
        'subject': subject,
        'sender': sender,
        'date': date,
        'body': body[:500] + '...' if len(body) > 500 else body,
        'attachments': attachments
    }
