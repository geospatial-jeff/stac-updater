import os

import click
import yaml

from stac_updater import resources

sls_template_path = os.path.join(os.path.dirname(__file__), '..', 'serverless_template.yml')
sls_config_path = os.path.join(os.path.dirname(__file__), '..', 'serverless.yml')

@click.group()
def stac_updater():
    pass

@stac_updater.command(name='update-collection')
@click.option('--name', '-n', type=str, required=True)
@click.option('--root', '-r', type=str, required=True)
@click.option('--long-poll/--short-poll', default=False)
@click.option('--concurrency', type=int, default=1)
def update_collection(name, root, long_poll, concurrency):
    # Create a SQS queue for the collection
    # Subscribe SQS queue to SNS topic with filter policy on collection name
    # Configure lambda function and attach to SQS queue (use ENV variables to pass state)

    filter_rule = {'collection': [name]}

    with open(sls_template_path, 'r') as f:
        sls_template = yaml.load(f, Loader=yaml.BaseLoader)

        aws_resources = resources.update_collection(name, root, filter_rule, long_poll, concurrency)
        sls_template['resources']['Resources'].update(aws_resources['resources'])
        sls_template['functions'].update(aws_resources['functions'])

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_template, outf, indent=1)

@stac_updater.command(name='modify-kickoff')
@click.option('--type', '-t', type=str, default='lambda')
@click.option('--bucket_name', '-n', type=str)
def modify_kickoff(type, bucket_name):
    if type == 's3':
        kickoff_func = resources.lambda_s3_trigger('kickoff', bucket_name)

        with open(sls_config_path, 'r') as f:
            sls_config = yaml.unsafe_load(f)
            sls_config['functions']['kickoff'].update(kickoff_func)

            with open(sls_config_path, 'w') as outf:
                yaml.dump(sls_config, outf, indent=1)