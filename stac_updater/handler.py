import json
import os
from pathlib import Path

from satstac import Collection, Item
import boto3

from stac_updater import names

sns_client = boto3.client('sns')
lambda_client = boto3.client('lambda')

ACCOUNT_ID = boto3.client('sts').get_caller_identity()['Account']
REGION = os.getenv('REGION')
CAT_ROOT = os.getenv('CAT_ROOT_URL')
ITEM_PATH = os.getenv('ITEM_PATH')
ITEM_NAME = os.getenv('ITEM_NAME')
DYNAMIC_INGEST_ARN = os.getenv('INGEST_ARN')


def kickoff(event, context):
    # Sends the stac item to the SNS Topic, kicking off update pipeline.
    stac_item = json.loads(event)

    sns_client.publish(
        TopicArn=f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:{names.sns_topic}",
        message=stac_item
    )

def staticStacUpdater(event, context):

    """
    Lambda function to update static catalogs by reading the collection path from the item's links.  Assumes that the
    STAC item is a part of a collection and that collection already exists within the catalog.

    Uses the `path` and `filename` parameters in sat_stac.Collection.add_item to build out catalog.
    """

    for record in event['Records']:
        stac_item = record['body']

        # Determine collection path from stac item links
        links = {}
        for link in stac_item['links']:
            if link['rel'] == 'collection':
                links.update({'collection': link['href']})
            elif link['rel'] == 'self':
                links.update({'self': link['href']})
        item_path = Path(links['self']).parent
        collection_path = (item_path / links['collection']).resolve()
        collection_path = 'https://' + str(collection_path).split('https:/')[-1]

        # Open collection and save STAC Item
        col = Collection.open(collection_path)
        item = Item(stac_item)

        kwargs = {'item': item}
        if ITEM_PATH:
            kwargs.update({'path': ITEM_PATH})
        if ITEM_NAME:
            kwargs.update({'filename': ITEM_NAME})
        col.add_item(**kwargs)
        col.save()

def dynamicStacUpdater(event, context):

    """
    Lambda function to update dynamic catalogs by passing each STAC Item in the queue to the ingest handler used by
    the dynamic catalog.
    """

    for record in event['Records']:
        stac_item = record['body']

        lambda_client.invoke(
            FunctionName=DYNAMIC_INGEST_ARN,
            InvocationType='Event',
            Payload=json.dumps(stac_item)
        )