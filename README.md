# BMS → Home Assistant (local)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**English** | [Português](README.pt-BR.md)

Read a LiFePO4 BMS through the vendor's Wi‑Fi/BT dongle **without relying on the
Tuya cloud API**, publish the data over **MQTT**, and integrate it with
**Home Assistant**. Optionally keep the vendor cloud working through a
transparent proxy and control Tuya devices on the LAN with **LocalTuya**.

> Intended for your **own** dongle/BMS. The proxy is a local MITM; use at your
> own risk.

## Architecture

```
BMS ──UART──► dongle ──TLS/MQTT──► local proxy ──TLS──► vendor cloud (Aliyun)
                                      │
                                      └── decodes Modbus ──► bms_state.json
                                                                    │
                                                          bms_mqtt.py
                                                                    │
                                                            Mosquitto (MQTT)
                                                                    │
                                                          Home Assistant
                                                                    │
                                                            LocalTuya (LAN)
```

## Files

| Path | Purpose |
|---|---|
| `src/bms_proxy.py` | TLS/MQTT proxy + Modbus polling (injects `WIFI_AP_BSSID`) |
| `src/bms_codec.py` | decodes the Modbus blocks (`WIFI_Band`) |
| `src/bms_mqtt.py` | publishes to MQTT and registers HA entities (discovery) |
| `src/arp_spoof.py` | one-way ARP spoof for the dongle |
| `scripts/bms-service.sh` | permanent service (ARP + DNAT + proxy) |
| `scripts/bms_tap.sh` | manual test wrapper |
| `deploy/*.service` | systemd units (adjust path/user) |
| `docker-compose.yml` | Home Assistant + Mosquitto |
| `mosquitto/config/mosquitto.conf` | broker (anonymous for testing) |
| `ha-config/configuration.yaml` | `default_config:` (MQTT is configured via UI) |
| `.env.example` | all settings (copy to `.env`) |
| `docs/HOMELAB.md` | homelab deployment guide (Portuguese) |

## Requirements

- Linux with `python3`, `python3-venv`, `openssl`, `iptables`, Docker + Compose.
- The dongle on the **same L2/VLAN** as this machine, with a DHCP reservation.
- Home Assistant and Mosquitto (via compose).

## 1. Configuration

```bash
cp .env.example .env
$EDITOR .env
```

Fill in at least:

- `BMS_DONGLE_IP`, `BMS_DONGLE_MAC` (from the router's DHCP list; the MAC often
  matches the dongle serial)
- `BMS_HOST_IP` (this machine's IP) — or leave empty for auto-detection
- `BMS_PRODUCT_KEY`, `BMS_DEVICE_NAME` — shown in the dongle's `CONNECT`
  (run the proxy once and read the log; see below)

### Discovering ProductKey / DeviceName

Run the manual tap for a few seconds and watch the log:

```bash
sudo bash scripts/bms_tap.sh 60
```

The `CONNECT` packet contains a ClientID like:

```
<ProductKey>.<DeviceName>|securemode=...
```

Example: `a1abc...xyz.FhGyi...|...` → ProductKey `a1abc...xyz`,
DeviceName `FhGyi...`.

Python dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. Home Assistant + Mosquitto

```bash
docker compose up -d
```

- HA: `http://<BMS_HOST_IP>:8123` (create the account on first access)
- Mosquitto: host `1884` → broker `1883`

In HA: **Settings → Devices & Services → Add Integration → MQTT**
- Broker: `mosquitto`
- Port: `1883`
- No username/password (test setup; enable auth in
  `mosquitto/config/mosquitto.conf` for production)

## 3. Run the tap and the publisher

Manual test:

```bash
sudo bash scripts/bms_tap.sh 120      # intercepts the dongle
.venv/bin/python src/bms_mqtt.py      # publishes to MQTT
```

Permanent (systemd):

```bash
# adjust /opt/bms and User=bms in deploy/ to your install path/user
sudo cp deploy/bms-tap.service deploy/bms-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bms-tap bms-mqtt
```

The entities show up automatically in HA: SOC, voltage, current, power,
cell max/min, cells 1–8, temperature and MOS.

## 4. LocalTuya (optional)

To control real Tuya devices **on the LAN** (no cloud), install
[LocalTuya](https://github.com/rospogrigio/localtuya) into
`ha-config/custom_components/localtuya` and add each device with:
IP, Device ID, Local Key and protocol version (3.3/3.4/3.5).

## Homelab deployment

Step-by-step (network, HA migration, cutover, validation) in
[`docs/HOMELAB.md`](docs/HOMELAB.md) (Portuguese).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `BMS_IFACE` | auto | LAN interface |
| `BMS_HOST_IP` | auto | this machine's IP |
| `BMS_DONGLE_IP` | — | dongle IP |
| `BMS_DONGLE_MAC` | — | dongle MAC |
| `BMS_GATEWAY_IP` | auto | gateway |
| `BMS_GATEWAY_MAC` | auto | gateway MAC |
| `BMS_REAL_HOST` | `public.iot-as-mqtt.us-east-1.aliyuncs.com` | vendor endpoint |
| `BMS_REAL_PORT` | `1883` | MQTT/TLS port |
| `BMS_PRODUCT_KEY` | — | dongle ProductKey |
| `BMS_DEVICE_NAME` | — | dongle DeviceName |
| `BMS_POLL_INTERVAL` | `30` | polling interval (s) |
| `BMS_POLL_CMD_DATA` | `D2030000007ED649` | Modbus read (data) |
| `BMS_POLL_CMD_TEMP` | `D203008000705665` | Modbus read (temperatures) |
| `MQTT_HOST` / `MQTT_PORT` | `127.0.0.1` / `1884` | broker |
| `MQTT_PREFIX` | `bms` | state topic |
| `MQTT_DISCOVERY` | `homeassistant` | discovery prefix |
| `BMS_NAME` / `BMS_ID` | `BMS 8S 24V` / `bms8s` | HA device name/ID |

## AI assistant instructions

- `AGENTS.md` — source of truth (OpenCode/Codex; Portuguese)
- `CLAUDE.md` — Claude Code
- `.github/copilot-instructions.md` — GitHub Copilot

## Security

- `.env`, `tuya.json`, certificates, state, logs and `ha-config/` are
  `.gitignore`d.
- Run the tap as root only on your own network.
- For production, enable Mosquitto authentication and do not expose HA to the
  internet without a VPN.

## License

MIT — see [LICENSE](LICENSE).

## Troubleshooting

- **Dongle does not connect**: check IP/MAC, DHCP reservation, and that the ARP
  spoof is running (`systemctl status bms-tap`).
- **`clientId is invalid` / `permission deny`**: those are Tuya cloud API errors;
  this project does not use that API.
- **No data in HA**: check `bms_state.json`, `bms_tap.log` and
  `journalctl -u bms-tap -f`.
