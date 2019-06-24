import ast
from datetime import datetime
import os

import boto3
from elasticsearch import Elasticsearch, RequestsHttpConnection, ConflictError
from requests_aws4auth import AWS4Auth


ES_HOST = os.getenv('ES_HOST')
REGION = os.getenv('REGION')

if ES_HOST:
    cred = boto3.Session().get_credentials()
    awsauth = AWS4Auth(cred.access_key, cred.secret_key, REGION, 'es', session_token=cred.token)
    es = Elasticsearch(
        hosts=[{'host': ES_HOST, 'port': 443}],
        http_auth=awsauth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection
    )

def create_index(index_name):
    """Create a new ES index with given name"""
    if not es.indices.exists(index_name):
        mapping = {
            "mappings": {
                "log": {
                    "properties": {
                        "id": {"type": "text"},
                        "BilledDuration": {"type": "float"},
                        "CollectionName": {"type": "text"},
                        "Duration": {"type": "float"},
                        "ItemCount": {"type": "integer"},
                        "ItemLinks": {"type": "text"},
                        "MaxMemoryUsed": {"type": "float"},
                        "MemorySize": {"type": "float"},
                        "LogType": {"type": "text"},
                        "RequestId": {"type": "text"},
                        "timestamp": {
                            "type": "date",
                            "format": "epoch_millis"
                        }
                    }
                }
            }
        }

        es.indices.create(index_name, body=mapping)

def transform_log(log):
    """Transform logs into schema which matches ES index (see create_index)."""
    log['id'] = int(str(log['id'])[:11])
    message = log.pop('message')
    splits = message.rstrip().split('\t')
    log_type = splits[0].split(' ')[0]
    splits[0] = splits[0].replace(log_type + ' ', '')

    for item in splits:
        k, v = item.split(': ')
        if k == 'ItemLinks':
            v = v.split('"')
            if len(v) == 1:
                v = v[0]
            else:
                v = '[' + ",".join(v) + ']'
        else:
            v = v.split(' ')[0]
        k = k.replace(' ','')
        log.update({k:v})

def transform_logs(first_log, second_log=None):
    """Identify input logs as LOGS or REPORT and build ES document (combining if both logs are passsed)."""
    log_type = first_log['message'].rstrip().split('\t')[0].split(' ')[0]

    event_report = event_log = None
    if log_type == 'LOGS':
        event_log = first_log
        if second_log:
            event_report = second_log
    elif log_type == 'REPORT':
        event_report = first_log
        if second_log:
            event_log = second_log

    if event_log:
        transform_log(event_log)
        print("event log",event_log)
        event_log['ItemLinks'] = ast.literal_eval(event_log['ItemLinks'])
    if event_report:
        transform_log(event_report)
        print("event report", event_report)
    if event_log and event_report:
        # Prioritize keys from event_report if duplicated.
        combined_logs = {**event_log, **event_report}
        return combined_logs
    else:
        if event_log:
            return event_log
        if event_report:
            return event_report

def es_index(body, index_name, safe=False):
    """Insert item into ES with safe mode"""
    kwargs = {
        'id': body['id'],
        'body': body,
        'index': index_name,
        'doc_type': 'log',
    }

    if safe:
        print("Using safe index.")
        kwargs.update({'op_type': 'create'})

    try:
        resp = es.index(**kwargs)
        return resp
    except ConflictError:
        del(kwargs['op_type'])
        # ID already exists, use update instead.
        kwargs['body'] = {'doc': kwargs['body']}
        resp = es.update(**kwargs)
        return resp

def index_logs(cwl_data):
    # Cloudwatch receives two types of logs (LOGS and REPORT) from the updateCollection lambda -- see cloudwatch filters.
    # LOGS contains information about lambda function payload (catalog name, batch size etc., stac item url)
    # REPORT contains information about lambda runtime (memory used, billed time etc.)
    # There is no guarantee that both logs from an individual lambda will be processed during the same invocation.
    log_count = len(cwl_data['logEvents'])

    # Making the assumption that all logs processed by a single invocation happen on the same calendar day.
    # Creating a new index each day.
    log_date = datetime.fromtimestamp(int(str(cwl_data['logEvents'][0]['timestamp'])[:-3]))
    index_name = 'stac_updater_logs_' + log_date.strftime("%Y%m%d")
    create_index(index_name)

    # If there are multiple messages, first try matching the LOGS and REPORT values across messages (via ID).
    # This saves having to check if the ID already exists in elasticsearch.
    if log_count > 1:
        # Only the first 11 characters of the id are unique across logs from the same invocation.
        ids = [x['id'] for x in cwl_data['logEvents']]
        unique_ids = set(ids)
        matches = [[i for i, x in enumerate(ids) if x==id] for id in unique_ids]
        for pair in matches:
            # The other log is being proceed by a different invocation
            if len(pair) == 1:
                some_log = transform_logs(cwl_data['logEvents'][pair[0]])
                es_index(some_log, index_name, safe=True)
            else:
                combined_logs = transform_logs(cwl_data['logEvents'][pair[0]], cwl_data['logEvents'][pair[1]])
                es_index(combined_logs, index_name, safe=True)
    else:
        some_log = transform_logs(cwl_data['logEvents'][0])
        es_index(some_log, index_name, safe=True)