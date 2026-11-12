# Copilot instructions — BMS local bridge

Leia `AGENTS.md` na raiz: é a fonte da verdade (arquitetura, protocolo,
armadilhas e passo a passo). Este arquivo resume o essencial para o Copilot.

## O que é

BMS LiFePO4 8S → dongle Wi‑Fi/BT (Bouffalo BL606) → **proxy TLS/MQTT local** →
**Mosquitto** → **Home Assistant**. O proxy também repassa o tráfego para a
nuvem do fabricante (Aliyun) e injeta polling Modbus.

## Estrutura

- `src/bms_proxy.py` — proxy TLS/MQTT + injeção do polling
- `src/bms_codec.py` — decodifica Modbus (`WIFI_Band`) e grava `bms_state.json`
- `src/bms_mqtt.py` — publica em `bms/state` e faz discovery no HA
- `src/arp_spoof.py` — ARP spoof unidirecional do dongle
- `scripts/bms-service.sh` / `scripts/bms_tap.sh` — serviço / teste manual
- `deploy/*.service` — systemd
- `docker-compose.yml` — Home Assistant + Mosquitto
- `.env.example` — todas as configurações

## Convenções

- **Tudo via `.env`**: nunca hardcode IP, MAC, ProductKey, DeviceName ou chaves.
- **Nunca commitar segredos**: `.env`, `cert.pem`, `key.pem`, `tuya.json`,
  `bms_state.json`, `bms_tap.log`, `*.pcap`, `ha-config/.storage`.
- Comentários/docs em português; identificadores de código em inglês.
- Mudanças pequenas e testáveis; respeite a divisão `src/` / `scripts/` / `deploy/`.
- Não reabra a **API de nuvem do Tuya** (modelo de produto/data center suspenso).
  Para Smart Life: Matter (hub) ou medidor DC Tuya.

## Comandos úteis

```bash
python3 -m py_compile src/*.py
bash -n scripts/*.sh
sudo bash scripts/bms_tap.sh 60          # teste manual
systemctl status bms-tap bms-mqtt
journalctl -u bms-tap -f
mosquitto_sub -t bms/state -v
```

## Armadilhas

- ARP spoof **unidirecional** (bidirecional quebra o DNS do dongle).
- Socket do túnel **sem timeout** (`settimeout(None)`); senão cai a cada 10 s.
- Docker deixa `FORWARD` em `DROP`: liberar o IP do dongle.
- `regs[i]` é índice de registrador (2 bytes), não offset de byte.
- HA atual não aceita `mqtt:` no YAML; configure pela UI.
