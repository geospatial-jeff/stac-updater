import os
import json

from satstac import Collection, Item
import boto3

sns_client = boto3.client('sns')

ACCOUNT_ID = boto3.client('sts').get_caller_identity()['Account']
REGION = os.getenv('REGION')


def kickoff(event, context):

    try:
        coll_name = event['stac_item']['properties']['collection']
    except KeyError:
        coll_name = event['stac_item']['collection']

    sns_client.publish(
        TopicArn=f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:newStacItemTopic",
        Message=json.dumps(event),
        MessageAttributes={
            'collection': {
                'DataType': 'String',
                'StringValue': coll_name
            }
        }
    )


def update_collection(event, context):
    collection_root = os.getenv('COLLECTION_ROOT')

    for record in event['Records']:
        message = json.loads(record['body'])

        col = Collection.open(collection_root)
        kwargs = {'item': Item(message['stac_item'])}
        if 'path' in message:
            kwargs.update({'path': message['path']})
        if 'filename' in message:
            kwargs.update({'filename': message['filename']})
        col.add_item(**kwargs)
        col.save()