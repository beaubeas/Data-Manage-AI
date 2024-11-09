import aiofiles
import os
import json
from enum import StrEnum
import mimetypes
import re
import time
from typing import Optional
from enum import StrEnum

import markdown2
from bleach.sanitizer import Cleaner
import boto3
from botocore.exceptions import NoCredentialsError

from functools import reduce
from pathlib import Path

from .services import config

def get_boto_client(service):
    endpoint_url = config.get_global("AWS_ENDPOINT_WRITE_URL", required=False) or None
    return boto3.client(
        service,
        endpoint_url=endpoint_url, # If None it defaults to default aws endpoint_url
        aws_access_key_id=config.get_global("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=config.get_global("AWS_SECRET_KEY"),
        region_name="us-east-1",
        verify=(not bool(endpoint_url)) # Don't verify if there is an endpoint_url
    )

def dict_safe_get(src, *paths, default=None):
    """ Safely get a value from a nested dictionary. """
    try:
        return reduce(lambda d, k: d[k], paths, src)
    except KeyError:
        return default

content_path = Path('./content')

CONTENT_TAGS = {
    "CHANGELOG": "CHANGELOG.md",
    "STARTING": "GETTING_STARTED.md",
    "PERMISSIONS": "PERMISSIONS.md",
    "EMAIL_TRIGGER_HELP": "EMAIL_TRIGGER_HELP.md",
    "HELP": "help.md",
}

class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'  # This resets the color
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Bright (bold) foreground colors
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'

    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    
    # Bright (bold) background colors
    BG_BRIGHT_BLACK = '\033[100m'
    BG_BRIGHT_RED = '\033[101m'
    BG_BRIGHT_GREEN = '\033[102m'
    BG_BRIGHT_YELLOW = '\033[103m'
    BG_BRIGHT_BLUE = '\033[104m'
    BG_BRIGHT_MAGENTA = '\033[105m'
    BG_BRIGHT_CYAN = '\033[106m'
    BG_BRIGHT_WHITE = '\033[107m'
    
    @classmethod
    def printc(cls, text, color, end='\n'):
        # Print the text with the specified color and then reset the color to default
        print(f"{color}{text}{cls.ENDC}", end=end)
        
def load_file_content(path=None, tag=None) -> str:
    if tag and tag in CONTENT_TAGS:
        path = CONTENT_TAGS[tag]

    if path:
        path = content_path / path
        if os.path.exists(path):
            return open(path).read()
        else:
            return f"File not found: {path}"
    else:
        return "no path"
    
def markdown_to_html(markdown_content: str) -> str:
    # Convert Markdown to HTML
    html_content = markdown2.markdown(markdown_content)

    # Create a cleaner with only email-safe tags
    cleaner = Cleaner(tags=['a', 'p', 'br', 'strong', 'em', 'ul', 'ol', 'li','h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'img'])

    # Sanitize HTML
    return cleaner.clean(html_content)


class EMAIL_KEYS(StrEnum):
    PWRESET = "PWRESET"
    EMAIL_CONFIRM = "EMAIL_CONFIRM"

SUBJECTS = {
    EMAIL_KEYS.PWRESET: "Reset your password on supercog.ai",
    EMAIL_KEYS.EMAIL_CONFIRM: "Confirm your supercog.ai account",
}

def send_email(recipient: str, email_key: str, vars: dict):
    if email_key in SUBJECTS:
        subject = SUBJECTS[email_key]
    else:
        raise RuntimeError(f"No subject line defined for email key: {email_key}")
    content = load_file_content(path=email_key + ".md")
    content = content.format(**vars)

    html_content = markdown_to_html(content)
    # send html email
    print("Sending html email to", recipient, "with content:\n", html_content)
    send_mail_ses(config.get_email_sender(), recipient, subject, text_body=content,
                    html_body=html_content)

def send_mail_ses(
        from_addr: str, 
        recipient: str, 
        subject: str, 
        text_body: str|None=None, 
        html_body:str|None=None):
    dest = {'ToAddresses':[recipient]}
    body = {}
    if text_body:
        body['Text'] = {
            'Charset': 'UTF-8',
            'Data': text_body,
        }
    if html_body:
        body['Html'] = {
            'Charset': 'UTF-8',
            'Data': html_body,
        }
    msg = {
        'Body': body,
        'Subject': {
            'Charset': 'UTF-8',
            'Data':subject
        }
    }
    client = get_boto_client("ses")
    response = client.send_email(
        Source=from_addr,
        Destination=dest,
        Message=msg
    )
    if 'ResponseMetadata' in response:
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            return response['MessageId']
    
    raise RuntimeError("Failed to send email: ", json.dumps(response))


def calc_s3_url(s3_client, bucket_name: str, object_name: str) -> str:
    # If using minio format it as that url
    endpoint_url = config.get_global("AWS_ENDPOINT_READ_URL", required=False) or None
    if endpoint_url:
        return f"{endpoint_url}/{bucket_name}/{object_name}"

    region = s3_client.get_bucket_location(Bucket=bucket_name)['LocationConstraint']
    if region == 'us-east-1' or region is None:
        return f"https://{bucket_name}.s3.amazonaws.com/{object_name}"
    else:
        return f"https://{bucket_name}.s3.{region}.amazonaws.com/{object_name}"


def create_presigned_url(s3_client, bucket_name, object_name, expiration=3600) -> dict:
    """Generate a presigned URL to share an S3 object

    :param bucket_name: string
    :param object_name: string
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """
    # Create a session using your current creds
    try:
        metadata = s3_client.head_object(Bucket=bucket_name, Key=object_name)
        mime_type = metadata['ContentType']

        response = s3_client.generate_presigned_url('get_object',
                                                    Params={'Bucket': bucket_name,
                                                            'Key': object_name},
                                                    ExpiresIn=expiration)
    except NoCredentialsError:
        return {"error" : "Credentials not available"}
    except s3_client.exceptions.NoSuchKey:
        return {"error" : "The object does not exist."}
    
    # LOGIC HERE TO REPLACE
    # If there is a AWS_ENDPOINT_READ_URL then switch the beginning of the URL to match
    write_url = config.get_global("AWS_ENDPOINT_WRITE_URL", required=False) or None
    read_url = config.get_global("AWS_ENDPOINT_READ_URL", required=False) or None
    if read_url and write_url and response.startswith(write_url):
        response = response.replace(write_url, read_url, 1)

    return {"url": response, "mime_type": mime_type}

def upload_file_to_s3(file_obj, bucket_name=None, object_name=None, mime_type=None) -> str:
    """
    Upload a file to an S3 bucket
    :param file_obj: File to upload (can be a file path or a file-like object)
    :param bucket_name: Bucket to upload to
    :param object_name: S3 object name. If not specified, file_name is used
    :param mime_type: MIME type of the file
    :return: S3 URL of the uploaded file
    """
    if bucket_name is None:
        bucket_name = config.get_global("S3_PUBLIC_BUCKET")

    if isinstance(file_obj, str):
        file_name = file_obj
        if object_name is None:
            object_name = os.path.basename(file_name)
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(file_name)
    else:
        file_name = None
        if object_name is None:
            raise ValueError("object_name must be specified when file_obj is not a string")

    if mime_type is None:
        mime_type = "application/octet-stream"

    s3_client = get_boto_client("s3")

    try:
        if file_name is not None:
            s3_client.upload_file(
                file_name,
                bucket_name,
                object_name,
                ExtraArgs={'ContentType': mime_type}
            )
        else:
            s3_client.upload_fileobj(
                file_obj,
                Bucket=bucket_name,
                Key=object_name,
                ExtraArgs={'ContentType': mime_type}
            )
    except Exception as e:
        raise RuntimeError(f"File upload to S3 failed: {e}")

    return calc_s3_url(s3_client, bucket_name, object_name)
    
async def download_s3_file(bucket_name: str, object_name: str, output_path: str):
    if bucket_name is None:
        bucket_name = config.get_global("S3_PUBLIC_BUCKET")

    s3_client = get_boto_client("s3")
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=object_name)
        async with aiofiles.open(output_path, "wb") as out_file:
            for chunk in response['Body'].iter_chunks(1024 * 1024):
                await out_file.write(chunk)
            await out_file.flush()
    except Exception as e:
        raise RuntimeError(f"File download from S3 failed: {e}")

def upload_bytes_to_s3(
        object_name: str, 
        byteslist: bytes, 
        mime_type: str,
        bucket_name: str|None=None,
    ):
    s3_client = get_boto_client("s3")
    if bucket_name is None:
        bucket_name = config.get_global("S3_PUBLIC_BUCKET")

    try:
        _ = s3_client.put_object(
            Bucket=bucket_name,
            Key=object_name,
            Body=byteslist,
            ContentType=mime_type
        )
    except Exception as e:
        raise RuntimeError(f"Bytes upload to S3 failed: {e}")
    
    return calc_s3_url(s3_client, bucket_name or "", object_name)

def wait_for_deletion(s3_client, bucket_name, object_name, max_attempts=12):   
    attempts = 0
    while attempts < max_attempts:
        try:
            s3_client.head_object(Bucket=bucket_name, Key=object_name)
            print(f"File still exists. Waiting for 0.5 seconds before checking again.")
            time.sleep(0.5)
            attempts += 1
        except s3_client.exceptions.NoSuchKey:
            print("File successfully removed.")
            return True
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False
    
    print("File removal not reflected within the maximum attempts.")
    return False

def get_file_mimetype(file_name) -> str:
    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = "application/octet-stream"    
    return mime_type

def sanitize_string(value: str) -> str:
    return re.sub(r'\W|^(?=\d)', '_', value.lower()).replace(" ","_")

## Markdown parsing

class NodeTypes(StrEnum):
    HEADING1 = "h1"
    HEADING2 = "h2"
    CODE_BLOCK = "code"
    PARAGRAPH = "p"
#    STATE = "state"

class Node:
    tag: str
    content: str
    raw_content: str

    def __init__(self, tag: str, content: str, raw_content: str):
        self.tag = tag
        self.content = content
        self.raw_content = raw_content

    def __repr__(self):
        return f"<Node {self.tag}: {self.content}>"
        
NODE_REGEXP = {
    r"^#\s+(.*)" : NodeTypes.HEADING1,
    r"^##\s+(.*)": NodeTypes.HEADING2,
#    r"^\s*\[(.*)\]": NodeTypes.STATE,
}

BLOCK_STARTS = {
    r"^```(.*)$": (NodeTypes.CODE_BLOCK, r"(.*)```"),
    r"^(.*)$": (NodeTypes.PARAGRAPH, r"^\s*$"),
}


def scan_markdown(text: str):
    def matches_special(line:  str) -> bool:
        return (
            any(re.match(pattern, line) for pattern in NODE_REGEXP.keys()) or
            re.match(list(BLOCK_STARTS.keys())[0], line) is not None
        )
   
    lines = text.splitlines()
    current = 0
    para = ""

   
    while current < len(lines):
        line = lines[current]
        for pattern, node_type in NODE_REGEXP.items():
            match = re.search(pattern, line)
            if match:
                yield Node(node_type, match.group(1).strip(), line)
                break
        else:
            block = ""
            for pattern, (node_type, end_pattern) in BLOCK_STARTS.items():
                match = re.search(pattern, line)
                if match:
                    block += match.group(1)
                    while current < len(lines):
                        current += 1
                        if current >= len(lines):
                            yield Node(node_type, block, block)
                            return
                        line = lines[current]
                        if match := re.match(end_pattern, line):
                            try:
                                block += match.group(1)
                            except IndexError:
                                pass
                            yield Node(node_type, block, block)
                            break
                        elif matches_special(line):
                            # implicitly close current block
                            yield Node(node_type, block, block)
                            current -= 1 # backup and return to main loop
                            break
                        else:
                            block += "\n" + line
                    break

        current += 1

def parse_markdown(text: str) -> list[Node]:
    return list(scan_markdown(text))

