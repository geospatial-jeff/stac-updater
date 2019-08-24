from datetime import datetime
import json

def stac_to_sns(stac_item):
    """Convert a STAC item to SNS message (with attributes)"""

    try:
        collection = stac_item['collection']
    except KeyError:
        collection = stac_item['properties']['collection']

    attributes = {
        'bbox.xmin': {
            "DataType": "Number",
            "StringValue": str(stac_item['bbox'][0])
        },
        'bbox.ymin': {
            "DataType": "Number",
            "StringValue": str(stac_item['bbox'][1])
        },
        'bbox.xmax': {
            "DataType": "Number",
            "StringValue": str(stac_item['bbox'][2])
        },
        'bbox.ymax': {
            "DataType": "Number",
            "StringValue": str(stac_item['bbox'][3])
        },
        'collection': {
            "DataType": "String",
            "StringValue": collection
        },
    }

    return {
        "Message": json.dumps(stac_item),
        "MessageAttributes": attributes
    }

def load_datetime(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except:
        return datetime.strptime(date_str, "%Y-%m-%d")