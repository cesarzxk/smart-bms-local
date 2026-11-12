# CLAUDE.md

Antes de qualquer coisa, leia **[`AGENTS.md`](./AGENTS.md)** — ele é a fonte da
verdade (arquitetura, protocolo descoberto, armadilhas e passo a passo).

Resumo para o Claude Code:

- Projeto: BMS Daly 8S → dongle BL606 → proxy TLS/MQTT local → Mosquitto → Home
  Assistant. Configuração 100% em `.env` (nunca commitar segredos).
- Foco: `src/` (Python), `scripts/` (shell), `deploy/` (systemd),
  `docker-compose.yml` (HA + Mosquitto), `README.md` (setup).
- **Não** tente a API de nuvem do Tuya (modelo/data center suspenso). Para Smart
  Life, apenas Matter (hub) ou medidor DC Tuya.
- Antes de `sudo`, ARP spoof, `iptables`, reiniciar serviço ou editar `.env`,
  descreva o efeito e peça confirmação.
- Validação típica:
  - `systemctl status bms-tap bms-mqtt`
  - `journalctl -u bms-tap -f`
  - `mosquitto_sub -t bms/state -v`
  - entidades no Home Assistant
- Evite reescrever o que funciona; faça diffs pequenos e rode
  `python3 -m py_compile src/*.py` e `bash -n scripts/*.sh` quando possível.
