#!/usr/bin/env python3
"""
SmartWard - AWS Infrastructure Setup
Creates all required AWS resources for the SmartWard backend.
Run once before starting the fog node or deploying Lambdas.

Usage:
  export AWS_DEFAULT_REGION=us-east-1
  python setup_infrastructure.py

AWS Academy note: uses environment credential chain (no explicit keys needed).
"""

import json
import sys
import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
TABLE_NAME = "smartward-readings"
QUEUE_NAME = "smartward-sensor-queue"
SNS_TOPIC_NAME = "smartward-alerts"
LAMBDA_ROLE_NAME = "smartward-lambda-role"

dynamodb = boto3.client("dynamodb", region_name=REGION)
sqs = boto3.client("sqs", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)
iam = boto3.client("iam", region_name=REGION)
lmb = boto3.client("lambda", region_name=REGION)


def create_dynamodb_table():
    print("Creating DynamoDB table...")
    try:
        dynamodb.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",   # on-demand; scales automatically
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "ttl",      # auto-delete old readings
            },
        )
        waiter = dynamodb.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        print(f"  ✓ Table '{TABLE_NAME}' created")
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  ✓ Table '{TABLE_NAME}' already exists")
            return True
        print(f"  ✗ Failed: {exc}")
        return False


def create_sqs_queue():
    print("Creating SQS queue...")
    try:
        resp = sqs.create_queue(
            QueueName=QUEUE_NAME,
            Attributes={
                "VisibilityTimeout": "60",
                "MessageRetentionPeriod": "86400",  # 24 hours
                "ReceiveMessageWaitTimeSeconds": "20",  # long-poll
            },
        )
        queue_url = resp["QueueUrl"]
        print(f"  ✓ Queue URL: {queue_url}")
        return queue_url
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "QueueAlreadyExists":
            resp = sqs.get_queue_url(QueueName=QUEUE_NAME)
            queue_url = resp["QueueUrl"]
            print(f"  ✓ Queue already exists: {queue_url}")
            return queue_url
        print(f"  ✗ Failed: {exc}")
        return None


def create_sns_topic():
    print("Creating SNS topic...")
    try:
        resp = sns.create_topic(Name=SNS_TOPIC_NAME)
        topic_arn = resp["TopicArn"]
        print(f"  ✓ Topic ARN: {topic_arn}")
        return topic_arn
    except ClientError as exc:
        print(f"  ✗ Failed: {exc}")
        return None


def subscribe_email_to_sns(topic_arn: str, email: str):
    """Subscribe an email address to receive clinical alerts."""
    print(f"Subscribing {email} to SNS alerts...")
    try:
        sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=email)
        print(f"  ✓ Confirm the subscription email sent to {email}")
    except ClientError as exc:
        print(f"  ✗ Failed: {exc}")


def print_env_exports(queue_url: str, topic_arn: str):
    """Print the environment variables needed to run the fog node."""
    print("\n" + "="*60)
    print("Copy these exports to your terminal before running the fog node:")
    print("="*60)
    print(f"export SQS_QUEUE_URL='{queue_url}'")
    print(f"export SNS_TOPIC_ARN='{topic_arn}'")
    print(f"export DYNAMODB_TABLE='{TABLE_NAME}'")
    print(f"export AWS_REGION='{REGION}'")
    print("="*60)


def main():
    print("SmartWard — AWS Infrastructure Setup\n")
    ok_table = create_dynamodb_table()
    queue_url = create_sqs_queue()
    topic_arn = create_sns_topic()

    if not all([ok_table, queue_url, topic_arn]):
        print("\n✗ One or more resources failed to create. Check errors above.")
        sys.exit(1)

    # Optionally subscribe an email address for alerts
    email = input("\nEnter email for alert notifications (or press Enter to skip): ").strip()
    if email:
        subscribe_email_to_sns(topic_arn, email)

    print_env_exports(queue_url, topic_arn)
    print("\n✓ Infrastructure ready. Next steps:")
    print("  1. Deploy Lambda functions (see README)")
    print("  2. Set env vars above in your terminal")
    print("  3. Run: python fog_node/fog_node.py")
    print("  4. In separate terminals, run each sensor script")


if __name__ == "__main__":
    main()
