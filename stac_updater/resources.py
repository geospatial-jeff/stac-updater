
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