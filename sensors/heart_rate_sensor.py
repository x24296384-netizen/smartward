"""
SmartWard - Heart Rate Sensor (Mock)
Simulates a patient wearable heart rate monitor.
Sends readings to the fog node at a configurable rate.
"""

import json
import os
import random
import socket
import time
from datetime import datetime, timezone

# ── Configuration ────────────────────────────────────────────────────────────
FOG_HOST = os.getenv("FOG_HOST", "127.0.0.1")
FOG_PORT = int(os.getenv("FOG_PORT", "5000"))
SEND_RATE_SECONDS = float(os.getenv("HEART_RATE_INTERVAL", "2"))  # readings per interval
PATIENT_ID = os.getenv("PATIENT_ID", "P001")
SENSOR_ID = os.getenv("SENSOR_ID", "HR-WARD-01")

# Simulated normal range (bpm)
NORMAL_MIN = 60
NORMAL_MAX = 100
# Occasional anomalies: 5% chance of abnormal reading
ANOMALY_CHANCE = 0.05


def generate_reading() -> dict:
    """Generate a single heart rate reading with realistic noise."""
    if random.random() < ANOMALY_CHANCE:
        # Simulate bradycardia (<60) or tachycardia (>100)
        value = random.choice([
            random.uniform(30, 55),   # bradycardia
            random.uniform(105, 150), # tachycardia
        ])
    else:
        base = random.uniform(NORMAL_MIN, NORMAL_MAX)
        noise = random.gauss(0, 3)    # ±3 bpm Gaussian noise
        value = max(20, min(220, base + noise))

    return {
        "sensor_id": SENSOR_ID,
        "patient_id": PATIENT_ID,
        "sensor_type": "heart_rate",
        "value": round(value, 1),
        "unit": "bpm",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "normal_range": {"min": NORMAL_MIN, "max": NORMAL_MAX},
    }


def send_to_fog(reading: dict) -> bool:
    """POST reading to the fog node via HTTP."""
    import urllib.request
    import urllib.error

    url = f"http://{FOG_HOST}:{FOG_PORT}/ingest"
    data = json.dumps(reading).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError) as exc:
        print(f"[HR] Fog node unreachable: {exc}")
        return False


def run():
    print(f"[HR] Sensor {SENSOR_ID} starting — interval {SEND_RATE_SECONDS}s")
    while True:
        reading = generate_reading()
        ok = send_to_fog(reading)
        status = "✓" if ok else "✗"
        print(f"[HR] {status} {reading['value']} {reading['unit']} @ {reading['timestamp']}")
        time.sleep(SEND_RATE_SECONDS)


if __name__ == "__main__":
    run()
