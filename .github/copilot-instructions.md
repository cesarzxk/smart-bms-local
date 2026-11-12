# Copilot instructions — BMS local bridge

Read `AGENTS.md` at the repository root: it is the source of truth
(architecture, protocol, pitfalls and step-by-step). This file summarizes the
essentials for Copilot.

## What this is

LiFePO4 8S BMS → vendor Wi‑Fi/BT dongle (Bouffalo BL606) → **local TLS/MQTT
proxy** → **Mosquitto** → **Home Assistant**. The proxy also forwards traffic to
the vendor cloud (Aliyun) and injects Modbus polling.

## Structure

- `src/bms_proxy.py` — TLS/MQTT proxy + polling injection
- `src/bms_codec.py` — decodes Modbus (`WIFI_Band`) and writes `bms_state.json`
- `src/bms_mqtt.py` — publishes `bms/state` and does HA discovery
- `src/arp_spoof.py` — one-way ARP spoof for the dongle
- `scripts/bms-service.sh` / `scripts/bms_tap.sh` — service / manual test
- `deploy/*.service` — systemd
- `docker-compose.yml` — Home Assistant + Mosquitto
- `.env.example` — all settings

## Conventions

- **Everything via `.env`**: never hardcode IPs, MACs, ProductKey, DeviceName or
  keys.
- **Never commit secrets**: `.env`, `cert.pem`, `key.pem`, `tuya.json`,
  `bms_state.json`, `bms_tap.log`, `*.pcap`, `ha-config/.storage`.
- Comments/docs: English is preferred for code; README has EN and pt-BR.
- Small, testable changes; respect the `src/` / `scripts/` / `deploy/` split.
- Do not reopen the **Tuya cloud API** (product model/data center issues).
  For Smart Life: Matter (hub) or a Tuya DC meter.

## Useful commands

```bash
python3 -m py_compile src/*.py
bash -n scripts/*.sh
sudo bash scripts/bms_tap.sh 60          # manual test
systemctl status bms-tap bms-mqtt
journalctl -u bms-tap -f
mosquitto_sub -t bms/state -v
```

## Pitfalls

- Use **one-way** ARP spoof (two-way breaks the dongle's DNS).
- Keep the tunnel socket **blocking** (`settimeout(None)`), otherwise it drops
  every 10 s.
- Docker leaves `FORWARD` as `DROP`: allow the dongle IP.
- `regs[i]` is a register index (2 bytes), not a byte offset.
- Current HA does not accept `mqtt:` in YAML; configure it via the UI.
