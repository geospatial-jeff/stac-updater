import os
import json
import base64
import gzip

import boto3
from satstac import Collection, Item

from stac_updater import utils

sns_client = boto3.client('sns')
s3_res = boto3.resource('s3')

ACCOUNT_ID = boto3.client('sts').get_caller_identity()['Account']
REGION = os.getenv('REGION')
NOTIFICATION_TOPIC = os.getenv('NOTIFICATION_TOPIC')

def kickoff(event, context):
    event_source = os.getenv('EVENT_SOURCE')

    # Load payload based on event source
    if event_source == "s3":
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']
        content_object = s3_res.Object(bucket, key)
        file_content = content_object.get()['Body'].read().decode('utf-8')
        payload = json.loads(file_content)
    elif event_source == "sns":
        payload = json.loads(event['Records'][0]['Sns']['Message'])
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
    item_count = len(event['Records'])
    stac_links = []

    for record in event['Records']:
        message = json.loads(record['body'])

        col = Collection.open(collection_root)
        collection_name = col.id
        kwargs = {'item': Item(message['stac_item'])}
        if 'path' in message:
            kwargs.update({'path': message['path']})
        if 'filename' in message:
            kwargs.update({'filename': message['filename']})
        col.add_item(**kwargs)
        col.save()

        stac_links.append(kwargs['item'].links('self')[0])

        # Send message to SNS Topic if enabled
        if NOTIFICATION_TOPIC:
            kwargs = utils.stac_to_sns(message['stac_item'])
            kwargs.update({
                'TopicArn': f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:{NOTIFICATION_TOPIC}"
            })
            sns_client.publish(**kwargs)


    print(f"LOGS CollectionName: {collection_name}\tItemCount: {item_count}\tItemLinks: {stac_links}")


def es_log_ingest(event, context):
    from stac_updater import logging

    cw_data = event['awslogs']['data']
    compressed_payload = base64.b64decode(cw_data)
    uncompressed_payload = gzip.decompress(compressed_payload)
    payload = json.loads(uncompressed_payload)

    # Index to ES
    logging.index_logs(payload)








