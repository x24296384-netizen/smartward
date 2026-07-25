"""
SmartWard - Lambda: Dashboard API
Serves JSON data for the monitoring dashboard via API Gateway.
Triggered by HTTP GET requests from the frontend dashboard.

Required environment variable:
  DYNAMODB_TABLE — name of the readings table (smartward-readings)

Endpoints (configured in API Gateway):
  GET /readings?sensor_type=heart_rate&patient_id=P001&limit=50
  GET /readings?sensor_type=spo2&patient_id=P001
  GET /readings?sensor_type=systolic&patient_id=P001
  GET /readings?sensor_type=diastolic&patient_id=P001
  GET /readings?sensor_type=temperature&ward_id=WARD-A
  GET /readings?sensor_type=humidity&ward_id=WARD-A
  GET /alerts?limit=20
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key, Attr

log = logging.getLogger()
log.setLevel(logging.INFO)

TABLE_NAME = os.environ["DYNAMODB_TABLE"]

# Initialise DynamoDB resource once at module level for connection reuse
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)


def cors_response(status_code, body):
    """
    Wrap API response with CORS headers to allow the dashboard
    (served from a different origin) to call this API.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",       # allow any origin for demo
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body, default=str),  # default=str handles Decimal types
    }


def get_readings(sensor_type, entity_id, entity_type, limit):
    """
    Query DynamoDB for recent readings using the composite key pattern.
    Results are returned newest-first (ScanIndexForward=False).

    Key pattern:
      pk = PATIENT#<patient_id>  (heart_rate, spo2, systolic, diastolic, respiratory_rate)
      pk = WARD#<ward_id>        (temperature, humidity)
      sk begins_with <sensor_type>#  (to filter by sensor type)
    """
    pk = f"{entity_type}#{entity_id}"
    sk_prefix = f"{sensor_type}#"

    try:
        resp = _table.query(
            KeyConditionExpression=(
                Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix)
            ),
            Limit=limit,
            ScanIndexForward=False,  # newest readings first
        )
        items = resp.get("Items", [])
        # Convert DynamoDB Decimal types to float for JSON serialisation
        return [
            {k: float(v) if hasattr(v, "as_tuple") else v for k, v in item.items()}
            for item in items
        ]
    except Exception as exc:
        log.error("DynamoDB query failed: %s", exc)
        return []


def get_alerts(limit):
    """
    Scan DynamoDB for recent readings where fog_alert is True.
    Uses a scan (not query) because alerts can come from any patient or ward.
    Over-fetches then sorts and truncates to return the most recent alerts.
    """
    try:
        # Scan with filter — over-fetch to account for pagination limits
        resp = _table.scan(
            FilterExpression=Attr("fog_alert").eq(True),
            Limit=limit * 3,
        )
        items = resp.get("Items", [])
        # Sort by sort key (which starts with sensor_type#timestamp) descending
        items.sort(key=lambda x: x.get("sk", ""), reverse=True)
        return items[:limit]  # return only the requested number
    except Exception as exc:
        log.error("DynamoDB scan failed: %s", exc)
        return []


def lambda_handler(event, context):
    """
    API Gateway Lambda proxy integration entry point.
    Routes GET requests to the appropriate DynamoDB query function.

    Supports both REST API (v1) and HTTP API (v2) event formats:
      REST API (v1): path is at event["path"], method at event["httpMethod"]
      HTTP API (v2):  path is at event["rawPath"], method at
                       event["requestContext"]["http"]["method"]
    """
    # Path: try v1 key first, fall back to v2 key
    path = event.get("path") or event.get("rawPath", "/")

    # HTTP APIs (v2) prefix rawPath with the stage name (e.g. "/prod/readings")
    # Strip it so routing below still matches "/readings"
    if path.startswith("/prod/"):
        path = path[len("/prod"):]
    elif path == "/prod":
        path = "/"

    params = event.get("queryStringParameters") or {}  # None if no query params

    # Method: try v1 key first, fall back to v2 nested key
    method = event.get("httpMethod") or event.get(
        "requestContext", {}
    ).get("http", {}).get("method", "GET")

    # Handle CORS preflight requests from the browser
    if method == "OPTIONS":
        return cors_response(200, {})

    if path == "/alerts":
        limit = min(int(params.get("limit", 20)), 100)  # cap at 100
        alerts = get_alerts(limit)
        return cors_response(200, {
            "alerts": alerts,
            "count": len(alerts),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if path == "/readings":
        sensor_type = params.get("sensor_type", "heart_rate")
        limit = min(int(params.get("limit", 50)), 200)  # cap at 200

        # Determine DynamoDB partition key based on sensor type
        # Patient sensors: HR, SpO2, systolic, diastolic, respiratory rate
        # Ward sensors: temperature, humidity
        if sensor_type in (
            "heart_rate", "spo2", "systolic", "diastolic", "respiratory_rate"
        ):
            entity_id = params.get("patient_id", "P001")
            entity_type = "PATIENT"
        else:
            entity_id = params.get("ward_id", "WARD-A")
            entity_type = "WARD"

        readings = get_readings(sensor_type, entity_id, entity_type, limit)
        return cors_response(200, {
            "sensor_type": sensor_type,
            "entity_id": entity_id,
            "readings": readings,
            "count": len(readings),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Unknown path
    return cors_response(404, {"error": "Not found", "path": path})
    