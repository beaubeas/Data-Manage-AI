import os
import re
import imaplib
import email
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Callable, List, Dict, Optional, Tuple
from pytz import utc
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

from supercog.shared.logging import logger
from supercog.shared.utils   import Colors

from supercog.engine.triggerable  import Triggerable
from supercog.engine.tool_factory import ToolFactory, ToolCategory, LLMFullResult
from supercog.engine.email_utils  import process_email, decode_email_header

from supercog.shared.services import db_connect
from supercog.engine.db       import EmailMsgsProcessed
from sqlmodel                 import Session, select

class IMAPTool(ToolFactory):
    email_address: str = ""
    app_password: str = ""
    agent_dir: str = ""

    
    def __init__(self):
        super().__init__(
            id = "imap_connector",
            system_name = "Gmail via IMAP/SMTP",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/2/2b/EmailServerIcon.png",
            category=ToolCategory.CATEGORY_EMAIL,
            help = """
Send and retrieve Gmail messages via IMAP/SMTP.
""",
            auth_config = {
                "stategy_token": {
                    "email_address": "Your Email address",
                    "app_password": "The mail account password (app password for Gmail)",
                    "help": """
Please visit [Google's documentation](https://support.google.com/accounts/answer/185833?hl=en) 
to learn how to create an app password. You need to supply this password to use the Gmail tool.
"""
                }
            }
        )
        self.agent_dir = ""
        
    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.send_email,
            self.retrieve_emails,
            self.retrieve_emails_once,
            self.list_emails,
        ])
    
    def list_emails(self, limit: int = 50, subject_words: str = None) -> List[Dict[str, Any]]:
        """
        List emails in the inbox, using SORT if available, otherwise handling large mailboxes efficiently.
        Optionally filter by words in the subject.
        
        :param limit: Maximum number of emails to retrieve (default: 50)
        :param subject_words: Words to search for in the subject (optional)
        :return: List of dictionaries containing email information
        """
        self.email_address = self.credentials['email_address']
        self.app_password = self.credentials['app_password']
        imap_server = "imap.gmail.com"
        imap_port = 993

        Colors.printc(f"Starting to list emails with limit={limit}", Colors.OKBLUE)

        imap = None
        try:
            Colors.printc(f"Connecting to IMAP server: {imap_server}:{imap_port}", Colors.OKCYAN)
            imap = imaplib.IMAP4_SSL(imap_server, imap_port)

            Colors.printc(f"Logging in with email: {self.email_address}", Colors.OKCYAN)
            imap.login(self.email_address, self.app_password)

            Colors.printc("Selecting INBOX", Colors.OKCYAN)
            imap.select('INBOX')

            search_criteria = ['ALL']
            if subject_words:
                # Use HEADER search for subject words
                search_criteria = ['HEADER', 'Subject', subject_words]
                Colors.printc(f"Searching for emails with subject containing: {subject_words}", Colors.OKCYAN)

            try:
                # Try SORT command first
                _, message_numbers = imap.sort("DATE", "UTF-8", *search_criteria)
                message_numbers = message_numbers[0].split()
                message_numbers = message_numbers[-limit:]  # Get the most recent 'limit' emails
                Colors.printc("SORT command successful", Colors.OKGREEN)
            except imaplib.IMAP4.error:
                Colors.printc("SORT command not supported, falling back to date-based search", Colors.YELLOW)
                # Fall back to date-based search
                message_numbers = self.date_based_search(imap, limit, search_criteria)

            email_list = []
            for num in reversed(message_numbers):
                if len(email_list) >= limit:
                    break
                
                Colors.printc(f"Fetching message ID: {num}", Colors.YELLOW)
                _, msg_data = imap.fetch(num, '(RFC822.HEADER)')
                email_header = msg_data[0][1]
                email_message = email.message_from_bytes(email_header)
                
                subject = self.decode_email_header(email_message['subject'])
                sender = self.decode_email_header(email_message['from'])
                date_str = email_message['date']
                
                email_list.append({
                    'id': num.decode(),
                    'subject': subject,
                    'sender': sender,
                    'date': date_str
                })

            Colors.printc(f"Successfully retrieved {len(email_list)} emails", Colors.OKGREEN)
            return email_list
        
        except Exception as e:
            Colors.printc(f"Error listing emails: {str(e)}", Colors.FAIL)
            import traceback
            Colors.printc(traceback.format_exc(), Colors.FAIL)
            return []
        finally:
            if imap:
                try:
                    Colors.printc("Closing IMAP connection", Colors.OKCYAN)
                    imap.close()
                    Colors.printc("Logging out from IMAP server", Colors.OKCYAN)
                    imap.logout()
                except Exception as e:
                    Colors.printc(f"Error during IMAP close/logout: {str(e)}", Colors.FAIL)
                    import traceback
                    Colors.printc(traceback.format_exc(), Colors.FAIL)

    def date_based_search(self, imap, limit: int, search_criteria: List[str]) -> List[bytes]:
        """Helper method for date-based search when SORT is not available."""
        email_ids = []
        date = datetime.now()
        while len(email_ids) < limit:
            date_criterion = f'(SINCE "{date.strftime("%d-%b-%Y")}")'
            full_criteria = search_criteria + [date_criterion]
            _, message_numbers = imap.search(None, *full_criteria)
            message_numbers = message_numbers[0].split()
            
            if not message_numbers:
                # If no emails found, move date back by a week
                date -= timedelta(days=7)
                continue

            email_ids.extend(message_numbers)
            
            # Move the date back by a day for the next iteration if needed
            date -= timedelta(days=1)

        return email_ids[-limit:]  # Return only the most recent 'limit' email IDs

                    
    def send_email(self,
                   to: str,
                   subject: str,
                   body: str) -> str:
        """ Send an email message """
        self.email_address = self.credentials['email_address']
        self.app_password = self.credentials['app_password']
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        smtp_username = self.email_address
        smtp_password = self.app_password
        
        # Create a multipart message
        msg = MIMEMultipart()
        sender_email = self.email_address
        msg['From'] = sender_email
        msg['To'] = to
        msg['Subject'] = subject
        
        # Body of the email
        msg.attach(MIMEText(body, 'plain'))
        
        try:
            # Create a secure SSL context
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()  # Secure the connection
            server.login(smtp_username, smtp_password)
            text = msg.as_string()
            server.sendmail(sender_email, to, text)
            return f"Sent message to {to} with subject '{subject}'."
        except Exception as e:
            # Print any error messages to stdout
            return f"Error: SMTP sender error: {e}."
        finally:
            server.quit()

    def retrieve_emails(self,
                        limit: int = 5,
                        search_criteria: str = "",
                        since_date: Optional[datetime] = None,
                        to_address: Optional[str] = None,
                        subject_words: Optional[str] = None) -> str:
        """
        Retrieve emails from the IMAP server based on specified criteria, date, recipient, and subject words.
        This version does not track which emails have been read.
        """
        return LLMFullResult(self.retrieve_emails_base(
            limit, search_criteria, since_date, to_address, subject_words,
            mark_as_read_func=self.dummy_mark_as_read,
            is_read_func=self.dummy_is_read
        ))

    def retrieve_emails_once(self,
                             limit: int = 5,
                             search_criteria: str = "",
                             since_date: Optional[datetime] = None,
                             to_address: Optional[str] = None,
                             subject_words: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve emails from the IMAP server based on specified criteria, date, recipient, and subject words.
        This version tracks which emails have been read and only processes new emails.
        """
        result = self.retrieve_emails_base(
            limit, search_criteria, since_date, to_address, subject_words,
            mark_as_read_func=self.mark_email_as_read,
            is_read_func=self.is_email_read
        )
    
        if not result:
            Colors.printc("No new emails found matching the criteria.", Colors.YELLOW)
    
        return result

    def retrieve_emails_base(self,
                             limit: int,
                             search_criteria: str,
                             since_date: Optional[datetime],
                             to_address: Optional[str],
                             subject_words: Optional[str],
                             mark_as_read_func: Callable,
                             is_read_func: Callable) -> List[Dict[str, Any]]:
        """Base function for retrieving emails."""
        Colors.printc(f"Starting retrieve_emails with limit={limit}, search_criteria='{search_criteria}', since_date={since_date}, to_address={to_address}, subject_words={subject_words}", Colors.OKBLUE)
        
        if search_criteria:
            is_valid, error_message = self.validate_imap_search_criteria(search_criteria)
            if not is_valid:
                raise ValueError(f"Invalid IMAP search criteria: {error_message}")

        self.email_address = self.credentials['email_address']
        self.app_password = self.credentials['app_password']
        imap_server = "imap.gmail.com"
        imap_port = 993

        self.agent_dir = self.run_context.create_agent_directory()
        Colors.printc(f"Agent directory created/confirmed: {self.agent_dir}", Colors.OKCYAN)

        imap = None
        try:
            Colors.printc(f"Connecting to IMAP server: {imap_server}:{imap_port}", Colors.OKCYAN)
            imap = imaplib.IMAP4_SSL(imap_server, imap_port)

            Colors.printc(f"Logging in with email: {self.email_address}", Colors.OKCYAN)
            imap.login(self.email_address, self.app_password)

            Colors.printc("Selecting INBOX", Colors.OKCYAN)
            imap.select('INBOX')

            if since_date is None:
                since_date = datetime.now() - timedelta(days=30)
            date_criterion = since_date.strftime("%d-%b-%Y")

            criteria_parts = [f'(SINCE "{date_criterion}")']
            
            if to_address:
                criteria_parts.append(f'(TO "{to_address}")')
            
            if search_criteria:
                criteria_parts.append(f'({search_criteria})')

            if subject_words:
                criteria_parts.append(f'(HEADER Subject "{subject_words}")')

            final_search_criteria = " ".join(criteria_parts)

            Colors.printc(f"Searching for emails with criteria: {final_search_criteria}", Colors.OKCYAN)
            try:
                _, message_numbers = imap.search(None, final_search_criteria)
            except imaplib.IMAP4.error as e:
                Colors.printc(f"IMAP SEARCH error: {str(e)}", Colors.FAIL)
                _, message_numbers = imap.search(None, f'(SINCE "{date_criterion}")')
                Colors.printc(f"Falling back to retrieving all emails since {date_criterion}", Colors.WARNING)

            message_numbers = message_numbers[0].split()
            Colors.printc(f"Search returned: {len(message_numbers)} messages", Colors.OKGREEN)

            message_ids = message_numbers[-limit:]

            email_list = []
            processed_count = 0
            with Session(db_connect("engine")) as session:
                for num in reversed(message_numbers):  # Process all found messages
                    if processed_count >= limit:
                        break

                    Colors.printc(f"Fetching message ID: {num}", Colors.YELLOW)
                    _, msg_data = imap.fetch(num, '(RFC822)')
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)
                    
                    uid = str(int.from_bytes(num, 'big'))
                    
                    if not is_read_func(session, uid, self.run_context.agent_id):
                        processed_email = self.process_email(email_message, self.agent_dir)
                        processed_email['to'] = email_message['To']
                        email_list.append(processed_email)
                        
                        mark_as_read_func(session, uid, self.run_context.agent_id, email_message)
                        processed_count += 1
                    else:
                        Colors.printc(f"Skipping already processed email: {uid}", Colors.YELLOW)

            Colors.printc(f"Successfully retrieved {len(email_list)} emails", Colors.OKGREEN)
            return email_list
        
        except ValueError as ve:
            Colors.printc(f"Validation error: {str(ve)}", Colors.FAIL)
            raise
        except Exception as e:
            Colors.printc(f"Error retrieving emails: {str(e)}", Colors.FAIL)
            import traceback
            Colors.printc(traceback.format_exc(), Colors.FAIL)
            return []
        finally:
            if imap:
                try:
                    Colors.printc("Closing IMAP connection", Colors.OKCYAN)
                    imap.close()
                    Colors.printc("Logging out from IMAP server", Colors.OKCYAN)
                    imap.logout()
                except Exception as e:
                    Colors.printc(f"Error during IMAP close/logout: {str(e)}", Colors.FAIL)
                    import traceback
                    Colors.printc(traceback.format_exc(), Colors.FAIL)

    def create_my_agent_directory(self) -> str:
        """
        Create and return the path to an agent-specific directory.
        """
        return  self.create_agent_directory(self.run_context.agent_name, self.run_context.agent_id)
    
    @staticmethod
    def create_agent_directory(agent_name: str, agent_id: str) -> str:
        """
        Create and return the path to an agent-specific directory.
        """
        safe_agent_name = re.sub(r'[^\w\-_\. ]', '_', agent_name)
        agent_dir_name = f"{safe_agent_name}_{agent_id}"
        agent_dir = agent_dir_name #os.path.join(os.getcwd(), agent_dir_name)
        os.makedirs(agent_dir, exist_ok=True)
        return agent_dir

    @staticmethod
    def validate_imap_search_criteria(criteria: str) -> Tuple[bool, str]:
        """
        Validate the given IMAP search criteria.
        """
        valid_keys = [
            'ALL', 'ANSWERED', 'BCC', 'BEFORE', 'BODY', 'CC', 'DELETED', 'FLAGGED',
            'FROM', 'KEYWORD', 'NEW', 'OLD', 'ON', 'RECENT', 'SEEN', 'SINCE',
            'SUBJECT', 'TEXT', 'TO', 'UNANSWERED', 'UNDELETED', 'UNFLAGGED',
            'UNKEYWORD', 'UNSEEN'
        ]

        # Check for balanced parentheses
        if criteria.count('(') != criteria.count(')'):
            return False, "Unbalanced parentheses in search criteria."

        # Split the criteria into tokens, preserving quoted strings and parentheses
        tokens = re.findall(r'\(|\)|"[^"]*"|\S+', criteria)

        i = 0
        while i < len(tokens):
            token = tokens[i]

            if token == '(' or token == ')':
                i += 1
                continue

            if token.upper() not in valid_keys:
                if i + 1 < len(tokens) and tokens[i + 1].startswith('"') and tokens[i + 1].endswith('"'):
                    # This is a key-value pair, which is valid
                    i += 2
                else:
                    return False, f"Invalid search key or syntax: {token}"
            else:
                # Check if the next token is a value (if required)
                if token.upper() in ['BCC', 'BEFORE', 'BODY', 'CC', 'FROM', 'KEYWORD', 'ON', 'SINCE', 'SUBJECT', 'TEXT', 'TO', 'UNKEYWORD']:
                    if i + 1 >= len(tokens) or not tokens[i + 1].startswith('"') or not tokens[i + 1].endswith('"'):
                        return False, f"Missing or invalid value for search key: {token}"
                    i += 2
                else:
                    i += 1

        return True, ""

    @staticmethod
    def mark_email_as_read(session: Session, uid: str, agent_id: str, email_message: email.message.EmailMessage):
        """Mark an email as read in the database."""
        email_msg_info = EmailMsgsProcessed(
            uid=uid,
            from_field=email_message['From'],
            to_field=email_message['To'],
            subject_field=email_message['Subject'],
            processed=1,
            agent_id=agent_id
        )
        session.add(email_msg_info)
        session.commit()
        session.refresh(email_msg_info)

    @staticmethod
    def is_email_read(session: Session, uid: str, agent_id: str) -> bool:
        """Check if an email has been read."""
        statement = select(EmailMsgsProcessed.processed).where(
            (EmailMsgsProcessed.uid == uid) & (EmailMsgsProcessed.agent_id == agent_id)
        )
        result = session.exec(statement).first()
        return result is not None and result == 1

    @staticmethod
    def dummy_mark_as_read(session: Session, uid: str, agent_id: str, email_message: email.message.EmailMessage):
        """Dummy function that does nothing."""
        pass

    @staticmethod
    def dummy_is_read(session: Session, uid: str, agent_id: str) -> bool:
        """Dummy function that always returns False."""
        return False

    @staticmethod
    def process_email(email_message: email.message.EmailMessage, agent_dir: str) -> Dict[str, Any]:
        """
        Process an email message, extracting subject, sender, date, body, and attachments.
        """
        subject = IMAPTool.decode_email_header(email_message['subject'])
        sender = IMAPTool.decode_email_header(email_message['from'])
        date = email_message['date']

        body_parts = []
        attachments = []
        IMAPTool.process_email_part(email_message, body_parts, attachments, agent_dir)

        body = "\n".join(body_parts)

        return {
            'subject': subject,
            'sender': sender,
            'date': date,
            'body': body,  # Return the full body without truncation
            #'body': body[:500] + '...' if len(body) > 500 else body,
            'attachments': attachments
        }

    @staticmethod
    def process_email_part(part, body_parts, attachments, agent_dir):
        """
        Recursively process email parts to extract body and attachments.
        """
        if part.is_multipart():
            for subpart in part.get_payload():
                IMAPTool.process_email_part(subpart, body_parts, attachments, agent_dir)
        else:
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))

            if content_type == "text/plain" and "attachment" not in content_disposition:
                body_parts.append(IMAPTool.decode_email_body(part))
            elif content_type == "text/html" and "attachment" not in content_disposition:
                html_content = IMAPTool.decode_email_body(part)
                body_parts.append(IMAPTool.get_text_from_html(html_content))
            elif "attachment" in content_disposition or "inline" in content_disposition:
                filename = part.get_filename()
                if filename:
                    attachment_data = part.get_payload(decode=True)
                    safe_filename = IMAPTool.get_safe_filename(filename, agent_dir)
                    file_path = os.path.join(agent_dir, safe_filename)
                    with open(file_path, 'wb') as f:
                        f.write(attachment_data)
                    attachments.append({
                        'filename': safe_filename,
                        'path': file_path,
                        'size': len(attachment_data)
                    })

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def get_text_from_html(html_content):
        """Convert HTML content to plain text."""
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text()

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """
            
        try:
            # Extract the email address and app password from the secrets
            email_address = secrets['email_address']
            app_password = secrets['app_password']
            # Attempt to establish a connection to the IMAP server
            imap_server = "imap.gmail.com"
            imap_port = 993
            with imaplib.IMAP4_SSL(imap_server, imap_port) as imap:
                imap.login(email_address, app_password)
                imap.select('inbox', readonly=True)
                Colors.printc("IMAP gmail tested!", Colors.OKGREEN)
            return None  # Return None if the test is successful
        except imaplib.IMAP4.error as imap_error:
            return f"IMAP login failed: {str(imap_error)}"
        except Exception as e:
            return f"An error occurred: {str(e)}"

# End of IMAPTool class

######################################################################################################
# Triggerable class 
#
from supercog.engine.tools.imap_poller import pollForGmail

class GmailPasswordTriggerable(Triggerable):
    def __init__(self, agent_dict: dict, run_state) -> None:
        super().__init__(agent_dict, run_state)
        matches = re.findall(r'\(([^)]+)\)', self.trigger) #FIXME: need better way to do this.

        if len(matches) >= 2:
            second_paren_contents = matches[1]  # 'Gmail for demos'
            self.cred_name = second_paren_contents
        else:
            print(f"search of trigger {self.trigger} yeilded {matches}")

    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        return trigger.startswith("IMAP")

    async def run(self):
        # Poll for events and dispatch them (run agents)
        print("Email Credentials: ",self.email_address, self.app_password)
        result = await pollForGmail(self.trigger_arg,
                                    self.tenant_id,
                                    self.user_id,
                                    self.agent_name,
                                    self.agent_id,
                                    self.email_address,
                                    self.app_password)
        return result


    def pick_credential(self, credentials) -> bool:
        # find a credential you can use for the trigger
        for cred in credentials:
            if (
                cred.name == self.cred_name and
                (cred.user_id == self.user_id or (
                    cred.tenant_id == self.tenant_id and
                    cred.scope == "shared"
                ))
            ):
                secrets = cred.retrieve_secrets()
                if 'email_address' not in secrets:
                    logger.error("Email cred {cred.name} has no email_address secret")
                    return False
                self.email_address = secrets['email_address']
                if 'app_password' not in secrets:
                    logger.error("Email cred {cred.name} has no app_password secret")
                    return False
                self.app_password = secrets['app_password']
                return True
        return False
