from stac_updater import names


def subscribe_sqs_to_sns(queue_name, topic_name):

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
                                "aws:SourceArn": topic_name
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

    return subscription, policy

def sqs_queue(queue_name, dlq_name=None, maxRetry=3):
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

    return resource

def sns_topic():
    resource = {
        "Type": "AWS::SNS::Topic",
        "Properties": {
            "TopicName": names.sns_topic
        }
    }
    return {names.sns_topic: resource}

def lambda_sqs_trigger(func_name, queue_name):
    func = {
        "handler": f"handler.{func_name}",
        "events": [
            {
                "sqs": {
                    "arn": "arn:aws:sqs:#{}:#{}:{}".format("{AWS::Region}",
                                                        "{AWS::AccountId}",
                                                        queue_name),
                }
            }
        ]
    }

    return func


def setup_resources(cat_type):
    dlq_name = getattr(names, f"{cat_type}_dlq")
    queue_name = getattr(names, f"{cat_type}_queue")
    sns_sub_name = getattr(names, f"{cat_type}_sns_sub")
    sqs_policy_name = getattr(names, f"{cat_type}_sqs_policy")
    lambda_name = getattr(names, f"{cat_type}_lambda_updater")

    dlq = sqs_queue(dlq_name)
    queue = sqs_queue(queue_name, dlq_name=dlq_name, maxRetry=3)
    sns_subscription, sqs_policy = subscribe_sqs_to_sns(queue_name, names.sns_topic)
    lambda_updater = lambda_sqs_trigger(lambda_name, queue_name)

    return {
        'resources': {
            dlq_name: dlq,
            queue_name: queue,
            sns_sub_name: sns_subscription,
            sqs_policy_name: sqs_policy
        },
        'functions': {
            lambda_name: lambda_updater
        }
    }



