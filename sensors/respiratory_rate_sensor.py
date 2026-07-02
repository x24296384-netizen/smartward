"""
SmartWard - Respiratory Rate Sensor (Mock)
Simulates a patient respiratory rate monitor measuring
breaths per minute. Sends readings to the fog node at a configurable rate.

Normal range: 12-20 breaths per minute (adults)
Clinical alert:
  < 12 breaths/min = bradypnea (dangerously slow breathing)
  > 25 breaths/min = tachypnea (rapid breathing — sign of distress)
"""

import json
import os
import random
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Configuration ────────────────────────────────────────────────────────────
FOG_HOST = os.getenv("FOG_HOST", "127.0.0.1")
FOG_PORT = int(os.getenv("FOG_PORT", "5000"))
SEND_RATE_SECONDS = float(os.getenv("RESP_INTERVAL", "5"))
PATIENT_ID = os.getenv("PATIENT_ID", "P001")
SENSOR_ID = os.getenv("SENSOR_ID", "RESP-WARD-01")

# Clinical ranges (breaths per minute)
NORMAL_MIN = 12
NORMAL_MAX = 20
ALERT_LOW = 12   # bradypnea threshold
ALERT_HIGH = 25  # tachypnea threshold
ANOMALY_CHANCE = 0.05  # 5% chance of abnormal reading


def generate_reading():
    """Generate a respiratory rate reading with realistic noise."""
    if random.random() < ANOMALY_CHANCE:
        # Simulate bradypnea or tachypnea
        if random.random() < 0.4:
            value = random.uniform(6, 11)   # bradypnea
        else:
            value = random.uniform(26, 35)  # tachypnea
    else:
        # Normal reading with small noise (respiratory rate is fairly stable)
        base = random.uniform(NORMAL_MIN, NORMAL_MAX)
        noise = random.gauss(0, 1)
        value = max(4, min(40, base + noise))

    return {
        "sensor_id": SENSOR_ID,
        "patient_id": PATIENT_ID,
        "sensor_type": "respiratory_rate",
        "value": round(value, 1),
        "unit": "breaths/min",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "normal_range": {"min": NORMAL_MIN, "max": NORMAL_MAX},
        "alert_thresholds": {"low": ALERT_LOW, "high": ALERT_HIGH},
    }


def send_to_fog(reading):
    """POST reading to the fog node via HTTP."""
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
        print(f"[RESP] Fog node unreachable: {exc}")
        return False


def run():
    print(f"[RESP] Sensor {SENSOR_ID} starting — interval {SEND_RATE_SECONDS}s")
    while True:
        reading = generate_reading()
        ok = send_to_fog(reading)
        status = "✓" if ok else "✗"
        alert = " *** ALERT ***" if (
            reading["value"] < ALERT_LOW or reading["value"] > ALERT_HIGH
        ) else ""
        print(
            f"[RESP] {status} {reading['value']} {reading['unit']}"
            f"{alert} @ {reading['timestamp']}"
        )
        time.sleep(SEND_RATE_SECONDS)


if __name__ == "__main__":
    run()
