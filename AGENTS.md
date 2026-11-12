# AGENTS.md — guide for AI assistants (Claude, Copilot, OpenCode, etc.)

This file is the **source of truth** for any agent working on this project.
Read it fully before changing code, running `sudo`, or touching the network.

## 1. Project goal

Read a **LiFePO4 8S BMS** through the vendor's Wi‑Fi/BT dongle, **without
depending on the Tuya cloud API**, and deliver the data to **Home Assistant**
over **MQTT**, with local automation (including controlling Tuya devices on the
LAN with **LocalTuya**).

The dongle speaks MQTT/TLS with the vendor cloud (Aliyun). This project runs a
**transparent local proxy** (MITM) that:

1. intercepts the dongle (ARP spoof + DNAT),
2. terminates TLS (the dongle **does not validate** the certificate),
3. forwards traffic to the real cloud (so the vendor app keeps working),
4. **injects Modbus requests** over MQTT to poll data on demand,
5. decodes the responses and publishes them to Mosquitto → Home Assistant.

## 2. Architecture

```
BMS ──UART──► dongle ──TLS/MQTT:1883──► proxy (src/bms_proxy.py) ──TLS──► Aliyun
                                          │
                                          ├─ injects Modbus (property/set WIFI_AP_BSSID)
                                          ├─ decodes WIFI_Band (src/bms_codec.py)
                                          └─ bms_state.json
                                                    │
                                          src/bms_mqtt.py
                                                    │
                                            Mosquitto :1884
                                                    │
                                            Home Assistant
                                                    │
                                            LocalTuya (LAN)
```

## 3. Layout

| Path | Purpose |
|---|---|
| `src/bms_proxy.py` | TLS/MQTT proxy + Modbus polling injection |
| `src/bms_codec.py` | decodes the Modbus blocks (`WIFI_Band`) and writes `bms_state.json` |
| `src/bms_mqtt.py` | publishes `bms/state` and registers HA entities (discovery) |
| `src/arp_spoof.py` | one-way ARP spoof for the dongle |
| `scripts/bms-service.sh` | permanent service: ARP + DNAT + proxy |
| `scripts/bms_tap.sh` | manual test wrapper (N seconds) |
| `deploy/*.service` | systemd units (adjust path/user) |
| `docker-compose.yml` | Home Assistant + Mosquitto |
| `mosquitto/config/mosquitto.conf` | broker (anonymous for testing) |
| `ha-config/configuration.yaml` | `default_config:` (MQTT is configured via UI) |
| `.env.example` | ALL settings (copy to `.env`) |
| `README.md` | user setup (English) / `README.pt-BR.md` (Portuguese) |

## 4. Golden rules (do not break)

1. **Never commit secrets.** `.env`, `cert.pem`, `key.pem`, `tuya.json`,
   `bms_state.json`, `bms_tap.log`, `*.pcap`, `ha-config/.storage` and
   `mosquitto/data` are in `.gitignore`. Do not remove those entries.
2. **Never try the Tuya cloud API again.** That path was abandoned: the product
   model (TuyaLink/TuyaOS) was never published and the data center answered
   `28841107 — data center is suspended`. The app shows the development draft,
   but the API sees an empty production model (`functions: []`,
   `command or value not support`). **Do not waste time on it.** If Smart Life
   integration is required, use **Matter** (with a hub) or a **Tuya DC energy
   meter with a shunt**.
3. **Everything is configurable via `.env`.** Do not hardcode IPs, MACs,
   ProductKey, DeviceName or keys. Use `os.environ.get(...)` with safe defaults.
4. **Ask for confirmation before**: `sudo`, ARP spoof, `iptables`, `sysctl`,
   restarting services, editing `.env` or changing the network. Explain the
   effect.
5. **Keep changes small and consistent.** Respect `src/` / `scripts/` /
   `deploy/`. Do not rewrite what already works.
6. **Always validate** with `systemctl status`, `journalctl -u bms-tap -f`,
   `mosquitto_sub -t bms/state` and the HA entities.
7. **Security/legal**: the MITM is for the **user's own dongle**. Do not help
   intercept third parties or expose HA/MQTT to the internet without a VPN.

## 5. Protocol cheat sheet (what was discovered)

- Dongle: Bouffalo **BL606**; the **MAC** is usually encoded in the serial
  (`DL-F` + MAC without colons). A DHCP reservation is required.
