#!/usr/bin/env python3
"""Publica o estado do BMS no Mosquitto + auto-descoberta no Home Assistant."""
import json
import os
import time

import paho.mqtt.client as mqtt

BASE = os.environ.get("BMS_DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(BASE, "bms_state.json")
HOST = os.environ.get("MQTT_HOST", "127.0.0.1")
PORT = int(os.environ.get("MQTT_PORT", "1884"))
PREFIX = os.environ.get("MQTT_PREFIX", "bms")
DISC = os.environ.get("MQTT_DISCOVERY", "homeassistant")
DEVICE_NAME = os.environ.get("BMS_NAME", "BMS 8S 24V")
DEVICE_ID = os.environ.get("BMS_ID", "bms8s")

try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
except AttributeError:
    client = mqtt.Client()
client.connect(HOST, PORT, 60)
client.loop_start()

DEVICE = {
    "identifiers": [DEVICE_ID],
    "name": DEVICE_NAME,
    "manufacturer": "Daly",
    "model": "8S 24V 120A",
}

SENSORS = {
    "soc": ("SOC", "%", "battery", 1),
    "voltage": ("Tensão", "V", "voltage", 1),
    "current": ("Corrente", "A", "current", 2),
    "power": ("Potência", "W", "power", 1),
    "cell_max": ("Célula máx", "mV", None, 0),
    "cell_min": ("Célula mín", "mV", None, 0),
    "temp": ("Temperatura", "°C", "temperature", 1),
}


def publish_discovery():
    for key, (name, unit, dev_class, prec) in SENSORS.items():
        cfg = {
            "name": name,
            "unique_id": f"{DEVICE_ID}_{key}",
            "state_topic": f"{PREFIX}/state",
            "value_template": "{{ value_json.%s }}" % key,
            "unit_of_measurement": unit,
            "device": DEVICE,
            "suggested_display_precision": prec,
        }
        if dev_class:
            cfg["device_class"] = dev_class
        client.publish(f"{DISC}/sensor/{DEVICE_ID}_{key}/config", json.dumps(cfg), retain=True)

    for i in range(1, 9):
        cfg = {
            "name": f"Célula {i}",
            "unique_id": f"{DEVICE_ID}_cell_{i}",
            "state_topic": f"{PREFIX}/state",
            "value_template": "{{ value_json.cells[%d] }}" % (i - 1),
            "unit_of_measurement": "mV",
            "device": DEVICE,
        }
        client.publish(f"{DISC}/sensor/{DEVICE_ID}_cell_{i}/config", json.dumps(cfg), retain=True)

    for key, name in (("Charging_Mos", "MOS carga"), ("Discharge_Mos", "MOS descarga")):
        cfg = {
            "name": name,
            "unique_id": f"{DEVICE_ID}_{key.lower()}",
            "state_topic": f"{PREFIX}/state",
            "value_template": "{{ 'ON' if value_json.%s | int(9) == 1 else ('OFF' if value_json.%s | int(9) == 0 else 'unknown') }}" % (key, key),
            "device": DEVICE,
            "device_class": "running",
        }
        client.publish(f"{DISC}/binary_sensor/{DEVICE_ID}_{key.lower()}/config", json.dumps(cfg), retain=True)


publish_discovery()
print(f"[mqtt] publicando em {HOST}:{PORT} -> {PREFIX}/state", flush=True)

last = None
last_good = {}
while True:
    try:
        with open(STATE) as f:
            st = json.load(f)
        last_good.update(st)
        st = last_good
        if "voltage" not in st or "soc" not in st or "cells" not in st:
            time.sleep(5)
            continue
        st["temp"] = (st.get("temps") or [None])[0]
        payload = json.dumps(st, ensure_ascii=False)
        if payload != last:
            client.publish(f"{PREFIX}/state", payload, retain=True)
            last = payload
            print("[mqtt]", payload, flush=True)
    except FileNotFoundError:
        pass
    except Exception as exc:
        print("[mqtt] erro:", exc, flush=True)
    time.sleep(5)
