"""
SmartWard - Blood Pressure Sensor (Mock)
Simulates a patient blood pressure monitor measuring systolic and
diastolic pressure. Sends readings to the fog node at a configurable rate.

Normal ranges:
  Systolic:  90-120 mmHg
  Diastolic: 60-80 mmHg

Clinical alert thresholds:
  Systolic > 140 mmHg (hypertension) or < 90 mmHg (hypotension)
  Diastolic > 90 mmHg or < 60 mmHg
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
SEND_RATE_SECONDS = float(os.getenv("BP_INTERVAL", "15"))  # BP measured less frequently
PATIENT_ID = os.getenv("PATIENT_ID", "P001")
SENSOR_ID = os.getenv("SENSOR_ID", "BP-WARD-01")

# Normal ranges (mmHg)
SYSTOLIC_MIN, SYSTOLIC_MAX = 90, 120
DIASTOLIC_MIN, DIASTOLIC_MAX = 60, 80
ANOMALY_CHANCE = 0.05  # 5% chance of hypertensive/hypotensive reading


def generate_reading():
    """Generate a blood pressure reading with realistic noise."""
    if random.random() < ANOMALY_CHANCE:
        # Simulate hypertension (high) or hypotension (low)
        if random.random() < 0.7:
            # Hypertension — more common anomaly
            systolic = random.uniform(141, 180)
            diastolic = random.uniform(91, 110)
        else:
            # Hypotension
            systolic = random.uniform(70, 89)
            diastolic = random.uniform(40, 59)
    else:
        # Normal reading with Gaussian noise
        systolic = random.uniform(SYSTOLIC_MIN, SYSTOLIC_MAX) + random.gauss(0, 4)
        diastolic = random.uniform(DIASTOLIC_MIN, DIASTOLIC_MAX) + random.gauss(0, 3)
        # Ensure diastolic is always lower than systolic
        diastolic = min(diastolic, systolic - 20)

    return {
        "sensor_id": SENSOR_ID,
        "patient_id": PATIENT_ID,
        "sensor_type": "blood_pressure",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "readings": {
            "systolic": {
                "value": round(systolic, 1),
                "unit": "mmHg",
                "normal_range": {"min": SYSTOLIC_MIN, "max": SYSTOLIC_MAX},
                "alert": not (SYSTOLIC_MIN <= systolic <= SYSTOLIC_MAX),
            },
            "diastolic": {
                "value": round(diastolic, 1),
                "unit": "mmHg",
                "normal_range": {"min": DIASTOLIC_MIN, "max": DIASTOLIC_MAX},
                "alert": not (DIASTOLIC_MIN <= diastolic <= DIASTOLIC_MAX),
            },
        },
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
        print(f"[BP] Fog node unreachable: {exc}")
        return False


def run():
    print(f"[BP] Sensor {SENSOR_ID} starting — interval {SEND_RATE_SECONDS}s")
    while True:
        reading = generate_reading()
        ok = send_to_fog(reading)
        status = "✓" if ok else "✗"
        sys_val = reading["readings"]["systolic"]["value"]
        dia_val = reading["readings"]["diastolic"]["value"]
        sys_alert = " [ALERT]" if reading["readings"]["systolic"]["alert"] else ""
        dia_alert = " [ALERT]" if reading["readings"]["diastolic"]["alert"] else ""
        print(
            f"[BP] {status} {sys_val}/{dia_val} mmHg"
            f"{sys_alert}{dia_alert} @ {reading['timestamp']}"
        )
        time.sleep(SEND_RATE_SECONDS)


if __name__ == "__main__":
    run()