- Endpoint: `public.iot-as-mqtt.us-east-1.aliyuncs.com:1883` over **TLS**.
- The dongle **does not validate** the server certificate → a local self-signed
  cert works. The CONNECT is MQTT 3.1.1, `clean=False`, keepalive 120.
- ClientID: `<ProductKey>.<DeviceName>|securemode=2,...`; username
  `<DeviceName>&<ProductKey>`; the password is an HMAC (not the DeviceSecret).
- **Polling**: publish to
  `/sys/<PK>/<DN>/thing/service/property/set` with
  `{"method":"thing.service.property.set","id":"...","params":{"WIFI_AP_BSSID":"<CMD>"},"version":"1.0.0"}`
  where `<CMD>` is a **raw Modbus RTU request in hex**:
  - data: `D2030000007ED649` (126 registers starting at 0x0000)
  - temperatures/info: `D203008000705665` (112 registers starting at 0x0080)
- **Response**: `thing/event/property/post` with `params.WIFI_Band` = Modbus
  response in hex (`D2 03 <count> <data> <crc16 little-endian>`).
- Register map (block 0x0000, verified):
  - `regs[0..7]` = cell voltages (mV)
  - `regs[0x28] / 10` = pack voltage (V)
  - `(regs[0x29] - 30000) / 10` = current (A)
  - `regs[0x2A] / 10` = SOC (%)
  - `regs[0x2B]` / `regs[0x2C]` = max/min cell (mV)
  - temperatures in block 0x0080: `regs[0x0A..0x0E] / 100` (°C)
- **Mind the offsets**: `regs[i]` is a **register index** (2 bytes), not a byte
  offset. This confusion already produced 64.7 V and -2993 A.
- The dongle only sends the big blocks when the cloud asks for them
  (property/set). Without polling, only the MOS DPs show up.

## 6. Known pitfalls (do not repeat)

| Symptom | Cause | Fix |
|---|---|---|
| Dongle loops on DNS (`iot-auth-global`) | **two-way** ARP spoof breaks DNS | Use **one-way** spoof (`arp_spoof.py ... oneway`) |
| Tunnel drops every ~10 s | outbound socket with timeout=10 | `up.settimeout(None)` (blocking) |
| Dongle authenticates (`rc=0`) but gets no data | Docker leaves `FORWARD` as `DROP` | `iptables -I FORWARD -s/-d <dongle> -j ACCEPT` (the script does this) |
| HA rejects `mqtt:` in YAML | MQTT integration moved to UI | remove it from YAML and add via *Add Integration → MQTT* |
| Port 1883 conflict | proxy and Mosquitto | Mosquitto on host **1884** (`1884:1883`) |
| `unavailable` entities / template warnings | publisher picked up a partial state | `bms_mqtt.py` only publishes with `voltage`/`soc`/`cells` and merges |
| Dongle IP changes | DHCP | DHCP reservation by MAC |

## 7. Reproducing from scratch

1. **Find the dongle**: reserve its IP on the router; note IP and MAC.
2. **Configure**: `cp .env.example .env` and set `BMS_DONGLE_IP`,
   `BMS_DONGLE_MAC`, `BMS_HOST_IP` (or leave empty for auto).
3. **Find ProductKey/DeviceName**: run
   `sudo bash scripts/bms_tap.sh 60` and read the `CONNECT` from the log or
   `journalctl`. Fill them in `.env`.
4. **Python**: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
5. **HA + MQTT**: `docker compose up -d`; open `http://<host>:8123`, create the
   account and add **MQTT** (broker `mosquitto`, port `1883`, no auth).
6. **Services**: adjust `deploy/*.service` (`/opt/bms`, `User=`) and
   `systemctl enable --now bms-tap bms-mqtt`.
7. **Validate**: `mosquitto_sub -t bms/state -v` and the HA entities.
8. **LocalTuya** (optional): install the custom component into
   `ha-config/custom_components/localtuya`, add IP/Device ID/Local Key and
   protocol 3.4; map DP 1 as switch/light.

## 8. How the agent should help

- Start by reading `README.md`, `AGENTS.md` and `.env.example`.
- Before coding, **describe the plan** and ask for approval if it involves
  network/root.
- Prefer small, testable edits in `src/` / `scripts/`.
- Use `rg`/`grep`, `systemctl`, `journalctl`, `mosquitto_sub` to diagnose.
- Never expose `.env` values in replies, commits or sample logs.
- If the user asks for “Smart Life/Tuya”, explain the **Matter** or
  **DC meter** route; do not reopen the Tuya cloud API.
- If something requires root/the password, **ask the user** to run the command;
  never ask for the password.
