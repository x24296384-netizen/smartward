"""
SmartWard - Lambda: SQS Processor
Triggered by SQS messages from the fog node.
Writes individual readings to DynamoDB and raises SNS alerts
for readings flagged as clinical anomalies by the fog node.

Deploy: zip this file and upload to Lambda (Python 3.12 runtime).
Required environment variables:
  DYNAMODB_TABLE  — name of the readings table (smartward-readings)
  SNS_TOPIC_ARN   — ARN of the alert topic (smartward-alerts)
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

# Read configuration from Lambda environment variables
TABLE_NAME = os.environ["DYNAMODB_TABLE"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]

# Initialise AWS clients once at module level (reused across invocations)
_dynamodb = boto3.resource("dynamodb")
_sns = boto3.client("sns")
_table = _dynamodb.Table(TABLE_NAME)


def flatten_reading(reading):
    """
    Convert a single fog-node reading dict into one or more DynamoDB items.
    Environment readings produce two items (temperature + humidity) because
    they contain nested sub-readings rather than a single scalar value.

    DynamoDB key design:
      pk (partition key): PATIENT#<patient_id> or WARD#<ward_id>
      sk (sort key):      <sensor_type>#<timestamp>
    This enables efficient time-range queries per patient or ward.
    """
    sensor_type = reading.get("sensor_type", "unknown")

    # Common fields shared across all sensor types
    base = {
        "reading_id": str(uuid.uuid4()),          # unique ID for this item
        "timestamp": reading.get("timestamp", ""),
        "fog_received_at": reading.get("fog_received_at", ""),
        "fog_alert": reading.get("fog_alert", False),  # clinical alert flag set by fog node
        "sensor_id": reading.get("sensor_id", ""),
        "sensor_type": sensor_type,
        "ttl": int(time.time()) + 7 * 24 * 3600,  # auto-expire after 7 days
    }

    if sensor_type == "environment":
        # Environment sensor has nested temperature + humidity readings
        # Split into two separate DynamoDB items for easier querying
        items = []
        ward_id = reading.get("ward_id", "")
        for metric, data in reading.get("readings", {}).items():
            item = {
                **base,
                "reading_id": str(uuid.uuid4()),  # each sub-reading gets its own ID
                "sensor_type": metric,             # "temperature" or "humidity"
                "ward_id": ward_id,
                "value": str(data.get("value", 0)),  # store as string (DynamoDB Decimal-safe)
                "unit": data.get("unit", ""),
                "alert": data.get("alert", False),
                "pk": f"WARD#{ward_id}",
                "sk": f"{metric}#{reading.get('timestamp', '')}",
            }
            items.append(item)
        return items

    # Heart rate and SpO2: single scalar value per reading
    item = {
        **base,
        "patient_id": reading.get("patient_id", ""),
        "value": str(reading.get("value", 0)),  # string for DynamoDB Decimal compatibility
        "unit": reading.get("unit", ""),
        "pk": f"PATIENT#{reading.get('patient_id', '')}",
        "sk": f"{sensor_type}#{reading.get('timestamp', '')}",
    }
    return [item]


def write_to_dynamodb(items):
    """
    Batch write a list of items to DynamoDB.
    batch_writer handles automatic batching in groups of 25 (DynamoDB limit)
    and retries any unprocessed items automatically.
    """
    with _table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)


def send_alert(reading, batch_id):
    """
    Publish a clinical alert notification to the SNS topic.
    SNS will fan out the message to all subscribed endpoints (email, SMS).
    """
    sensor_type = reading.get("sensor_type", "unknown")
    value = reading.get("value", "N/A")
    # Use patient_id for clinical sensors, ward_id for environment
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
    Lambda entry point. Triggered by SQS with a batch of fog node messages.
    Each SQS record contains one fog batch (up to MAX_BATCH_SIZE readings).
    Lambda concurrency handles multiple SQS records in parallel automatically.
    """
    processed = 0
    alerts_sent = 0

    for record in event.get("Records", []):
        # Parse the SQS message body (JSON string)
        try:
            body = json.loads(record["body"])
        except (json.JSONDecodeError, KeyError) as exc:
            log.error("Could not parse SQS record body: %s", exc)
            continue  # skip malformed records; do not block the batch

        batch_id = body.get("batch_id", "unknown")
        readings = body.get("readings", [])
        log.info("Processing batch %s — %d readings", batch_id, len(readings))

        all_items = []
        for reading in readings:
            # Flatten reading into DynamoDB items (1 or 2 per reading)
            items = flatten_reading(reading)
            all_items.extend(items)

            # Send SNS alert if fog node flagged this reading as a clinical anomaly
            if reading.get("fog_alert"):
                send_alert(reading, batch_id)
                alerts_sent += 1

        # Write all items for this batch in one DynamoDB batch operation
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
