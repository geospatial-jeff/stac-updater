import os
import re
import shutil
import subprocess

import click
import yaml
from satstac import Collection

from stac_updater import resources

sls_template_path = os.path.join(os.path.dirname(__file__), '..', 'serverless_template.yml')
sls_config_path = os.path.join(os.path.dirname(__file__), '..', 'serverless.yml')

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
def update_collection(root, long_poll, concurrency):
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

        aws_resources = resources.update_collection(name, root, filter_rule, long_poll, concurrency)
        sls_config['resources']['Resources'].update(aws_resources['resources'])
        sls_config['functions'].update(aws_resources['functions'])

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
@click.option('--topic_name', type=str, required=True, help="Name of SNS topic.")
def add_notifications(topic_name):
    # Remove all non-alphanumeric characters
    pattern = re.compile('[\W_]+')
    alphanumeric_name = pattern.sub('', topic_name)

    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)
        sls_config['resources']['Resources'].update({
            alphanumeric_name: resources.sns_topic(topic_name)
        })

        sls_config['provider']['environment'].update({
            'NOTIFICATION_TOPIC': topic_name
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





@stac_updater.command(name='deploy', short_help="deploy service to aws")
def deploy():
    subprocess.call("docker build . -t stac-updater:latest", shell=True)
    subprocess.call("docker run --rm -v $PWD:/home/stac_updater -it stac-updater:latest package-service.sh", shell=True)
    subprocess.call("npm install serverless-pseudo-parameters", shell=True)
    subprocess.call("sls deploy -v", shell=True)