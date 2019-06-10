import os

import click
import yaml

# from stac_updater import resources, names
from stac_updater import resources


@click.group()
def stac_updater():
    pass

@stac_updater.command(name='build-project')
def build_project():
    user_config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yml')

    with open(user_config_path, 'r') as f:
        user_config = yaml.load(f, Loader=yaml.BaseLoader)
        user_keys = list(user_config)

        sls_config = {
            'service': user_config['service']['name'] + '-${self:provider.stage}',
            'provider': {
                'name': 'aws',
                'runtime': 'python3.7',
                'stage': user_config['service']['stage'],
                'region': user_config['service']['region'],
                'environment': {
                    'REGION': user_config['service']['region']
                }
            },
            'functions': {
                "kickoff": {
                    "handler": "handler.kickoff"
                },
            },
            'resources': {
                'Resources': resources.sns_topic()
            },
            'plugins': [
                'serverless-pseudo-parameters'
            ]
        }

        # Generate AWS resources to update static STAC catalog
        if 'static_catalog' in user_keys:
            sls_config['provider']['environment'].update({
                'ITEM_PATH': user_config['static_catalog']['item_path'],
                'ITEM_NAME': user_config['static_catalog']['item_name']
            })

            aws_resources = resources.setup_resources('static')
            sls_config['resources']['Resources'].update(aws_resources['resources'])
            sls_config['functions'].update(aws_resources['functions'])

        if 'dynamic_catalog' in user_keys:
            sls_config['provider']['environment'].update({'INGEST_ARN': user_config['dynamic_catalog']['ingest_arn']})

            aws_resources = resources.setup_resources('dynamic')
            sls_config['resources']['Resources'].update(aws_resources['resources'])
            sls_config['functions'].update(aws_resources['functions'])

        # Save to serverless.yml file
        with open('serverless.yml', 'w') as outfile:
            yaml.dump(sls_config, outfile, indent=1)



