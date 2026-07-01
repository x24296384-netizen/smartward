"""
SmartWard - Virtual Fog Node
Receives sensor readings via HTTP, validates and aggregates them,
detects threshold breaches, then dispatches batches to AWS SQS.

Fog node responsibilities (per Fog/Edge computing principles):
  1. Receive data from multiple sensor streams
  2. Validate and filter out-of-range / malformed readings
  3. Aggregate readings into time-window batches (reduces cloud calls)
  4. Detect critical alerts and flag them for priority processing
  5. Dispatch payload to cloud backend (SQS) over HTTPS
"""

import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# ── Configuration ────────────────────────────────────────────────────────────
FOG_HOST = os.getenv("FOG_HOST", "0.0.0.0")
FOG_PORT = int(os.getenv("FOG_PORT", "5000"))
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")   # set in env before running
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BATCH_INTERVAL_SECONDS = float(os.getenv("BATCH_INTERVAL", "10"))
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "20"))

# Per-sensor validation rules
VALIDATION_RULES = {
    "heart_rate": {"min": 20, "max": 250, "field": "value"},
    "spo2":       {"min": 50, "max": 100, "field": "value"},
    "environment": None,  # validated per sub-reading inside the payload
}

# Alert thresholds (fog-level detection — fast local response)
ALERT_THRESHOLDS = {
    "heart_rate": {"low": 40, "high": 130},
    "spo2":       {"low": 90, "high": None},
    "temperature": {"low": 16, "high": 26},
    "humidity":   {"low": 30, "high": 70},
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FOG] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fog_node")

# ── In-memory buffer ─────────────────────────────────────────────────────────
_buffer = []
_buffer_lock = threading.Lock()
_stats = defaultdict(int)   # message counts per sensor type


# ── Validation ───────────────────────────────────────────────────────────────

def validate(reading):
    """Return (is_valid, reason). Rejects malformed or physically impossible readings."""
    sensor_type = reading.get("sensor_type")
    if sensor_type not in VALIDATION_RULES:
        return False, f"Unknown sensor_type: {sensor_type}"

    if sensor_type == "environment":
        # Validate each sub-reading
        readings = reading.get("readings", {})
        if not readings:
            return False, "Environment reading missing 'readings' dict"
        return True, "ok"

    rule = VALIDATION_RULES[sensor_type]
    value = reading.get(rule["field"])
    if value is None:
        return False, f"Missing field '{rule['field']}'"
    if not (rule["min"] <= value <= rule["max"]):
        return False, (
            f"{sensor_type} value {value} outside physical range "
            f"[{rule['min']}, {rule['max']}]"
        )

    return True, "ok"


def detect_alert(reading: dict) -> bool:
    """Return True if reading breaches a clinical alert threshold."""
    sensor_type = reading.get("sensor_type")

    # Environment sensor has nested readings — handle before threshold lookup
    if sensor_type == "environment":
        r = reading.get("readings", {})
        t_val = r.get("temperature", {}).get("value")
        h_val = r.get("humidity", {}).get("value")
        t_thr = ALERT_THRESHOLDS["temperature"]
        h_thr = ALERT_THRESHOLDS["humidity"]
        t_alert = (
            t_val is not None
            and (t_val < t_thr["low"] or (t_thr["high"] and t_val > t_thr["high"]))
        )
        h_alert = (
            h_val is not None
            and (h_val < h_thr["low"] or (h_thr["high"] and h_val > h_thr["high"]))
        )
        return t_alert or h_alert

    # For scalar sensors, look up threshold by sensor type
    thresholds = ALERT_THRESHOLDS.get(sensor_type)
    if thresholds is None:
        return False  # unknown sensor type — no alert

    value = reading.get("value", 0)
    low = thresholds.get("low")
    high = thresholds.get("high")
    if low is not None and value < low:
        return True
    if high is not None and value > high:
        return True
    return False


# ── HTTP server (receives sensor data) ───────────────────────────────────────

