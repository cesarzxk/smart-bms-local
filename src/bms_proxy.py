#!/usr/bin/env python3
"""Proxy MQTT/TLS transparente: dongle <-> Aliyun real, com tap e polling local."""
import json
import os
import socket
import ssl
import sys
import threading
import time

import bms_codec as codec

BASE = os.environ.get("BMS_DATA_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CERT = os.environ.get("BMS_CERT", os.path.join(BASE, "cert.pem"))
KEY = os.environ.get("BMS_KEY", os.path.join(BASE, "key.pem"))
REAL_HOST = os.environ.get("BMS_REAL_HOST", "public.iot-as-mqtt.us-east-1.aliyuncs.com")
REAL_PORT = int(os.environ.get("BMS_REAL_PORT", "1883"))
PK = os.environ.get("BMS_PRODUCT_KEY", "")
DN = os.environ.get("BMS_DEVICE_NAME", "")
POLL_INTERVAL = max(5, int(os.environ.get("BMS_POLL_INTERVAL", "30")))
POLL_CMDS = [
    (os.environ.get("BMS_POLL_CMD_DATA", "D2030000007ED649"), "dados"),
    (os.environ.get("BMS_POLL_CMD_TEMP", "D203008000705665"), "temps"),
]

server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
server_ctx.load_cert_chain(CERT, KEY)
server_ctx.set_ciphers("DEFAULT@SECLEVEL=0")
client_ctx = ssl.create_default_context()


def read_exact(s, n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c:
            raise ConnectionError("fechou")
        b += c
    return b


def read_varint(s):
    m, v = 1, 0
    while True:
        b = read_exact(s, 1)[0]
        v += (b & 0x7F) * m
        if not b & 0x80:
            return v
        m *= 128


def enc_varint(n):
    o = b""
    while True:
        d = n % 128
        n //= 128
        o += bytes([d | (0x80 if n else 0)])
        if not n:
            return o


def pstr(d, i):
    n = int.from_bytes(d[i:i + 2], "big")
    return d[i + 2:i + 2 + n], i + 2 + n


def inject(tls, stop, lock):
    """Pede os dados ao dongle replicando o comando de polling da nuvem."""
    if not PK or not DN:
        codec.log("[inject] BMS_PRODUCT_KEY/BMS_DEVICE_NAME nao definidos; polling desativado")
        return
    time.sleep(8)
    n = 0
    while not stop.is_set():
        n += 1
        for cmd, label in POLL_CMDS:
            payload = json.dumps({
                "method": "thing.service.property.set",
                "id": str(100000 + n),
                "params": {"WIFI_AP_BSSID": cmd},
                "version": "1.0.0",
            }).encode()
            topic = f"/sys/{PK}/{DN}/thing/service/property/set".encode()
            body = len(topic).to_bytes(2, "big") + topic + payload
            pkt = bytes([0x30]) + enc_varint(len(body)) + body
            try:
                with lock:
                    tls.sendall(pkt)
                codec.log(f"[inject] #{n} {label} {cmd}")
            except Exception:
                return
            time.sleep(1)
        time.sleep(max(1, POLL_INTERVAL - len(POLL_CMDS)))


def pump_up(tls, up, stop, lock):
    try:
        while not stop.is_set():
            first = read_exact(up, 1)[0]
            body = read_exact(up, read_varint(up))
            with lock:
                tls.sendall(bytes([first]) + enc_varint(len(body)) + body)

            t = first >> 4
            if t == 2:
                codec.log(f"[aliyun] CONNACK session={body[0] & 1} rc={body[1]}")
            elif t == 3:
                qos = (first >> 1) & 3
                i = 0
                topic, i = pstr(body, i)
                if qos:
                    i += 2
                payload = body[i:]
                top = topic.decode(errors="replace")
                if not top.endswith("/thing/lan/prefix/get_reply"):
                    codec.log(f"[aliyun->dongle] PUBLISH {top} ({len(payload)}b) {payload[:400]!r}")
            elif t == 9:
                codec.log("[aliyun] SUBACK")
    except Exception as exc:
        codec.log(f"[aliyun->dongle] {exc!r}")
    finally:
        stop.set()


def handle(conn, addr):
    stop = threading.Event()
    try:
        tls = server_ctx.wrap_socket(conn, server_side=True)
    except Exception as exc:
        codec.log(f"[{addr[1]}] handshake local falhou {exc!r}")
        return
    try:
        raw = socket.create_connection((REAL_HOST, REAL_PORT), timeout=10)
        up = client_ctx.wrap_socket(raw, server_hostname=REAL_HOST)
        up.settimeout(None)
    except Exception as exc:
        codec.log(f"[{addr[1]}] conexao {REAL_HOST} falhou {exc!r}")
        tls.close()
        return
    codec.log(f"[{addr[1]}] tunel aberto para {REAL_HOST}")
    lock = threading.Lock()
    threading.Thread(target=pump_up, args=(tls, up, stop, lock), daemon=True).start()
    if os.environ.get("INJECT", "1") == "1":
        threading.Thread(target=inject, args=(tls, stop, lock), daemon=True).start()

    try:
        while not stop.is_set():
            first = read_exact(tls, 1)[0]
            t, f = first >> 4, first & 0x0F
            body = read_exact(tls, read_varint(tls))
            up.sendall(bytes([first]) + enc_varint(len(body)) + body)

            if t == 1:
                i = 0
                _, i = pstr(body, i)
                level = body[i]; i += 1
                cflags = body[i]; i += 1
                ka = int.from_bytes(body[i:i + 2], "big"); i += 2
                if level == 5:
                    i += body[i] + 1
                cid, i = pstr(body, i)
                codec.log(f"[{addr[1]}] CONNECT clean={bool(cflags & 2)} keepalive={ka} cid={cid.decode(errors='replace')}")
            elif t == 3:
                qos = (f >> 1) & 3
                i = 0
                topic, i = pstr(body, i)
                if qos:
                    i += 2
                payload = body[i:]
                top = topic.decode(errors="replace")
                if not top.endswith("/thing/lan/prefix/get"):
                    codec.log(f"[{addr[1]}] PUBLISH {top} ({len(payload)}b)")
                if top.endswith("/thing/event/property/post") or top.endswith("/thing/event/property/batch/post"):
                    try:
                        obj = json.loads(payload)
                        p = obj.get("params")
                        if isinstance(p, dict):
                            if isinstance(p.get("properties"), list):
                                for item in p["properties"]:
                                    if isinstance(item.get("value"), dict):
                                        codec.update(item["value"])
                            else:
                                codec.update(p)
                        codec.tuya_push()
                    except Exception as exc:
                        codec.log(f"[{addr[1]}] payload invalido {exc!r}")
            elif t == 8:
                i = 2
                topics = []
                while i < len(body):
                    tt, i = pstr(body, i)
                    topics.append(tt.decode(errors="replace")); i += 1
                codec.log(f"[{addr[1]}] SUBSCRIBE {topics}")
    except Exception as exc:
        codec.log(f"[{addr[1]}] fim {exc!r}")
    finally:
        stop.set()
        for s in (tls, up):
            try:
                s.close()
            except Exception:
                pass


codec.tuya_init()
srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", 1883))
srv.listen(10)
srv.settimeout(1)
codec.log("[proxy] ouvindo TLS 1883 ->", REAL_HOST)
while True:
    try:
        c, a = srv.accept()
    except socket.timeout:
        continue
    threading.Thread(target=handle, args=(c, a), daemon=True).start()
