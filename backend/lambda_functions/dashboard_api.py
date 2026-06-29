"""
SmartWard - Lambda: Dashboard API
Serves JSON data for the monitoring dashboard.
Triggered by API Gateway (HTTP GET requests).

Endpoints:
  GET /readings?sensor_type=heart_rate&patient_id=P001&limit=50
  GET /readings?sensor_type=spo2&patient_id=P001
  GET /readings?sensor_type=temperature&ward_id=WARD-A
  GET /readings?sensor_type=humidity&ward_id=WARD-A
  GET /alerts?limit=20

Env vars required:
  DYNAMODB_TABLE — name of the readings table
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
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)


def cors_response(status_code: int, body: dict) -> dict:
    """Wrap response with CORS headers for the dashboard."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body, default=str),
    }


def get_readings(sensor_type: str, entity_id: str, entity_type: str, limit: int) -> list[dict]:
    """
    Query DynamoDB for recent readings.
    PK pattern: PATIENT#<patient_id> or WARD#<ward_id>
    SK pattern: <sensor_type>#<timestamp>
    """
    pk = f"{entity_type}#{entity_id}"
    sk_prefix = f"{sensor_type}#"

    try:
        resp = _table.query(
            KeyConditionExpression=(
                Key("pk").eq(pk) & Key("sk").begins_with(sk_prefix)
            ),
            Limit=limit,
            ScanIndexForward=False,  # newest first
        )
        items = resp.get("Items", [])
        # Convert Decimal to float for JSON serialisation
        return [{k: float(v) if hasattr(v, "as_tuple") else v for k, v in item.items()} for item in items]
    except Exception as exc:
        log.error("DynamoDB query failed: %s", exc)
        return []


def get_alerts(limit: int) -> list[dict]:
    """Scan for recent alert readings (fog_alert == True)."""
    try:
        resp = _table.scan(
            FilterExpression=Attr("fog_alert").eq(True),
            Limit=limit * 3,  # over-fetch before sorting
        )
        items = resp.get("Items", [])
        # Sort by timestamp descending
        items.sort(key=lambda x: x.get("sk", ""), reverse=True)
        return items[:limit]
    except Exception as exc:
        log.error("DynamoDB scan failed: %s", exc)
        return []


def lambda_handler(event, context):
    """Route API Gateway GET requests."""
    path = event.get("path", "/")
    params = event.get("queryStringParameters") or {}
    method = event.get("httpMethod", "GET")

    if method == "OPTIONS":
        return cors_response(200, {})

    if path == "/alerts":
        limit = min(int(params.get("limit", 20)), 100)
        alerts = get_alerts(limit)
        return cors_response(200, {
            "alerts": alerts,
            "count": len(alerts),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        })

    if path == "/readings":
        sensor_type = params.get("sensor_type", "heart_rate")
        limit = min(int(params.get("limit", 50)), 200)

        # Determine entity (patient vs ward)
        if sensor_type in ("heart_rate", "spo2"):
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

    return cors_response(404, {"error": "Not found", "path": path})
