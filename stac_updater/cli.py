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
    print(name)

    filter_rule = {'collection': [name]}

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
@click.option('--bucket_name', '-n', type=str, help="Required if type=='s3'; creates new bucket used by event source.")
def modify_kickoff(type, bucket_name):
    func_name = 'kickoff'

    if type == 's3':
        kickoff_func = resources.lambda_s3_trigger(func_name, bucket_name)
    elif type == 'lambda':
        kickoff_func = resources.lambda_invoke(func_name)
    else:
        raise ValueError("The `type` parameter must be one of ['s3', 'lambda'].")

    # Add kickoff source event to environment
    kickoff_func.update({'environment': {
        'EVENT_SOURCE': type
    }})
    with open(sls_config_path, 'r') as f:
        sls_config = yaml.unsafe_load(f)
        sls_config['functions']['kickoff'].update(kickoff_func)

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

@stac_updater.command(name='deploy', short_help="deploy service to aws")
def deploy():
    subprocess.call("docker build . -t stac-updater:latest", shell=True)
    subprocess.call("docker run --rm -v $PWD:/home/stac_updater -it stac-updater:latest package-service.sh", shell=True)
    subprocess.call("npm install serverless-pseudo-parameters", shell=True)
    subprocess.call("sls deploy -v", shell=True)