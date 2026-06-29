"""
SmartWard - Lambda: SQS Processor
Triggered by SQS messages from the fog node.
Writes individual readings to DynamoDB and raises SNS alerts.

Deploy: zip this file and upload to Lambda (Python 3.12 runtime).
Env vars required:
  DYNAMODB_TABLE  — name of the readings table
  SNS_TOPIC_ARN   — ARN of the alert topic
  AWS_REGION      — e.g. us-east-1 (auto-set in Lambda env)
"""

import json
import logging
import os
import time
import uuid

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

_dynamodb = boto3.resource("dynamodb")
_sns = boto3.client("sns")
_table = _dynamodb.Table(TABLE_NAME)


def flatten_reading(reading: dict) -> list[dict]:
    """
    Convert a single sensor reading dict into one or more DynamoDB items.
    Environment readings produce two items (temperature + humidity).
    """
    sensor_type = reading.get("sensor_type", "unknown")
    base = {
        "reading_id": str(uuid.uuid4()),
        "timestamp": reading.get("timestamp", ""),
        "fog_received_at": reading.get("fog_received_at", ""),
        "fog_alert": reading.get("fog_alert", False),
        "sensor_id": reading.get("sensor_id", ""),
        "sensor_type": sensor_type,
        "ttl": int(time.time()) + 7 * 24 * 3600,  # auto-expire after 7 days
    }

    if sensor_type == "environment":
        items = []
        ward_id = reading.get("ward_id", "")
        for metric, data in reading.get("readings", {}).items():
            item = {
                **base,
                "reading_id": str(uuid.uuid4()),
                "sensor_type": metric,
                "ward_id": ward_id,
                "value": str(data.get("value", 0)),   # DynamoDB Decimal-safe
                "unit": data.get("unit", ""),
                "alert": data.get("alert", False),
                "pk": f"WARD#{ward_id}",
                "sk": f"{metric}#{reading.get('timestamp', '')}",
            }
            items.append(item)
        return items

    # Heart rate / SpO2
    item = {
        **base,
        "patient_id": reading.get("patient_id", ""),
        "value": str(reading.get("value", 0)),
        "unit": reading.get("unit", ""),
        "pk": f"PATIENT#{reading.get('patient_id', '')}",
        "sk": f"{sensor_type}#{reading.get('timestamp', '')}",
    }
    return [item]


def write_to_dynamodb(items: list[dict]):
    """Batch write items to DynamoDB."""
    with _table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)


def send_alert(reading: dict, batch_id: str):
    """Publish a clinical alert to SNS."""
    sensor_type = reading.get("sensor_type", "unknown")
    value = reading.get("value", "N/A")
    patient = reading.get("patient_id", reading.get("ward_id", "unknown"))

    subject = f"SmartWard ALERT: {sensor_type} ({patient})"
    message = (
        f"Clinical alert detected by fog node.\n\n"
        f"Batch ID  : {batch_id}\n"
        f"Sensor    : {reading.get('sensor_id', 'N/A')}\n"
        f"Type      : {sensor_type}\n"
        f"Value     : {value} {reading.get('unit', '')}\n"
        f"Patient   : {patient}\n"
        f"Timestamp : {reading.get('timestamp', 'N/A')}\n"
    )
    try:
        _sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
        log.info("SNS alert sent for %s %s", sensor_type, patient)
    except ClientError as exc:
        log.error("SNS publish failed: %s", exc)


def lambda_handler(event, context):
    """
    Entry point. Each SQS event record contains one fog batch message.
    Lambda concurrency handles multiple records in parallel automatically.
    """
    processed = 0
    alerts_sent = 0

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
        except (json.JSONDecodeError, KeyError) as exc:
            log.error("Could not parse SQS record body: %s", exc)
            continue

        batch_id = body.get("batch_id", "unknown")
        readings = body.get("readings", [])
        log.info("Processing batch %s — %d readings", batch_id, len(readings))

        all_items = []
        for reading in readings:
            items = flatten_reading(reading)
            all_items.extend(items)

            if reading.get("fog_alert"):
                send_alert(reading, batch_id)
                alerts_sent += 1

        if all_items:
            write_to_dynamodb(all_items)
            processed += len(all_items)
            log.info("Wrote %d items to DynamoDB", len(all_items))

    return {
        "statusCode": 200,
        "body": json.dumps({
            "processed_items": processed,
            "alerts_sent": alerts_sent,
        }),
    }
