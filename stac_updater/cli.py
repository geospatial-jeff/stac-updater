import os

import click
import yaml

from stac_updater import resources, names


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
            'resources': {
                'Resources': {
                    'NewSTACItemTopic': resources.sns_topic(names.sns_topic)
                }
            },
            'plugins': [
                'serverless-pseudo-parameters'
            ]
        }

        # Generate AWS resources to update static STAC catalog
        if 'static_catalog' in user_keys:
            sls_config['provider']['environment'].update({
                'CAT_ROOT_URL': user_config['static_catalog']['root_url']
            })

            # Create DLQ
            dlq = resources.sqs_queue(names.static_dlq)

            # Create SQS queue and subscribe to NewSTACItemTopic
            sqs_queue = resources.sqs_queue(names.static_queue, dlq_name=names.static_dlq, maxRetry=1)
            sns_subscription, sqs_policy = resources.subscribe_sqs_to_sns(names.static_queue, names.sns_topic)

            # Add resources to sls config
            sls_config['resources']['Resources'].update({
                names.static_dlq: dlq,
                names.static_queue: sqs_queue,
                names.static_sns_sub: sns_subscription,
                names.static_sqs_policy: sqs_policy
            })

        # Save to serverless.yml file
        with open('serverless.yml', 'w') as outfile:
            yaml.dump(sls_config, outfile, indent=1)



