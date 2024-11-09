
from typing import Callable, Dict, Any, Optional

import os
import pandas as pd
import asyncio
import json
import re
import boto3
from urllib.parse import urlparse, unquote_plus, unquote
import pytextract
import requests
import chardet
import PyPDF2
from io import BytesIO

import boto3
from botocore.exceptions import ClientError

from supercog.engine.tool_factory import ToolFactory, ToolCategory, LLMFullResult
from supercog.engine.triggerable import Triggerable
from supercog.shared.logging import logger
from supercog.shared.utils import upload_file_to_s3, get_boto_client, calc_s3_url
from supercog.engine.file_utils import read_pdf, read_eml

KEY_ID = 'AWS_ACCESS_KEY_ID'
SECRET_KEY = 'AWS_SECRET_ACCESS_KEY'

class S3Tool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="s3_connector",
            system_name="Amazon S3",
            logo_url=super().logo_from_domain("amazonaws.com"),
            category=ToolCategory.CATEGORY_FILES,
            help = """
Manage S3: list, upload, download, delete, and copy files.
""",
            auth_config={
                "strategy_token": {
                    "AWS_ACCESS_KEY_ID": "Your AWS Access Key ID",
                    "AWS_SECRET_ACCESS_KEY": "Your AWS Secret Access Key",
                    "help": "Configure your AWS credentials to access S3."
                }
            }
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.list_s3_buckets,
            self.upload_file_to_s3,
            self.download_file_from_s3,
            self.list_files_in_bucket,
            self.delete_file_from_s3,
            self.copy_file_within_s3,
            self.get_file_metadata,
            self.create_presigned_url,
            self.read_file_from_s3,
        ])

    def validate_creds(self):
        print("S3 VALIDATING CREDS, credentials: ", self.credentials)
        if KEY_ID not in self.credentials:
            raise RuntimeError("Error: AWS Access Key ID not provided.")
        if SECRET_KEY not in self.credentials:
            raise RuntimeError("Error: AWS Secret Access Key not provided.")
        
    def list_s3_buckets(self) -> list[str]:
        """ List the S3 buckets available to the given credentials. """
        self.validate_creds()

        s3_client = boto3.client(
            's3',
            aws_access_key_id=self.credentials[KEY_ID],
            aws_secret_access_key=self.credentials[SECRET_KEY]
        )
        response = s3_client.list_buckets()
        buckets = [bucket['Name'] for bucket in response['Buckets']]
        return buckets

    def list_files_in_bucket(self, bucket_name: str, prefix:str = "", return_rows:int = 5) -> dict:
        """ List the files available in the indicated bucket. If prefix is provided then only
            files with the given prefix will be returned. """
        s3_client = boto3.client(
            's3',
            aws_access_key_id=self.credentials[KEY_ID],
            aws_secret_access_key=self.credentials[SECRET_KEY]
        )
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

        # Print out the files contained in the folder
        files: list[dict] = []
        if 'Contents' in response:
            files = []
            for file in response['Contents']:
                val = file['Key']
                print(val)
                if prefix and not val.startswith(prefix):
                    continue
                elif not prefix and '/' in val and not val.endswith('/'):
                    continue
                print("Keeping val: ", val)
                url = calc_s3_url(s3_client, bucket_name, file['Key'])
                files.append({"name": val, "size": file['Size'], "url": url})
        files = sorted(files, key=lambda x: x['name'])
        df = pd.DataFrame(files)
        return self.get_dataframe_preview(
            df, 
            max_rows=return_rows, 
            name_hint=bucket_name, 
            sanitize_column_names=False
        )

    def read_file_from_s3(self, identifier_type: str, identifier: str):
        """
        Returns the contents of the given file from S3.

        This function handles different file types and formats, including:
        - S3 URLs: Reads the file directly from S3.
        - Excel files (.xlsx): Reads the content into a DataFrame and returns a preview.
        - PDF files (.pdf): Extracts text from all pages using the shared utility.
        - EML files (.eml): Parses email content, saves attachments, and returns a structured representation.
        - Other file types: Attempts to extract content using the pytextract library.

        Args:
            identifier_type (str): One of 'URI', 'ARN', or 'URL'.
            identifier (str): The identifier corresponding to the specified type.

        Returns:
            dict: A dictionary containing the file content or error information.
        """
        logger.info(f"Attempting to read file with {identifier_type}: {identifier}")

        try:
            s3_client = boto3.client('s3',
                                     aws_access_key_id=self.credentials[KEY_ID],
                                     aws_secret_access_key=self.credentials[SECRET_KEY],
                                     region_name='us-east-2'  # Ensure this is the correct region
            )
            logger.debug("S3 client initialized")

            if identifier_type == 'ETag':
                bucket, key = self._find_object_by_etag(s3_client, identifier)
                if not bucket or not key:
                    return {"status": "error", "message": f"No object found with ETag: {identifier}"}
            else:
                bucket, key = self._parse_identifier(identifier_type, identifier)
                if not bucket or not key:
                    return {
                        "status": "error",
                        "message": f"Unable to parse bucket and key from {identifier_type}: {identifier}"
                    }

            logger.info(f"Parsed S3 identifier - Bucket: {bucket}, Key: {key}")

            # Check if the object exists
            try:
                s3_client.head_object(Bucket=bucket, Key=key)
            except ClientError as e:
                if e.response['Error']['Code'] == "404":
                    logger.error(f"The object does not exist. Bucket: {bucket}, Key: {key}")
                    return {"status": "error", "message": f"The specified file does not exist: {key}"}
                else:
                    raise

            # Get the object from S3
            logger.info(f"Fetching object from S3 - Bucket: {bucket}, Key: {key}")
            response = s3_client.get_object(Bucket=bucket, Key=key)
            content = response['Body'].read()
            content_type = response.get('ContentType', '')
            logger.info(f"Object fetched successfully. Content Type: {content_type}, Size: {len(content)} bytes")

            # Process the content based on file type

            # EXCEL
            if key.lower().endswith('.xlsx'):
                return self._process_excel(content)
            # PDF
            elif key.lower().endswith('.pdf'):
                return LLMFullResult(read_pdf(BytesIO(content)))
            # Emails
            elif key.lower().endswith('.eml'):
                agent_dir = self.run_context.create_agent_directory()
                return LLMFullResult(read_eml(BytesIO(content), agent_dir, self.run_context))
            # TEXT
            elif 'text' in content_type.lower():
                return self._process_text(content)
            # OTHER
            else:
                return self._process_other(content, content_type)

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"AWS ClientError reading file from S3: {error_code} - {error_message}")
            return {"status": "error", "message": f"{error_code} - {error_message}"}
        except Exception as e:
            logger.error(f"Unexpected error reading file from S3: {str(e)}")
            return {"status": "error", "message": f"Unexpected error: {str(e)}"}

    def _find_object_by_etag(self, s3_client, etag: str) -> Optional[tuple[str, str]]:
        """
        Finds an object in any bucket with the specified ETag.

        Args:
            s3_client: The boto3 S3 client.
            etag (str): The ETag to search for.

        Returns:
            Optional[tuple[str, str]]: A tuple containing the bucket name and key of the object if found, None otherwise.
        """
        buckets = self.list_s3_buckets()
        for bucket in buckets:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket):
                for obj in page.get('Contents', []):
                    if obj['ETag'].strip('"') == etag.strip('"'):
                        return bucket, obj['Key']
        return None

    def _parse_identifier(self, identifier_type: str, identifier: str) -> Optional[tuple[str, str]]:
        """
        Parses the given identifier based on its type and returns the bucket and key.

        Args:
            identifier_type (str): The type of identifier ('URI', 'ARN', or 'URL').
            identifier (str): The identifier string.

        Returns:
            Optional[tuple[str, str]]: A tuple containing the bucket name and key, or None if parsing fails.
        """
        if identifier_type == 'URI':
            parts = identifier.split('/', 3)
            return parts[2], parts[3] if len(parts) > 3 else ''
        elif identifier_type == 'ARN':
            match = re.match(r'arn:aws:s3:::([^/]+)/?(.*)$', identifier)
            if match:
                bucket, key = match.groups()
                return bucket, key
        elif identifier_type == 'URL':
            parsed_url = urlparse(identifier)
            bucket = parsed_url.netloc.split('.s3.')[0]
            key = unquote_plus(parsed_url.path.lstrip('/'))
            return bucket, key
        
        logger.error(f"Unsupported identifier type: {identifier_type}")
        return None

    def _process_excel(self, content):
        logger.info("Processing Excel file")
        df = pd.read_excel(BytesIO(content), engine='openpyxl')
        logger.debug(f"Excel file read into DataFrame. Shape: {df.shape}")
        return self.get_dataframe_preview(df)

    def _process_text(self, content):
        logger.info("Processing text file")
        text_content = content.decode('utf-8')
        logger.debug(f"Text file decoded. Length: {len(text_content)} characters")
        return text_content

    def _process_other(self, content, content_type):
        logger.info(f"Processing file with content type: {content_type}")
        try:
            logger.debug("Attempting to process with pytextract")
            extracted_content = pytextract.process(BytesIO(content))
            logger.info("Successfully processed with pytextract")
            return extracted_content
        except Exception as pytextract_error:
            logger.warn(f"pytextract processing failed: {str(pytextract_error)}")
            logger.debug("Falling back to basic content decoding")
            result = chardet.detect(content)
            encoding = result['encoding']
            logger.info(f"Detected encoding: {encoding}")
            if encoding is None:
                logger.warn("No encoding detected, using UTF-8 with error replacement")
                return content.decode('utf-8', errors='replace')
            try:
                decoded_content = content.decode(encoding)
                logger.info(f"Content successfully decoded using {encoding}")
                return decoded_content
            except UnicodeDecodeError as decode_error:
                logger.warn(f"Decoding with {encoding} failed: {str(decode_error)}")
                logger.info("Falling back to UTF-8 decoding with error replacement")
                return content.decode(encoding, errors='replace')

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"AWS ClientError reading file from S3: {error_code} - {error_message}")
            return f"Error: {error_code} - {error_message}"
        except Exception as e:
            logger.error(f"Unexpected error reading file from S3: {str(e)}")
            return f"Unexpected error: {str(e)}"

    def _read_pdf_content(self, file_obj):
        """
        Reads a PDF file and extracts text from all pages.

        Args:
            file_obj (BytesIO): The PDF file object.

        Returns:
            str: The extracted text from all pages of the PDF.
        """
        logger.info("Starting PDF content extraction")
        pdf_reader = PyPDF2.PdfReader(file_obj)
        logger.debug(f"PDF has {len(pdf_reader.pages)} pages")
        text = ""
        for i, page in enumerate(pdf_reader.pages):
            logger.debug(f"Extracting text from page {i+1}")
            page_text = page.extract_text()
            text += page_text + "\n"
            logger.debug(f"Extracted {len(page_text)} characters from page {i+1}")
        logger.info(f"PDF extraction complete. Total extracted text length: {len(text)} characters")
        return text
    
    def upload_file_to_s3(self, bucket_name: str, file_path: str, object_name: str|None=None):
        """ Uploads the give file to the indicated S3 bucket. Uses the file name or the indicated
            object name if provided. """
        s3_client = boto3.client(
            's3',
            aws_access_key_id=self.credentials[KEY_ID],
            aws_secret_access_key=self.credentials[SECRET_KEY]
        )
        object_name = object_name or os.path.basename(file_path)
        s3_client.upload_file(file_path, bucket_name, object_name)
        return {"status": "success", "message": "File uploaded successfully"}

    def download_file_from_s3(self, bucket_name: str = None, object_name: str = None, s3_url: str = None):
        """
        Downloads a file from S3. Accepts either bucket_name and object_name, or a full S3 URL.
        Handles special characters and spaces in object names.
        
        Args:
            bucket_name (str, optional): The name of the S3 bucket.
            object_name (str, optional): The name of the object in the bucket.
            s3_url (str, optional): Full S3 URL of the object.
        
        Returns:
            dict: A dictionary containing the status and a message.
        """
        try:
            if s3_url:
                parsed_url = urlparse(s3_url)
                bucket_name = parsed_url.netloc.split('.')[0]
                object_name = unquote_plus(parsed_url.path.lstrip('/'))
            else:
                object_name = unquote_plus(object_name)

            if not bucket_name or not object_name:
                return {"status": "error", "message": "Either provide both bucket_name and object_name, or a valid S3 URL"}

            s3_client = boto3.client(
                's3',
                aws_access_key_id=self.credentials['AWS_ACCESS_KEY_ID'],
                aws_secret_access_key=self.credentials['AWS_SECRET_ACCESS_KEY']
            )

            file_name = object_name.split('/')[-1]  # Use the last part of the path as file name

            # First, try to download the file as is
            try:
                s3_client.download_file(bucket_name, object_name, file_name)
                return {"status": "success", "message": f"File {file_name} downloaded successfully"}
            except ClientError as e:
                if e.response['Error']['Code'] == "404":
                    # If file not found, try to find a similar file name
                    similar_object = self._find_similar_object(s3_client, bucket_name, object_name)
                    if similar_object:
                        s3_client.download_file(bucket_name, similar_object, similar_object.split('/')[-1])
                        return {"status": "success", "message": f"File {similar_object} downloaded successfully (similar name found)"}
                    else:
                        return {"status": "error", "message": f"The object {object_name} does not exist in bucket {bucket_name} and no similar object was found"}
                else:
                    raise

        except KeyError as e:
            return {"status": "error", "message": f"Missing credential: {str(e)}"}
        except ClientError as e:
            return {"status": "error", "message": f"An error occurred: {str(e)}"}
        except Exception as e:
            return {"status": "error", "message": f"An unexpected error occurred: {str(e)}"}

    def _find_similar_object(self, s3_client, bucket_name: str, object_name: str) -> str or None:
        """
        Attempts to find an object with a similar name in the given bucket.
        
        Args:
            s3_client: The boto3 S3 client
            bucket_name (str): The name of the S3 bucket
            object_name (str): The name of the object to find

        Returns:
            str or None: The name of a similar object if found, None otherwise
        """
        try:
            # List objects in the bucket
            response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=object_name.split('/')[0])
            
            if 'Contents' in response:
                # Create a list of object keys
                object_keys = [obj['Key'] for obj in response['Contents']]
                
                # Function to calculate similarity
                def similarity(s1, s2):
                    return sum(a == b for a, b in zip(s1, s2)) / max(len(s1), len(s2))
                
                # Find the most similar object key
                most_similar = max(object_keys, key=lambda x: similarity(x, object_name))
                
                # If the similarity is above a threshold, return the similar object key
                if similarity(most_similar, object_name) > 0.8:  # You can adjust this threshold
                    return most_similar

        except ClientError:
            pass  # If there's an error listing objects, we'll just return None
        
        return None



    def copy_file_within_s3(self,
                        source_bucket_name: str,
                        source_object_name: str,
                        destination_bucket_name: str,
                        destination_object_name: str):
        """
        Copies a file from one location to another within Amazon S3.

        Parameters:
        source_bucket_name (str): The name of the S3 bucket where the source file is located.
        source_object_name (str): The name of the source file (object key) to be copied.
        destination_bucket_name (str): The name of the S3 bucket where the file should be copied to.
        destination_object_name (str): The name of the destination file (object key) in the target bucket.

        Returns:
        dict: A dictionary containing the status of the operation and a message with details.

        Notes:
        - Ensure that the AWS credentials (aws_access_key_id and aws_secret_access_key) are
        - correctly set in self.credentials.
        - Both the source and destination buckets must be accessible with the provided AWS credentials.

        """

        s3_client = boto3.client('s3',
            aws_access_key_id=self.credentials[KEY_ID],
            aws_secret_access_key=self.credentials[SECRET_KEY]
        )
        copy_source = {'Bucket': source_bucket_name, 'Key': source_object_name}
        s3_client.copy_object(CopySource=copy_source, Bucket=destination_bucket_name, Key=destination_object_name)
        return {"status": "success", "message":
                f"File copied from {source_bucket_name}/{source_object_name}"+
                f" to {destination_bucket_name}/{destination_object_name}"}
    
    def delete_file_from_s3(self, bucket_name: str, object_name: str):
        """
        Delete a file from an S3 bucket.

        Args:
            bucket_name (str): The name of the S3 bucket.
            object_name (str): The key of the object to delete in the bucket.

        Returns:
            dict: A dictionary containing the status and a message confirming deletion.

        Raises:
            botocore.exceptions.ClientError: If there's an error deleting the object.
        """
        s3_client = boto3.client('s3',
                                 aws_access_key_id=self.credentials[KEY_ID],
                                 aws_secret_access_key=self.credentials[SECRET_KEY])
        s3_client.delete_object(Bucket=bucket_name, Key=object_name)
        return {"status": "success", "message": f"File {object_name} deleted successfully"}
    
    def get_file_metadata(self, bucket_name: str, object_name: str):
        """
        Retrieve metadata for a file in an S3 bucket.

        Args:
            bucket_name (str): The name of the S3 bucket.
            object_name (str): The key of the object in the bucket.

        Returns:
            dict: A dictionary containing the metadata of the specified object.

        Raises:
            botocore.exceptions.ClientError: If there's an error retrieving the metadata.
        """
        s3_client = boto3.client('s3',
                                 aws_access_key_id=self.credentials[KEY_ID],
                                 aws_secret_access_key=self.credentials[SECRET_KEY])
        response = s3_client.head_object(Bucket=bucket_name, Key=object_name)
        return response['Metadata']

    def create_presigned_url(self, bucket_name: str, object_name: str, expiration=3600):
        """
        Generate a presigned URL for an object in an S3 bucket.

        Args:
            bucket_name (str): The name of the S3 bucket.
            object_name (str): The key of the object in the bucket.
            expiration (int, optional): Time in seconds for the presigned URL to remain valid.
                                        Defaults to 3600 seconds (1 hour).

        Returns:
            dict: A dictionary containing the status and the generated presigned URL.

        Raises:
            botocore.exceptions.ClientError: If there's an error generating the presigned URL.
        """
        s3_client = boto3.client('s3',
                                 aws_access_key_id=self.credentials[KEY_ID],
                                 aws_secret_access_key=self.credentials[SECRET_KEY])
        url = s3_client.generate_presigned_url('get_object',
                                               Params={'Bucket': bucket_name, 'Key': object_name},
                                               ExpiresIn=expiration)
        return {"status": "success", "url": url}

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """

        if KEY_ID not in secrets:
            return "Error: AWS Access Key ID not provided."
        if SECRET_KEY not in secrets:
            return "Error: AWS Secret Access Key not provided"
        
        print("Secrets:  ", secrets)
        s3_client = boto3.client(
            's3',
            aws_access_key_id=secrets[KEY_ID],
            aws_secret_access_key=secrets[SECRET_KEY]
        )
        try:
            # Use head_bucket on a known bucket, or list_buckets_v2 with max_keys=0
            s3_client.list_buckets()
            return None
        except ClientError as e:
            print(e)
            return f"Error: {e.response['Error']}"


######################################################################################################
# Triggerable class 
#

class S3Triggerable(Triggerable):
    def __init__(self, agent_dict: dict, run_state) -> None:
        super().__init__(agent_dict, run_state)
        self.run_state = run_state
        self.bucket_name = None
        self.queue_arn = None
        self.cred_name = None
        self.s3_client = None
        self.sqs_client = None
        self.sqs_queue_url = None
        self.is_valid = False

        try:
            logger.info(f"Initializing S3Triggerable with trigger_arg: {self.trigger_arg}")
            self.bucket_name, self.queue_arn = self._parse_trigger_arg(self.trigger_arg)
            self.cred_name = self.trigger.split('(')[1].split(')')[0]
            logger.info(f"Credential name: {self.cred_name}")
            self.is_valid = True
        except ValueError as e:
            logger.error(f"Error initializing S3Triggerable: {e}")

    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        return trigger.startswith("Amazon")

    def pick_credential(self, credentials: list) -> bool:
        logger.info(f"Picking credential for {self.cred_name}")
        for cred in credentials:
            if (cred.name == self.cred_name and 
                (cred.user_id == self.user_id or (
                    cred.tenant_id == self.tenant_id and
                    cred.scope == "shared"
                ))
            ):
                secrets = cred.retrieve_secrets()
                if 'AWS_ACCESS_KEY_ID' not in secrets or 'AWS_SECRET_ACCESS_KEY' not in secrets:
                    logger.error(f"S3 cred {cred.name} is missing required secrets")
                    return False
                self.aws_access_key_id = secrets['AWS_ACCESS_KEY_ID']
                self.aws_secret_access_key = secrets['AWS_SECRET_ACCESS_KEY']
                self.aws_region = 'us-east-2'
                logger.info(f"Picked credential: {cred.name}, Region: {self.aws_region}")
                return True
        logger.error(f"No matching credential found for {self.cred_name}")
        return False

    @staticmethod
    def _parse_trigger_arg(trigger_arg):
        logger.info(f"Parsing trigger arg: {trigger_arg}")
        parts = trigger_arg.split()
        if len(parts) != 2:
            logger.error(f"Invalid trigger arg format: {trigger_arg}")
            raise ValueError("Trigger arg must contain bucket name and queue ARN separated by space")
        
        bucket_name = S3Triggerable._extract_bucket_name(parts[0])
        queue_arn = parts[1]
        
        logger.info(f"Parsed bucket name: {bucket_name}")
        logger.info(f"Parsed queue ARN: {queue_arn}")
        
        arn_pattern = r'^arn:aws:sqs:[a-z0-9-]+:\d{12}:[a-zA-Z0-9-_]+(.fifo)?$'
        if not re.match(arn_pattern, queue_arn):
            logger.error(f"Invalid queue ARN format: {queue_arn}")
            raise ValueError(f"Invalid queue ARN format: {queue_arn}")
        
        logger.info(f"Queue ARN validation passed: {queue_arn}")
        return bucket_name, queue_arn
    
    @staticmethod
    def _extract_bucket_name(bucket_identifier):
        logger.info(f"Extracting bucket name from: {bucket_identifier}")
        # Check if the identifier is an ARN
        arn_pattern = r'arn:aws:s3:::([a-zA-Z0-9.\-_]{1,255})$'
        arn_match = re.match(arn_pattern, bucket_identifier)
        if arn_match:
            bucket_name = arn_match.group(1)
            logger.info(f"Extracted bucket name from ARN: {bucket_name}")
            return bucket_name
        
        # Check if it's a valid bucket name
        bucket_pattern = r'^[a-zA-Z0-9.\-_]{1,255}$'
        if re.match(bucket_pattern, bucket_identifier):
            logger.info(f"Valid bucket name: {bucket_identifier}")
            return bucket_identifier
        
        logger.error(f"Invalid bucket identifier: {bucket_identifier}")
        raise ValueError(f"Invalid bucket identifier: {bucket_identifier}")

    async def run(self):
        if not self.is_valid:
            logger.error("Cannot run S3Triggerable due to initialization errors")
            return

        try:
            await self._run()
        except Exception as e:
            logger.error(f"Error running S3 trigger: {e}")

    async def _run(self):
        logger.info("Starting S3Triggerable._run()")
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
            )
            self.sqs_client = boto3.client(
                'sqs',
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.aws_region,
            )
            logger.info("Created S3 and SQS clients")

            # Get the queue URL from the ARN
            queue_name = self.queue_arn.split(':')[-1]
            logger.info(f"Getting queue URL for queue name: {queue_name}")
            response = self.sqs_client.get_queue_url(QueueName=queue_name)
            self.sqs_queue_url = response['QueueUrl']
            logger.info(f"Queue URL: {self.sqs_queue_url}")

            try:
                await self._setup_s3_event_notification()
                logger.info("S3 event notification setup complete")
                while await self.run_state.is_running():
                    await self._poll_sqs_queue()
                    await asyncio.sleep(1)  # Adjust the polling interval as needed
            except Exception as e:
                logger.error(f"Error in S3 trigger main loop: {e}")
            finally:
                await self._cleanup_s3_event_notification()
        except Exception as e:
            logger.error(f"Error in S3Triggerable._run(): {e}")

    async def _setup_s3_event_notification(self):
        logger.info(f"Setting up S3 event notification for bucket: {self.bucket_name}")
        try:
            notification_configuration = {
                'QueueConfigurations': [
                    {
                        'QueueArn': self.queue_arn,
                        'Events': ['s3:ObjectCreated:*']
                    }
                ]
            }
            self.s3_client.put_bucket_notification_configuration(
                Bucket=self.bucket_name,
                NotificationConfiguration=notification_configuration
            )
            logger.info(f"Successfully set up S3 event notification for bucket: {self.bucket_name}")
        except ClientError as e:
            logger.error(f"ClientError setting up S3 event notification: {e}")
            raise
        
    async def _cleanup_s3_event_notification(self):
        logger.info(f"Cleaning up S3 event notification for bucket: {self.bucket_name}")
        try:
            self.s3_client.put_bucket_notification_configuration(
                Bucket=self.bucket_name,
                NotificationConfiguration={}
            )
            logger.info(f"Successfully cleaned up S3 event notification for bucket: {self.bucket_name}")
        except ClientError as e:
            logger.error(f"Error cleaning up S3 event notification: {e}")


    async def _poll_sqs_queue(self):
        logger.info(f"Polling SQS queue: {self.sqs_queue_url}")
        try:
            response = self.sqs_client.receive_message(
                QueueUrl=self.sqs_queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=10
            )

            messages = response.get('Messages', [])
            logger.info(f"Received {len(messages)} messages from SQS")

            for message in messages:
                logger.info(f"Processing message: {message['MessageId']}")
                try:
                    message_body = json.loads(message['Body'])
                    
                    # Ignore test events
                    if 'Event' in message_body and message_body['Event'] == 's3:TestEvent':
                        logger.debug("Ignoring S3 test event")
                    elif 'Records' in message_body:
                        for record in message_body['Records']:
                            await self.process_s3_event(record)
                    else:
                        logger.info(f"Unexpected message format: {json.dumps(message_body, indent=2)}")

                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON: {e}")
                except KeyError as e:
                    logger.error(f"KeyError processing message: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error processing message: {e}")

                # Delete the processed message
                self.sqs_client.delete_message(
                    QueueUrl=self.sqs_queue_url,
                    ReceiptHandle=message['ReceiptHandle']
                )
                logger.debug(f"Deleted message: {message['MessageId']}")

        except ClientError as e:
            logger.error(f"Error polling SQS queue: {e}")

    async def process_s3_event(self, record):
        logger.info(f"Processing S3 event: {json.dumps(record, indent=2)}")
        if (record.get('eventSource')   == 'aws:s3' and
            record.get('eventName', '').startswith('ObjectCreated:')):
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            logger.info(f"New file detected: {key} in bucket {bucket}")

            # Trigger the agent with the new file information
            run_data = {
                'bucket': bucket,
                'key': key,
                'event_type': record['eventName'],
                'file_size': record['s3']['object']['size'],
                'etag': record['s3']['object']['eTag']
            }
            logger.info(f"Creating run with data: {run_data}")
            try:
                self.create_run(run_data)
                logger.info(f"Successfully created run for file: {key}")
            except Exception as e:
                logger.error(f"Error creating run for file {key}: {str(e)}")
        else:
            logger.info(f"Skipping non-ObjectCreated event: {record.get('eventName')}")

    async def cancel(self):
        logger.info("Cancelling S3Triggerable")
        await self._cleanup_s3_event_notification()
        self.run_state.stop()
        logger.info("S3Triggerable cancelled")


