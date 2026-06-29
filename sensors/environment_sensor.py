"""
SmartWard - Room Temperature & Humidity Sensor (Mock)
Simulates an environmental sensor monitoring ward conditions.
Temperature and humidity affect patient comfort and infection risk.
Sends readings to the fog node at a configurable rate.
"""

import json
import os
import random
import time
from datetime import datetime, timezone

FOG_HOST = os.getenv("FOG_HOST", "127.0.0.1")
FOG_PORT = int(os.getenv("FOG_PORT", "5000"))
SEND_RATE_SECONDS = float(os.getenv("ENV_INTERVAL", "10"))
WARD_ID = os.getenv("WARD_ID", "WARD-A")
SENSOR_ID = os.getenv("SENSOR_ID", "ENV-WARD-01")

# NHS recommended ward environment ranges
TEMP_MIN, TEMP_MAX = 18.0, 24.0       # °C
HUMIDITY_MIN, HUMIDITY_MAX = 40, 60   # %RH

# Drift model: temperature slowly drifts over time
_temp_drift = 21.0
_humidity_drift = 50.0


def generate_reading() -> dict:
    """Generate correlated temperature + humidity readings with slow drift."""
    global _temp_drift, _humidity_drift

    # Random walk — small step each cycle
    _temp_drift += random.gauss(0, 0.1)
    _temp_drift = max(15.0, min(30.0, _temp_drift))

    _humidity_drift += random.gauss(0, 0.3)
    _humidity_drift = max(20.0, min(80.0, _humidity_drift))

    temperature = round(_temp_drift + random.gauss(0, 0.2), 2)
    humidity = round(_humidity_drift + random.gauss(0, 0.5), 1)

    return {
        "sensor_id": SENSOR_ID,
        "ward_id": WARD_ID,
        "sensor_type": "environment",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "readings": {
            "temperature": {
                "value": temperature,
                "unit": "°C",
                "normal_range": {"min": TEMP_MIN, "max": TEMP_MAX},
                "alert": not (TEMP_MIN <= temperature <= TEMP_MAX),
            },
            "humidity": {
                "value": humidity,
                "unit": "%RH",
                "normal_range": {"min": HUMIDITY_MIN, "max": HUMIDITY_MAX},
                "alert": not (HUMIDITY_MIN <= humidity <= HUMIDITY_MAX),
            },
        },
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
        print(f"[ENV] Fog node unreachable: {exc}")
        return False


def run():
    print(f"[ENV] Sensor {SENSOR_ID} starting — interval {SEND_RATE_SECONDS}s")
    while True:
        reading = generate_reading()
        ok = send_to_fog(reading)
        status = "✓" if ok else "✗"
        t = reading["readings"]["temperature"]
        h = reading["readings"]["humidity"]
        t_alert = " [TEMP ALERT]" if t["alert"] else ""
        h_alert = " [HUMIDITY ALERT]" if h["alert"] else ""
        print(f"[ENV] {status} {t['value']}°C{t_alert} | {h['value']}%RH{h_alert} @ {reading['timestamp']}")
        time.sleep(SEND_RATE_SECONDS)


if __name__ == "__main__":
    run()
