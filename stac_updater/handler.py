import os
import json
import base64
import gzip
from datetime import datetime

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

    print(payload)

    try:
        coll_name = payload['properties']['collection']
    except KeyError:
        coll_name = payload['collection']

    sns_client.publish(
        TopicArn=f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:newStacItemTopic",
        Message=json.dumps(payload),
        MessageAttributes={
            'collection': {
                'DataType': 'String',
                'StringValue': coll_name
            }
        }
    )

def update_collection(event, context):
    try:
        collection_root = os.getenv('COLLECTION_ROOT')
        path = os.getenv('PATH')
        filename = os.getenv('FILENAME')
        backfill_extent = os.getenv('BACKFILL_EXTENT')

        item_count = len(event['Records'])
        stac_links = []

        for record in event['Records']:
            stac_item = json.loads(record['body'])
            print(stac_item)

            col = Collection.open(collection_root)
            collection_name = col.id
            kwargs = {'item': Item(stac_item)}
            if path:
                kwargs.update({'path': '$' + '/$'.join(path.split('/'))})
            if filename:
                kwargs.update({'filename': '$' + '/$'.join(filename.split('/'))})

            # Update spatial and temporal extent of collection
            if backfill_extent:
                if 'spatial' in col.data['extent']:
                    if stac_item['bbox'][0] < col.data['extent']['spatial'][0]:
                        col.data['extent']['spatial'][0] = stac_item['bbox'][0]
                    if stac_item['bbox'][1] < col.data['extent']['spatial'][1]:
                        col.data['extent']['spatial'][1] = stac_item['bbox'][1]
                    if stac_item['bbox'][2] > col.data['extent']['spatial'][2]:
                        col.data['extent']['spatial'][2] = stac_item['bbox'][2]
                    if stac_item['bbox'][3] > col.data['extent']['spatial'][3]:
                        col.data['extent']['spatial'][3] = stac_item['bbox'][3]
                else:
                    col.data['extent'].update({'spatial': stac_item['bbox']})

                if 'temporal' in col.data['extent']:
                    item_dt = utils.load_datetime(stac_item['properties']['datetime'])
                    min_dt = utils.load_datetime(col.data['extent']['temporal'][0])
                    max_dt = utils.load_datetime(col.data['extent']['temporal'][1])
                    if item_dt < min_dt:
                        col.data['extent']['temporal'][0] = stac_item['properties']['datetime']
                    if item_dt > max_dt:
                        col.data['extent']['temporal'][1] = stac_item['properties']['datetime']
                else:
                    col.data['extent'].update({'temporal': [stac_item['properties']['datetime'], stac_item['properties']['datetime']]})

            col.add_item(**kwargs)
            col.save()

            stac_links.append(kwargs['item'].links('self')[0])

            # Send message to SNS Topic if enabled
            if NOTIFICATION_TOPIC:
                kwargs = utils.stac_to_sns(kwargs['item'].data)
                kwargs.update({
                    'TopicArn': f"arn:aws:sns:{REGION}:{ACCOUNT_ID}:{NOTIFICATION_TOPIC}"
                })
                sns_client.publish(**kwargs)


        print(f"LOGS CollectionName: {collection_name}\tItemCount: {item_count}\tItemLinks: {stac_links}")
    except:
        raise


def es_log_ingest(event, context):
    from stac_updater import logging

    cw_data = event['awslogs']['data']
    compressed_payload = base64.b64decode(cw_data)
    uncompressed_payload = gzip.decompress(compressed_payload)
    payload = json.loads(uncompressed_payload)

    # Index to ES
    logging.index_logs(payload)