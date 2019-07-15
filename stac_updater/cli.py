import os
import re
import shutil
import subprocess
import json

import click
import yaml
from satstac import Collection

from stac_updater import resources

sls_template_path = os.path.join(os.path.dirname(__file__), '..', 'serverless_template.yml')
sls_config_path = os.path.join(os.path.dirname(__file__), '..', 'serverless.yml')
notification_topic_name = 'stacUpdaterNotifications'

@click.group()
def stac_updater():
    pass

@stac_updater.command(name='new-service', short_help="build a new service")
def new_service():
    shutil.copyfile(sls_template_path, sls_config_path)

@stac_updater.command(name='update-collection', short_help="update a static collection")
@click.option('--root', '-r', type=str, required=True, help="URL of collection.")
@click.option('--long-poll/--short-poll', default=False, help="Enable long polling.")
@click.option('--concurrency', type=int, default=1, help="Sets lambda concurrency limit when polling the queue.")
@click.option('--timeout', type=int, default=15, help="Sets lambda timeout.")
@click.option('--path', type=str, help="Pattern used by sat-stac to build sub-catalogs.")
@click.option('--filename', type=str, help="Pattern used by sat-stac to build item name.")
def update_collection(root, long_poll, concurrency, timeout, path, filename):
    # Create a SQS queue for the collection
    # Subscribe SQS queue to SNS topic with filter policy on collection name
    # Configure lambda function and attach to SQS queue (use ENV variables to pass state)

    name = Collection.open(root).id
    filter_rule = {'collection': [name]}

    pattern = re.compile('[\W_]+')
    name = pattern.sub('', name)

    with open(sls_config_path, 'r') as f:
        # Using unsafe load to preserve type.
        sls_config = yaml.unsafe_load(f)

        aws_resources = resources.update_collection(name, root, filter_rule, long_poll, concurrency, timeout, path, filename)
        sls_config['resources']['Resources'].update(aws_resources['resources'])
        sls_config['functions'].update(aws_resources['functions'])

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_config, outf, indent=1)

@stac_updater.command(name='update-dynamic-catalog', short_help="update a dynamic catalog")
@click.option('--arn', type=str, help="ARN of sat-api ingest lambda function.")
def update_dynamic_catalog(arn):
    # This microservice re-uses the SNS topic created with the `add_notifications` command
    # Subscribe sat-api ingest function to SNS topic.

    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)
        if notification_topic_name not in sls_config['resources']['Resources']:

            sls_config['resources']['Resources'].update({
                notification_topic_name: resources.sns_topic(notification_topic_name)
            })

            sls_config['provider']['environment'].update({
                'NOTIFICATION_TOPIC': notification_topic_name
            })

        sns_subscription, policy = resources.subscribe_lambda_to_sns(arn, notification_topic_name)
        sls_config['resources']['Resources'].update({
            'satApiIngestSubscription': sns_subscription,
            'satApiIngestPolicy': policy
        })
        sns_subscription.update({'DependsOn': 'stacUpdaterNotifications'})

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_config, outf, indent=1)


@stac_updater.command(name='modify-kickoff', short_help="modify event source of kickoff")
@click.option('--type', '-t', type=str, default='lambda', help="Type of event source used by kickoff.")
@click.option('--bucket_name', type=str, help="Required if type=='s3'; defines name of bucket used by event source.")
@click.option('--topic_name', type=str, help="Required if type=='sns'; defines name of SNS topic used by event source.")
def modify_kickoff(type, bucket_name, topic_name):
    func_name = 'kickoff'

    if type == 's3':
        kickoff_func = resources.lambda_s3_trigger(func_name, bucket_name)
    elif type == 'lambda':
        kickoff_func = resources.lambda_invoke(func_name)
    elif type == 'sns':
        kickoff_func = resources.lambda_sns_trigger(func_name, topic_name)
    else:
        raise ValueError("The `type` parameter must be one of ['s3', 'lambda'].")

    # Add kickoff source event to environment
    kickoff_func.update({'environment': {
        'EVENT_SOURCE': type
    }})
    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)
        sls_config['functions']['kickoff'].update(kickoff_func)

        if type == 'lambda' and 'events' in sls_config['functions']['kickoff']:
            del(sls_config['functions']['kickoff']['events'])

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_config, outf, indent=1)

@stac_updater.command(name='add-notifications', short_help="notifications on catalog update")
def add_notifications():

    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)
        sls_config['resources']['Resources'].update({
            notification_topic_name: resources.sns_topic(notification_topic_name)
        })

        sls_config['provider']['environment'].update({
            'NOTIFICATION_TOPIC': notification_topic_name
        })

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_config, outf, indent=1)

