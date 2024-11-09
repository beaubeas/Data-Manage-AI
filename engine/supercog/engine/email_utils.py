import email
from email.header import decode_header
from bs4 import BeautifulSoup
from typing import Dict, Any
import os
import re

def process_email(email_message: email.message.EmailMessage,
                  agent_dir: str,
                  run_context) -> Dict[str, Any]:
    """
    Process an email message, extracting subject, sender, date, body, and attachments.
    """
    subject = decode_email_header(email_message['subject'])
    sender = decode_email_header(email_message['from'])
    date = email_message['date']
    to = email_message['To']

    body = {'plain': '', 'html': ''}
    attachments = []

    for part in email_message.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition"))

        if content_type == "text/plain" and "attachment" not in content_disposition:
            body['plain'] += decode_email_body(part)
        elif content_type == "text/html" and "attachment" not in content_disposition:
            body['html'] += decode_email_body(part)
        elif "attachment" in content_disposition or "inline" in content_disposition:
            filename = part.get_filename()
            if filename:
                attachment_data = part.get_payload(decode=True)
                safe_filename = get_safe_filename(filename, agent_dir)
                file_path = os.path.join(agent_dir, safe_filename)
                with open(file_path, 'wb') as f:
                    f.write(attachment_data)
                
                # Upload to S3 and get download URL
                #s3_path = run_context.upload_user_file_to_s3(
                #    file_name=file_path,
                #    mime_type=content_type
                #)
                #download_url = run_context.get_file_url(safe_filename)
                
                attachments.append({
                    'filename': safe_filename,
                    'path': file_path,
                    'size': len(attachment_data),
                    #'s3_path': s3_path,
                    #'download_url': download_url.get("url", "")
                })

    if body['html']:
        body['plain'] += get_text_from_html(body['html'])

    return {
        'subject': subject,
        'sender': sender,
        'to': to,
        'date': date,
        'body': body,
        'attachments': attachments
    }

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
