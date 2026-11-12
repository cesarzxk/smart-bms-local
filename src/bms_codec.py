#!/usr/bin/env python3
"""Decodificador Daly/Modbus + push Tuya opcional (ativado se existir tuya.json)."""
import json
import os
import time

BASE = os.environ.get("BMS_DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOG = os.path.join(BASE, "bms_tap.log")
STATE = os.path.join(BASE, "bms_state.json")
CONF = os.path.join(BASE, "tuya.json")

state = {}
TUYA = None
cloud = None
last_push = 0.0


def log(*a):
    line = " ".join(str(x) for x in a)
    print(line, flush=True)
    try:
        with open(LOG, "a") as f:
            f.write(time.strftime("%H:%M:%S ") + line + "\n")
    except OSError:
        pass


def crc16(data):
    c = 0xFFFF
    for b in data:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return c


def decode_wifi_band(hexstr):
    try:
        raw = bytes.fromhex(hexstr)
    except ValueError:
        return None
    if len(raw) < 5 or raw[0] != 0xD2 or raw[1] != 0x03:
        return None
    n = raw[2]
    body = raw[3:3 + n]
    if len(body) < n:
        return None
    regs = [int.from_bytes(body[i:i + 2], "big") for i in range(0, n - 1, 2)]
    return {"count": n, "regs": regs,
            "crc": crc16(raw[:-2]) == int.from_bytes(raw[-2:], "little")}


def update(params):
    for k, v in params.items():
        if k == "WIFI_Band" and isinstance(v, str):
            log(f"[wb] len={len(v)} {v}")
            blk = decode_wifi_band(v)
            if not blk:
                continue
            r = blk["regs"]
            if blk["count"] == 0xFC and len(r) >= 0x2D:
                state["cells"] = [x for x in r[0:8] if 500 < x < 5000]
                state["voltage"] = r[0x28] / 10.0
                state["current"] = (r[0x29] - 30000) / 10.0
                state["soc"] = r[0x2A] / 10.0
                state["cell_max"] = r[0x2B]
                state["cell_min"] = r[0x2C]
            elif blk["count"] == 0xE0 and len(r) > 0x0F:
                state["temps"] = [round(r[i] / 100.0, 2) for i in range(0x0A, 0x0F)]
        else:
            state[k] = v
    if "voltage" in state:
        state["power"] = round(state["voltage"] * state.get("current", 0), 1)
    try:
        with open(STATE, "w") as f:
            json.dump(state, f, indent=1)
    except OSError:
        pass
    log("[state]", json.dumps(state, ensure_ascii=False))


def tuya_init():
    global TUYA, cloud
    if not os.path.exists(CONF):
        return
    try:
        import tinytuya
        cfg = json.load(open(CONF))
        TUYA = cfg
        cloud = tinytuya.Cloud(
            apiRegion=cfg.get("region", "eu"),
            apiKey=cfg["apiKey"],
            apiSecret=cfg["apiSecret"],
            apiDeviceID=cfg.get("deviceId", ""),
        )
        log("[tuya] config carregada")
    except Exception as exc:
        log("[tuya] init falhou:", repr(exc))


def tuya_push(force=False):
    global last_push
    if not TUYA or not cloud:
        return
    now = time.time()
    if not force and now - last_push < 15:
        return
    d = TUYA.get("dps", {})
    mapping = {
        "soc": state.get("soc"),
        "voltage": state.get("voltage"),
        "current": state.get("current"),
        "power": state.get("power"),
        "cell_max": state.get("cell_max"),
        "cell_min": state.get("cell_min"),
        "temp": (state.get("temps") or [None])[0],
    }
    scales = {"soc": 1, "voltage": 1, "current": 1, "power": 1,
              "cell_max": 0, "cell_min": 0, "temp": 2}
    dps = {}
    for k, dp in d.items():
        if mapping.get(k) is None:
            continue
        dps[str(dp)] = int(round(float(mapping[k]) * (10 ** scales.get(k, 0))))
    if not dps:
        return
    try:
        cloud.sendcommand(TUYA["deviceId"], dps)
        log("[tuya] push", dps)
        last_push = now
    except Exception as exc:
        log("[tuya] push falhou:", repr(exc))
