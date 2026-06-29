"""
SmartWard - Unit Tests
Tests fog node validation and alert detection logic.
Uses moto for mocked AWS services (no real AWS calls).
Run: pytest tests/ -v
"""

import json
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fog_node.fog_node import validate, detect_alert


# ── Validation tests ──────────────────────────────────────────────────────────

class TestValidation:
    def test_valid_heart_rate(self):
        reading = {"sensor_type": "heart_rate", "value": 75.0}
        ok, reason = validate(reading)
        assert ok, reason

    def test_invalid_heart_rate_too_low(self):
        reading = {"sensor_type": "heart_rate", "value": 10.0}
        ok, reason = validate(reading)
        assert not ok

    def test_invalid_heart_rate_too_high(self):
        reading = {"sensor_type": "heart_rate", "value": 300.0}
        ok, reason = validate(reading)
        assert not ok

    def test_valid_spo2(self):
        reading = {"sensor_type": "spo2", "value": 98.0}
        ok, reason = validate(reading)
        assert ok, reason

    def test_invalid_spo2_impossible(self):
        reading = {"sensor_type": "spo2", "value": 110.0}
        ok, reason = validate(reading)
        assert not ok

    def test_valid_environment(self):
        reading = {
            "sensor_type": "environment",
            "readings": {
                "temperature": {"value": 21.0, "unit": "°C", "alert": False},
                "humidity": {"value": 50.0, "unit": "%RH", "alert": False},
            }
        }
        ok, reason = validate(reading)
        assert ok, reason

    def test_environment_missing_readings(self):
        reading = {"sensor_type": "environment", "readings": {}}
        ok, reason = validate(reading)
        assert not ok

    def test_unknown_sensor_type(self):
        reading = {"sensor_type": "pressure", "value": 1013.0}
        ok, reason = validate(reading)
        assert not ok

    def test_missing_value_field(self):
        reading = {"sensor_type": "heart_rate"}
        ok, reason = validate(reading)
        assert not ok


# ── Alert detection tests ─────────────────────────────────────────────────────

class TestAlertDetection:
    def test_normal_heart_rate_no_alert(self):
        reading = {"sensor_type": "heart_rate", "value": 72.0}
        assert not detect_alert(reading)

    def test_bradycardia_triggers_alert(self):
        reading = {"sensor_type": "heart_rate", "value": 38.0}
        assert detect_alert(reading)

    def test_tachycardia_triggers_alert(self):
        reading = {"sensor_type": "heart_rate", "value": 145.0}
        assert detect_alert(reading)

    def test_normal_spo2_no_alert(self):
        reading = {"sensor_type": "spo2", "value": 97.0}
        assert not detect_alert(reading)

    def test_hypoxia_triggers_alert(self):
        reading = {"sensor_type": "spo2", "value": 87.0}
        assert detect_alert(reading)

    def test_environment_normal_no_alert(self):
        reading = {
            "sensor_type": "environment",
            "readings": {
                "temperature": {"value": 21.0},
                "humidity": {"value": 50.0},
            }
        }
        assert not detect_alert(reading)

    def test_environment_high_temp_triggers_alert(self):
        reading = {
            "sensor_type": "environment",
            "readings": {
                "temperature": {"value": 30.0},
                "humidity": {"value": 50.0},
            }
        }
        assert detect_alert(reading)

    def test_environment_low_humidity_triggers_alert(self):
        reading = {
            "sensor_type": "environment",
            "readings": {
                "temperature": {"value": 21.0},
                "humidity": {"value": 25.0},
            }
        }
        assert detect_alert(reading)