@stac_updater.command(name='add-logging', short_help="Pipe cloudwatch logs into elasticsearch.")
@click.option('--es_host', type=str, required=True, help="Domain name of elasticsearch instance.")
def add_logging(es_host):
    # Add the ES_LOGGING lambda function (cloudwatch trigger).
    # Add es_domain to ES_LOGGING lambda as environment variable.
    # Update IAM permissions (es:*, arn:Aws:es:*)
    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)

        # Create lambda function
        service_name = sls_config['custom']['service-name']
        service_stage = sls_config['custom']['stage']
        collection_names = [x.split('_')[0] for x in list(sls_config['functions']) if x not in ['kickoff', 'es_log_ingest']]
        func = resources.lambda_cloudwatch_trigger("es_log_ingest", service_name, service_stage, collection_names)
        func.update({'environment': {'ES_HOST': es_host}})
        sls_config['functions'].update({'es_log_ingest': func})

        # Expanding IAM role
        if 'es:*' not in sls_config['provider']['iamRoleStatements'][0]['Action']:
            sls_config['provider']['iamRoleStatements'][0]['Action'].append('es:*')
        if 'arn:aws:es:*' not in sls_config['provider']['iamRoleStatements'][0]['Resource']:
            sls_config['provider']['iamRoleStatements'][0]['Resource'].append('arn:aws:ecs:*')

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_config, outf, indent=1)

@stac_updater.command(name='build-thumbnails', short_help="Generate thumbnails when ingesting items.")
@click.option('--collection', '-c', type=str, multiple=True, help="Limit thumbnails to specific collections.")
def build_thumbnails(collection):
    # Deploy the stac-thumbnail service
    # Subscribe notification SNS topic to stac-thumbnail SQS queue
    queue_name = 'newThumbnailQueue'

    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)

        # Build notification topic if it doesn't already exist
        if notification_topic_name not in sls_config['resources']['Resources']:
            sls_config['resources']['Resources'].update({
                notification_topic_name: resources.sns_topic(notification_topic_name)
            })
            sls_config['provider']['environment'].update({
                'NOTIFICATION_TOPIC': notification_topic_name
            })

        # Create filter policies based on input collections
        filter_policy = {"collection": collection} if len(collection) > 0 else None
        subscription, policy = resources.subscribe_sqs_to_sns(queue_name, notification_topic_name, filter_policy)

        # Use remote references instead of local (queue is defined in separate service).
        policy['Properties']['PolicyDocument']['Statement'][0].update({
            'Resource': "arn:aws:sqs:#{AWS::Region}:#{AWS::AccountId}:" + queue_name
        })
        policy['Properties']['Queues'][0] = 'https://sqs.#{AWS::Region}.amazonaws.com/#{AWS::AccountId}/' + queue_name
        subscription['Properties'].update({'Endpoint': "arn:aws:sqs:#{AWS::Region}:#{AWS::AccountId}:" + queue_name})
        subscription.update({'DependsOn': 'stacUpdaterNotifications'})

        sls_config['resources']['Resources'].update({
            'thumbnailSnsSub': subscription,
            'thumbnailSqsPolicy': policy,
        })

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_config, outf, indent=1)

@stac_updater.command(name='deploy', short_help="deploy service to aws.")
def deploy():
    subprocess.call("docker build . -t stac-updater:latest", shell=True)
    subprocess.call("docker run --rm -v $PWD:/home/stac_updater -it stac-updater:latest package-service.sh", shell=True)
    subprocess.call("npm install serverless-pseudo-parameters", shell=True)
    subprocess.call("sls deploy -v", shell=True)

@stac_updater.command(name='info', short_help="prints information about your service.")
def info():
    info = {}
    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)
        static_updaters = [sls_config['functions'][x] for x in sls_config['functions'] if x.endswith('update_collection')]
        if len(static_updaters) > 0:
            info.update({
                'static_collections': [{
                    'root': x['environment']['COLLECTION_ROOT'],
                    'path': x['environment']['PATH'],
                    'filename': x['environment']['FILENAME'],
                    'eventSource': list(x['events'])[0]
                } for x in static_updaters]
            })

        if notification_topic_name in sls_config['resources']['Resources']:
            info.update({
                'notifications': {
                    'topicArn': 'arn:aws:sns:#{AWS::Region}:#{AWS::AccountId}:' + notification_topic_name
                }
            })

        if 'es_log_ingest' in sls_config['functions']:
            info.update({
                'logging': {
                    'host': sls_config['functions']['es_log_ingest']['environment']['ES_HOST'],
                    'logGroups': [x['cloudwatchLog']['logGroup'] for x in sls_config['functions']['es_log_ingest']['events']]
                }
            })

    print(json.dumps(info, indent=1))
