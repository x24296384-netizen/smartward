"""
SmartWard - SpO2 (Blood Oxygen) Sensor (Mock)
Simulates a pulse oximeter monitoring blood oxygen saturation.
Sends readings to the fog node at a configurable rate.
Clinical alert threshold: SpO2 < 90% requires immediate intervention.
"""

import json
import os
import random
import time
from datetime import datetime, timezone

FOG_HOST = os.getenv("FOG_HOST", "127.0.0.1")
FOG_PORT = int(os.getenv("FOG_PORT", "5000"))
SEND_RATE_SECONDS = float(os.getenv("SPO2_INTERVAL", "3"))
PATIENT_ID = os.getenv("PATIENT_ID", "P001")
SENSOR_ID = os.getenv("SENSOR_ID", "SPO2-WARD-01")

# Clinical ranges (%)
NORMAL_MIN = 95
NORMAL_MAX = 100
ALERT_THRESHOLD = 90   # below this triggers critical alert
ANOMALY_CHANCE = 0.04  # 4% chance of low reading


def generate_reading() -> dict:
    """Generate a SpO2 reading. Values are percentages (0–100)."""
    if random.random() < ANOMALY_CHANCE:
        # Simulate hypoxia
        value = random.uniform(82, 89)
    else:
        base = random.uniform(NORMAL_MIN, NORMAL_MAX)
        noise = random.gauss(0, 0.5)   # SpO2 sensors are precise; small noise
        value = max(70, min(100, base + noise))

    return {
        "sensor_id": SENSOR_ID,
        "patient_id": PATIENT_ID,
        "sensor_type": "spo2",
        "value": round(value, 1),
        "unit": "%",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "normal_range": {"min": NORMAL_MIN, "max": NORMAL_MAX},
        "alert_threshold": ALERT_THRESHOLD,
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
        print(f"[SPO2] Fog node unreachable: {exc}")
        return False


def run():
    print(f"[SPO2] Sensor {SENSOR_ID} starting — interval {SEND_RATE_SECONDS}s")
    while True:
        reading = generate_reading()
        ok = send_to_fog(reading)
        status = "✓" if ok else "✗"
        alert = " *** ALERT ***" if reading["value"] < ALERT_THRESHOLD else ""
        print(f"[SPO2] {status} {reading['value']}{reading['unit']}{alert} @ {reading['timestamp']}")
        time.sleep(SEND_RATE_SECONDS)


if __name__ == "__main__":
    run()
