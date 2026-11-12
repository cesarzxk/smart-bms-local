# CLAUDE.md

Before anything else, read **[`AGENTS.md`](./AGENTS.md)** — it is the source of
truth (architecture, discovered protocol, pitfalls and step-by-step).

Claude Code summary:

- Project: Daly 8S BMS → BL606 dongle → local TLS/MQTT proxy → Mosquitto →
  Home Assistant. All configuration lives in `.env` (never commit secrets).
- Focus areas: `src/` (Python), `scripts/` (shell), `deploy/` (systemd),
  `docker-compose.yml` (HA + Mosquitto), `README.md` (setup).
- **Do not** retry the Tuya cloud API (product model/data center issues). For
  Smart Life, only Matter (hub) or a Tuya DC meter.
- Before `sudo`, ARP spoof, `iptables`, restarting services or editing `.env`,
  explain the effect and ask for confirmation.
- Typical validation:
  - `systemctl status bms-tap bms-mqtt`
  - `journalctl -u bms-tap -f`
  - `mosquitto_sub -t bms/state -v`
  - Home Assistant entities
- Avoid rewriting working code; keep diffs small and run
  `python3 -m py_compile src/*.py` and `bash -n scripts/*.sh` when possible.