class FogHandler(BaseHTTPRequestHandler):
    """Handles POST /ingest from sensors and GET /health for monitoring."""

    def log_message(self, fmt, *args):
        pass  # suppress default HTTP logs; use our own logger

    def do_GET(self):
        if self.path == "/health":
            with _buffer_lock:
                buf_size = len(_buffer)
            body = json.dumps({
                "status": "ok",
                "buffer_size": buf_size,
                "stats": dict(_stats),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/ingest":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = self.rfile.read(length)
            reading = json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            log.warning("Invalid JSON from sensor: %s", exc)
            self.send_response(400)
            self.end_headers()
            return

        is_valid, reason = validate(reading)
        if not is_valid:
            log.warning("Rejected reading — %s", reason)
            self.send_response(422)
            self.end_headers()
            return

        # Tag alert status at fog layer (enables priority routing in cloud)
        reading["fog_alert"] = detect_alert(reading)
        reading["fog_received_at"] = datetime.now(timezone.utc).isoformat()

        if reading["fog_alert"]:
            log.warning(
                "ALERT detected — %s %s",
                reading.get("sensor_type"),
                reading.get("value", ""),
            )

        with _buffer_lock:
            _buffer.append(reading)
            _stats[reading.get("sensor_type", "unknown")] += 1

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')


# ── SQS dispatcher ───────────────────────────────────────────────────────────

def build_sqs_client():
    """Return a boto3 SQS client using env credentials (AWS Academy compatible)."""
    return boto3.client("sqs", region_name=AWS_REGION)


def dispatch_batch(batch, sqs_client):
    """Send a batch of readings to SQS as a single message."""
    if not SQS_QUEUE_URL:
        log.error("SQS_QUEUE_URL not set — cannot dispatch")
        return False

    payload = {
        "batch_id": f"fog-{int(time.time())}",
        "dispatched_at": datetime.now(timezone.utc).isoformat(),
        "reading_count": len(batch),
        "has_alerts": any(r.get("fog_alert") for r in batch),
        "readings": batch,
    }
    body = json.dumps(payload)

    try:
        sqs_client.send_message(
            QueueUrl=SQS_QUEUE_URL,
            MessageBody=body,
            MessageAttributes={
                "source": {"DataType": "String", "StringValue": "fog_node"},
                "has_alerts": {
                    "DataType": "String",
                    "StringValue": str(payload["has_alerts"]).lower(),
                },
            },
        )
        log.info("Dispatched batch of %d readings (alerts=%s)", len(batch), payload["has_alerts"])
        return True
    except (BotoCoreError, ClientError) as exc:
        log.error("SQS dispatch failed: %s", exc)
        return False


def dispatcher_loop(sqs_client):
    """Background thread: flush buffer to SQS every BATCH_INTERVAL_SECONDS."""
    while True:
        time.sleep(BATCH_INTERVAL_SECONDS)
        with _buffer_lock:
            if not _buffer:
                continue
            batch = _buffer[:MAX_BATCH_SIZE]
            del _buffer[:MAX_BATCH_SIZE]

        dispatch_batch(batch, sqs_client)


# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    log.info("Fog node starting on %s:%d", FOG_HOST, FOG_PORT)
    log.info("Batch interval: %ss | Max batch size: %d", BATCH_INTERVAL_SECONDS, MAX_BATCH_SIZE)
    log.info("SQS queue: %s", SQS_QUEUE_URL or "(NOT SET)")

    sqs = build_sqs_client()

    # Start background dispatcher thread
    dispatcher = threading.Thread(target=dispatcher_loop, args=(sqs,), daemon=True)
    dispatcher.start()

    server = HTTPServer((FOG_HOST, FOG_PORT), FogHandler)
    log.info("Fog node listening — POST to http://%s:%d/ingest", FOG_HOST, FOG_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Fog node shutting down")
        server.shutdown()


if __name__ == "__main__":
    run()
