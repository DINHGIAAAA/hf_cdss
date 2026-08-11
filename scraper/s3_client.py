import os
import time

from botocore.config import Config
from botocore.exceptions import ClientError


def _retry_on_client_error(fn, max_attempts=3, base_delay=1.0):
    for attempt in range(max_attempts):
        try:
            return fn()
        except ClientError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


def s3_client(endpoint_url: str):
    import boto3

    return _retry_on_client_error(
        lambda: boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "testtest"),
            region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            config=Config(
                retries={"max_attempts": 0},
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
    )
