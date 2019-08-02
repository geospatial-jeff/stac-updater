
def subscribe_sqs_to_sns(queue_name, topic_name, filter_policy=None):

    policy = {
        "Type": "AWS::SQS::QueuePolicy",
        "Properties": {
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "allow-sns-messages",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Resource": {
                            "Fn::GetAtt": [
                                queue_name,
                                "Arn"
                            ]
                        },
                        "Action": "SQS:SendMessage",
                        "Condition": {
                            "ArnEquals": {
                                "aws:SourceArn": {
                                    "Ref": topic_name
                                }
                            }
                        }
                    }
                ]
            },
            "Queues": [
                {'Ref': queue_name}
            ]
        }
    }

    subscription = {
        "Type": "AWS::SNS::Subscription",
        "Properties": {
            "TopicArn": "arn:aws:sns:#{}:#{}:{}".format("{AWS::Region}",
                                                        "{AWS::AccountId}",
                                                        topic_name),
            "Endpoint": {
                "Fn::GetAtt": [
                    queue_name,
                    "Arn"
                ]
            },
            "Protocol": "sqs",
            "RawMessageDelivery": "true"
        }
    }

    if filter_policy:
        subscription['Properties'].update({
            "FilterPolicy": filter_policy
        })

    return subscription, policy

def subscribe_lambda_to_sns(lambda_arn, topic_name):

    lambda_policy = {
        "Type": "AWS::Lambda::Permission",
        "Properties": {
            "Action": "lambda:Invokefunction",
            "FunctionName": lambda_arn,
            "Principal": "sns.amazonaws.com",
            "SourceArn": {"Ref": topic_name},
        }
    }

    subscription = {
        "Type": "AWS::SNS::Subscription",
        "Properties": {
            "TopicArn": "arn:aws:sns:#{}:#{}:{}".format("{AWS::Region}",
                                                        "{AWS::AccountId}",
                                                        topic_name),
            "Endpoint": lambda_arn,
            "Protocol": "lambda",
        }
    }

    return subscription, lambda_policy


def sqs_queue(queue_name, dlq_name=None, maxRetry=3, long_poll=False, timeout=None):
    resource = {
        "Type": "AWS::SQS::Queue",
        "Properties": {
            "QueueName": queue_name
        }
    }

    if dlq_name:
        redrive_policy = {
            "deadLetterTargetArn": {
                "Fn::GetAtt": [
                    dlq_name,
                    "Arn"
                ]
            },
            "maxReceiveCount": maxRetry,
        }
        resource['Properties'].update({'RedrivePolicy': redrive_policy})

    if long_poll:
        resource['Properties'].update({'ReceiveMessageWaitTimeSeconds': 20})

    if timeout:
        resource['Properties'].update({'VisibilityTimeout': timeout})

    return resource

def sns_topic(topic_name):
    resource = {
        "Type": "AWS::SNS::Topic",
        "Properties": {
            "TopicName": topic_name
        }
    }
    return resource

def lambda_sqs_trigger(func_name, queue_name):
    func = {
        "handler": f"stac_updater.handler.{func_name}",
        "events": [
            {
                "sqs": {
                    "arn": "arn:aws:sqs:#{}:#{}:{}".format("{AWS::Region}",
                                                        "{AWS::AccountId}",
                                                        queue_name)
                }
            }
        ]
    }
    return func

def lambda_s3_trigger(func_name, bucket_name):
    func = {
        "handler": f"stac_updater.handler.{func_name}",
        "events": [
            {
                "s3": {
                    "bucket": bucket_name,
                    "event": "s3:ObjectCreated:*"
                }
            }
        ]
    }

    return func

def lambda_sns_trigger(func_name, topic_name):
    func = {
        "handler": f"stac_updater.handler.{func_name}",
        "events": [
            {
                "sns": {
                    "arn": "arn:aws:sns:#{}:#{}:{}".format("{AWS::Region}",
                                                        "{AWS::AccountId}",
                                                        topic_name),
                    "topicName": topic_name
                }
            }
        ]
    }

    return func

def lambda_cloudwatch_trigger(func_name, service_name, service_stage, collections):
    func = {
        "handler": f"stac_updater.handler.{func_name}",
        "events": []
    }

    for coll in collections:
        func['events'].append(
            {
                "cloudwatchLog": {
                    "logGroup": f"/aws/lambda/{service_name}-{service_stage}-{coll}_update_collection",
                    "filter": "?REPORT ?LOGS"
                }
            }
        )

    return func

def lambda_invoke(func_name):
    func = {
        "handler": f"stac_updater.handler.{func_name}",
    }
    return func

def update_collection(name, root, filter_rule, long_poll, concurrency, timeout, vis_timeout, path, filename, backfill_extent):
    dlq_name = f"{name}Dlq"[:43]
    queue_name = f"{name}Queue"[:43]
    sns_sub_name = f"{name}SnsSub"[:43]
    sqs_policy_name = f"{name}SqsPolicy"[:43]
    lambda_name = "update_collection"

    dlq = sqs_queue(dlq_name)
    queue = sqs_queue(queue_name, dlq_name=dlq_name, maxRetry=3, long_poll=long_poll, timeout=vis_timeout)
    sns_subscription, sqs_policy = subscribe_sqs_to_sns(queue_name, 'newStacItemTopic', filter_rule)
    lambda_updater = lambda_sqs_trigger(lambda_name, queue_name)

    lambda_updater.update({
        'environment': {
            'COLLECTION_ROOT': root
        },
        "reservedConcurrency": concurrency,
        "timeout": timeout
    })

    if path:
        lambda_updater['environment'].update({
            'PATH': path
        })

    if filename:
        lambda_updater['environment'].update({
            'FILENAME': filename
        })

    if backfill_extent:
        lambda_updater['environment'].update({
            'BACKFILL_EXTENT': backfill_extent
        })

    return {
        'resources': {
            dlq_name: dlq,
            queue_name: queue,
            sns_sub_name: sns_subscription,
            sqs_policy_name: sqs_policy
        },
        'functions': {
            f"{name}_{lambda_name}"[:45]: lambda_updater
        }
    }