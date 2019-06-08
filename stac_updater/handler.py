import json
import os
from pathlib import Path

from satstac import Collection, Item
import boto3

from stac_updater import names

sns_client = boto3.client('sns')

ACCOUNT_ID = boto3.client('sts').get_caller_identity()['Account']
REGION = os.getenv('REGION')
CAT_ROOT = os.getenv('CAT_ROOT_URL')
ITEM_PATH = os.getenv('ITEM_PATH')
ITEM_NAME = os.getenv('ITEM_NAME')


def kickoff(event, context):
    # Sends the stac item to the SNS Topic, kicking off update pipeline.
    stac_item = json.loads(event)

    sns_client.publish(
        TopicArn=f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:{names.sns_topic}",
        message=stac_item
    )

def static_stac_updater(event, context):

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