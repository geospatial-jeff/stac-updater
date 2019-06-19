import os
import json

from satstac import Collection, Item
import boto3

sns_client = boto3.client('sns')
s3_res = boto3.resource('s3')

ACCOUNT_ID = boto3.client('sts').get_caller_identity()['Account']
REGION = os.getenv('REGION')


def kickoff(event, context):
    event_source = os.getenv('EVENT_SOURCE')

    # Load payload based on event source
    if event_source == "s3":
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']
        content_object = s3_res.Object(bucket, key)
        file_content = content_object.get()['Body'].read().decode('utf-8')
        payload = json.loads(file_content)
    else:
        # Default is lambda
        payload = event

    try:
        coll_name = payload['stac_item']['properties']['collection']
    except KeyError:
        coll_name = payload['stac_item']['collection']

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