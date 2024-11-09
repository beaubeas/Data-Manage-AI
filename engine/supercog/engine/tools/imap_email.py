from sqlalchemy import Engine
from sqlmodel import SQLModel, Session, Field, select
from uuid import UUID, uuid4
from typing import Optional
from datetime import datetime



import requests
import sys
import time

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

def get_text_from_html(html_content):
    """Convert HTML content to plain text."""
    soup = BeautifulSoup(html_content, 'html.parser')
    return soup.get_text()

    
async def pollForGmail( filter: str,
                        tenant_id: str,
                        user_id: str,
                        agent_id: str,
                        username: str,
                        app_password: str):
    """
    poll for email messages for the user attached to this trigger
    
    Keyword arguments:
    __________________________
    filter       -- The filter on the users inbox. We currently force the filter to be on the subject line
    tenant_id    --
    user_id      --
    agent_id     --
    server       -- The email server. I.e. Gmail, Outlook, Yahoo
    username     -- email address for login
    app_password -- This can be the password or the app password.
    description:
    ____________________
    This function will poll an email server searching it's inbox for new emails. It will use the 
    authentication of the user under whom the call is made.

    Currently poll will pull all messages it finds in email that through filtering is determined not 
    to be a junk email. 

    Currently using Imaplib which supports lots of different types of email servers. 
    But the simplegmail api exposes all of the builtin gmail filtering options which are not
    really easy for the LLM to access.

    FIXME: As a future enhancement we  may want to integrate the use of the LLM to filter the
           emails for appropriate candidate emails. This would be over and above email search.
           Which means the Agent UI might have a few parts that take LLM prompts.
           The power of the LLM is in interpreting the text of the message.
           So I think we will want a combination of both especially for sophisticated users. 

    FIXME: Would be nice to work more like push model with a push from the mail server. 
           Need to look deeper into the mail libraries

    FIXME: prefilter the list of email_ids before we get into the main for loop poping off 
           all already processed emails. making it one select statement to fetch all processed 
           email_ids instead of each time through the loop
    NOTE:  if we want to have custom flags can use:     supports_custom_flags(mail):
    Return:
    ___________
    We will embed a format_str into the trigger passed to the Agent when invoking the agent. This will
    eventually go into the generic {TRIGGER} variable in the prompt sent to the LLM for 
    further processing.
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
    #username = 'alieralex@gmail.com'
    #app_password = 'qhbeupqxfvplbgtp'
    imap_server = 'imap.gmail.com'        # Connect to Gmail's IMAP server on default port
    delay = 60                            # 60 second wait in thread for polling loop
    engine = db_connect("engine")         # need this to connect with the model for remembering which emails we've processed
    port = 993
    if( server == 'Gmail' or server == 'imap.gmail.com' ):
        imap_server = 'imap.gmail.com'        # Connect to Gmail's IMAP server on default port
    elif (server == "outlook.office365.com"):
        imap_server = 'outlook.office365.com' # Connect to outlook office's IMAP server on port

    mail = imaplib.IMAP4_SSL(imap_server,port)  
    mail.login(username, app_password)          # Authenticate
    mail.select('inbox', readonly=True)         # Select the mailbox, read-only mode to not change any message flags inadvertently

    with Session(engine) as session:
          
        while True:  # Main loop 
            #status,data = mail.search(None, 'UNSEEN') # Search for all unread emails)
            status, data = mail.search(None, f'(SUBJECT "{filter}")')

            if status == 'OK':
                email_ids = data[0].split()    # Convert messages to a list of email IDs
                total_emails = len(email_ids)
                print (f'Search inbox with filter: (SUBJECT  "{filter}")'+
                       f'found {total_emails} messages that match')

                while(len(email_ids)>0):    # process all emails that match the filter criteria
                    num_msgs_to_process = min(10, len(email_ids))    # process in batches of 10 

                    for email_id in email_ids[-num_msgs_to_process:]:
                        email_ids.pop()    # remove the item we are processing from the list
                        #                    to control the while loop so we don't process it again.
                        # Fetch flags before processing
                        typ, flags_before = mail.fetch(email_id, '(FLAGS)')
                        # search in database of processed emails.
                        uid, processed, processed_agent_id = already_processed(email_id, agent_id, session) 
                        print("email id: "+uid+'Processed flag: ',processed,
                              ' agent id: ',processed_agent_id,' flags = ',flags_before)
                        
                        if (processed ): #and (agent_id == processed_agent_id) ):     
                            print ("skipping message ")
                            continue   # skip messages we've already processed
                        # use mail package to get the actual email
                        typ, data = mail.fetch(email_id, '(RFC822)')  
                        for response_part in data:
                            body =''  # initialize body each time through
                            # tuple means it's the actual raw email message
                            if isinstance(response_part, tuple):    
                                # Parse the email content
                                raw_email = response_part[1]  # Get the raw email bytes
                                msg = email.message_from_bytes(response_part[1])
                       
                                # Handling the body of the email
                                if msg.is_multipart():
                                    # build body of message for multipart inline attachements
                                    for part in msg.walk():
                                        # Extract email content type
                                        content_type = part.get_content_type()
                                        content_disposition = str(part.get("Content-Disposition"))
        
                                        # Look for text/plain or text/html parts
                                        if content_type == "text/plain" and \
                                            "attachment" not in content_disposition:
                                            # get text/plain add to body
                                            try:
                                                # Try UTF-8 first
                                                body += part.get_payload(decode=True).decode()
                                            except UnicodeDecodeError:
                                                try:
                                                    # Try a different encoding, like 'iso-8859-1'
                                                    body += part.get_payload(decode=True).decode('iso-8859-1')
                                                except UnicodeDecodeError:
                                                    # If all fails, decode with replacement characters
                                                    body += part.get_payload(decode=True).decode('utf-8', errors='replace')
                                        elif content_type == "text/html" and \
                                            "attachment" not in content_disposition: 
                                            # Get the charset from part, default to utf-8 if not found
                                            charset = part.get_content_charset('utf-8')
                                            print ( "decoding using charset: ",charset)
                                            # Decode using the charset from the part
                                            html = part.get_payload(decode=True).decode(charset, errors='replace')
                                            body += get_text_from_html(html)
                                        # FIXME: handle attachements
                                else:
                                    def decode_payload(payload, encodings=['utf-8', 'iso-8859-1']):
                                        for encoding in encodings:
                                            try:
                                                return payload.decode(encoding)
                                            except UnicodeDecodeError:
                                                continue
                                        return payload.decode('utf-8', errors='replace')  # Fallback if all encodings fail

                                    try:
                                        payload = msg.get_payload(decode=True)
                                        body = decode_payload(payload)
                                        content_type = msg.get_content_type()
                                        if content_type == "text/html":
                                            html = decode_payload(payload)  # Decode again for HTML content
                                            plain_text = get_text_from_html(html)
                                        else:
                                            plain_text = body  # Reuse the decoded body if not HTML
                                    except Exception as e:
                                        print(f"Error processing email: {e}")
                                        plain_text = ""
                                        return plain_text

                                    """
                                    # Email is not multipart so we can just get the whole message body
                                    body = msg.get_payload(decode=True).decode()
                                    content_type = msg.get_content_type()
                                    if content_type == "text/html":
                                        html = msg.get_payload(decode=True).decode()
                                        plain_text = get_text_from_html(html)
                                    else:
                                        plain_text = msg.get_payload(decode=True).decode()
                                    body = plain_text
                                    """

                                    
                                #Build the SQL INSERT to set the processed flag
                                email_msg_info = EmailMsgsProcessed(uid=uid,       
                                                                    from_field=msg["From"],
                                                                    to_field=msg["To"],
                                                                    subject_field=msg["Subject"],
                                                                    processed=1,
                                                                    agent_id=agent_id)
                                session.add(email_msg_info)
                                session.commit()
                                session.refresh(email_msg_info)
              
                                header_str = (
                                    f'From: {msg["From"]}\n'+
                                    f'To: {msg["To"]}\n'+
                                    f'Subject: {msg["Subject"]}\n'+
                                    f'Date: {msg["Date"]}\n'
                                    )
                                debug_str = 'Send email to Agent: '+header_str
                                format_str = (
                                    header_str+
                                    f'Message: ###\n{body}\n###\n' 
                                    #f'Mime Message: ###\n{email_body}\n###\n'
                                    )
                                print (debug_str)
                                # post it to the agents that are listening to it.
                                create_run( tenant_id, user_id, agent_id, format_str)
            #time.sleep(delay) # sleep for a while to preserve resorurces
            await asyncio.sleep(delay)
        mail.close()  # Close the mailbox 
        mail.logout() # Logout from the server

                    
