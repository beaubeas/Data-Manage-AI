import os
import boto3

from supercog.shared.services import config
from supercog.shared.utils import upload_file_to_s3, get_boto_client, calc_s3_url

def get_file_from_s3(tenant_id, folder_name, file_name):
    os.chdir('/tmp')
    s3_client = get_boto_client('s3')

    bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
    object_name = f"{tenant_id}/{folder_name}/{file_name}"

    try:
        s3_client.download_file(bucket_name, object_name, file_name)
    except Exception as e:
        raise RuntimeError(f"File not found in S3: {e}")

def put_file_to_s3(tenant_id, folder_name, file_name):
    os.chdir('/tmp')
    bucket_name = config.get_global("S3_FILES_BUCKET_NAME")
    object_name = f"{tenant_id}/{folder_name}/{file_name}"

    upload_file_to_s3(
        file_name, 
        bucket_name,
        object_name
    )

def list_files(tenant_id: str, folder: str):
    s3 = get_boto_client('s3')
    prefix = f"{tenant_id}/{folder}/"

    bucket_name = config.get_global("S3_FILES_BUCKET_NAME") or ""
  
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    # Print out the files contained in the folder
    files: list[dict] = []
    if 'Contents' in response:
        files = []
        for file in response['Contents']:
            val = file['Key']
            if val.startswith(prefix):
                val = val[len(prefix):]
            url = calc_s3_url(s3, bucket_name, file['Key'])
            files.append({"name": val, "size": file['Size'], "url": url})
    return sorted(files, key=lambda x: x['name'])

def public_image_bucket() -> str:
    return config.get_global("S3_PUBLIC_BUCKET")
