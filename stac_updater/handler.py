import json
import os

import boto3

from stac_updater import names

sns_client = boto3.client('sns')

ACCOUNT_ID = boto3.client('sts').get_caller_identity()['Account']
REGION = os.getenv('REGION')
CAT_ROOT = os.getenv('CAT_ROOT_URL')


def kickoff(event, context):
    # Sends the stac item to the SNS Topic, kicking off update pipeline.
    stac_item = json.loads(event)

    sns_client.publish(
        TopicArn=f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:{names.sns_topic}",
        message=stac_item
    )
