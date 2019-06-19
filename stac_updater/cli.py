import os
import json

import click
import yaml

from stac_updater import resources



@click.group()
def stac_updater():
    pass

# Base deployment starts out with a single SNS topic which receives new STAC Items as messages
# Also a lambda function which ingests a STAC Item from various payloads and sends SNS message with collection filter.

@stac_updater.command(name='update-collection')
@click.option('--name', '-n', type=str, required=True)
@click.option('--root', '-r', type=str, required=True)
def update_collection(name, root):
    # Create a SQS queue for the collection
    # Subscribe SQS queue to SNS topic with filter policy on collection name
    # Configure lambda function and attach to SQS queue (use ENV variables to pass state)

    sls_template_path = os.path.join(os.path.dirname(__file__), '..', 'serverless_template.yml')
    sls_config_path = os.path.join(os.path.dirname(__file__), '..', 'serverless.yml')

    filter_rule = {'collection': [name]}

    with open(sls_template_path, 'r') as f:
        sls_template = yaml.load(f, Loader=yaml.BaseLoader)


        aws_resources = resources.update_collection(name, root, filter_rule)
        sls_template['resources']['Resources'].update(aws_resources['resources'])
        sls_template['functions'].update(aws_resources['functions'])

        with open(sls_config_path, 'w') as outf:
            yaml.dump(sls_template, outf, indent=1)






