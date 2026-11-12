# BMS → Home Assistant (local)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Português** | [English](README.md)

Lê um BMS LiFePO4 via dongle Wi‑Fi/BT (Daly/Modbus) **sem depender da nuvem do
fabricante para a automação**, publica os dados no **MQTT** e integra no
**Home Assistant**. Opcionalmente faz um *proxy transparente* para a nuvem do
fabricante continuar funcionando e usa **LocalTuya** para controlar dispositivos
Tuya na LAN.

> Uso pretendido: o **seu próprio** dongle/BMS. O proxy é um MITM local; use por
> sua conta e risco.

## Arquitetura

```
BMS ──UART──► dongle ──TLS/MQTT──► proxy local ──TLS──► nuvem do fabricante
                                      │
                                      └── decodifica Modbus ──► bms_state.json
                                                                    │
                                                          bms_mqtt.py
                                                                    │
                                                            Mosquitto (MQTT)
                                                                    │
                                                          Home Assistant
                                                                    │
                                                            LocalTuya (LAN)
```

## Arquivos

| Arquivo | Função |
|---|---|
| `src/bms_proxy.py` | proxy TLS/MQTT + polling Modbus (injeta `WIFI_AP_BSSID`) |
| `src/bms_codec.py` | decodifica os blocos Modbus (`WIFI_Band`) |
| `src/bms_mqtt.py` | publica no MQTT e registra as entidades no HA |
| `src/arp_spoof.py` | ARP spoof unidirecional do dongle |
| `scripts/bms-service.sh` | serviço permanente (ARP + DNAT + proxy) |
| `scripts/bms_tap.sh` | versão manual para testes |
| `docker-compose.yml` | Home Assistant + Mosquitto |
| `deploy/*.service` | units systemd (ajuste caminho/usuário) |
| `.env.example` | todas as configurações |

## Requisitos

- Linux com `python3`, `openssl`, `iptables`, Docker + Compose.
- Dongle na mesma LAN, com **IP fixo/reserva DHCP**.
- Home Assistant e Mosquitto (via compose).

## 1. Configuração

```bash
cp .env.example .env
$EDITOR .env
```

Preencha no mínimo:

- `BMS_DONGLE_IP`, `BMS_DONGLE_MAC` (veja no DHCP do roteador; o MAC costuma
  bater com o serial do dongle)
- `BMS_HOST_IP` (IP desta máquina) — ou deixe vazio para auto-detectar
- `BMS_PRODUCT_KEY`, `BMS_DEVICE_NAME` — aparecem no `CONNECT` do dongle
  (rode o proxy uma vez e veja o log; veja abaixo)

### Como descobrir ProductKey/DeviceName

Rode o tap manual por alguns segundos e observe o log:

```bash
sudo bash scripts/bms_tap.sh 60
```

No `CONNECT` aparece o ClientID:

```
<ProductKey>.<DeviceName>|securemode=...
```

Exemplo: `a1abc...xyz.FhGyi...|...` → ProductKey `a1abc...xyz`,
DeviceName `FhGyi...`.

Dependências Python:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. Home Assistant + Mosquitto

```bash
docker compose up -d
```

- HA: `http://<BMS_HOST_IP>:8123` (crie a conta no primeiro acesso)
- Mosquitto: host `1884` → broker `1883`

No HA: **Settings → Devices & Services → Add Integration → MQTT**
- Broker: `mosquitto`
- Port: `1883`
- Sem usuário/senha (config de teste; para produção configure auth no
  `mosquitto/config/mosquitto.conf`)

## 3. Rodar o tap e o publicador

Teste manual:

```bash
sudo bash scripts/bms_tap.sh 120      # intercepta o dongle
.venv/bin/python src/bms_mqtt.py      # publica no MQTT
```

Permanente (systemd):

```bash
# ajuste /opt/bms e User=bms nos units de deploy/ para o caminho/usuário da sua instalação
sudo cp deploy/bms-tap.service deploy/bms-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bms-tap bms-mqtt
```

> Os units em `deploy/` usam `/opt/bms` e `User=bms` como exemplo; troque pelo caminho
> onde você clonou o projeto e pelo usuário que roda o publicador.

As entidades aparecem sozinhas no HA: SOC, tensão, corrente, potência,
célula máx/mín, células 1–8, temperatura e MOS.

## 4. LocalTuya (opcional)

Para controlar dispositivos Tuya reais **na LAN** (sem nuvem), instale o
[LocalTuya](https://github.com/rospogrigio/localtuya) em
`ha-config/custom_components/localtuya` e adicione cada dispositivo com:
IP, Device ID, Local Key e versão do protocolo (3.3/3.4/3.5).

## Deploy no homelab

Passo a passo (rede, migração do HA, cutover, validação) em
**[`docs/HOMELAB.md`](docs/HOMELAB.md)**.

## Portainer

Duas opções em **[`docs/PORTAINER.md`](docs/PORTAINER.md)**:

- build pelo Git: `docker-compose.portainer.yml`
- imagem do GHCR: `docker-compose.portainer-image.yml`
  (`ghcr.io/cesarzxk/smart-bms-local:latest`, gerada pelo GitHub Actions).

## Variáveis de ambiente

| Variável | Padrão | Descrição |
|---|---|---|
| `BMS_IFACE` | auto | interface da LAN |
| `BMS_HOST_IP` | auto | IP desta máquina |
| `BMS_DONGLE_IP` | — | IP do dongle |
| `BMS_DONGLE_MAC` | — | MAC do dongle |
| `BMS_GATEWAY_IP` | auto | gateway |
| `BMS_GATEWAY_MAC` | auto | MAC do gateway |
| `BMS_REAL_HOST` | `public.iot-as-mqtt.us-east-1.aliyuncs.com` | endpoint do fabricante |
| `BMS_REAL_PORT` | `1883` | porta MQTT/TLS |
| `BMS_PRODUCT_KEY` | — | ProductKey do dongle |
| `BMS_DEVICE_NAME` | — | DeviceName do dongle |
| `BMS_POLL_INTERVAL` | `30` | intervalo do polling (s) |
| `BMS_POLL_CMD_DATA` | `D2030000007ED649` | leitura Modbus dos dados |
| `BMS_POLL_CMD_TEMP` | `D203008000705665` | leitura Modbus das temperaturas |
| `MQTT_HOST` / `MQTT_PORT` | `127.0.0.1` / `1884` | broker |
| `MQTT_PREFIX` | `bms` | tópico de estado |
| `MQTT_DISCOVERY` | `homeassistant` | prefixo de discovery |
| `BMS_NAME` / `BMS_ID` | `BMS 8S 24V` / `bms8s` | nome/ID no HA |

## Instruções para assistentes de IA

- `AGENTS.md` — fonte da verdade, **em inglês** (OpenCode/Codex, e base para os demais)
- `CLAUDE.md` — Claude Code
- `.github/copilot-instructions.md` — GitHub Copilot

## Segurança

- `.env`, `tuya.json`, certificados, estado, logs e `ha-config/` ficam no
  `.gitignore`.
- Rode o tap como root apenas na sua rede.
- Para produção, ative autenticação no Mosquitto e não exponha o HA na internet
  sem VPN.

## Licença

MIT — veja [LICENSE](LICENSE).

## Troubleshooting

- **Dongle não conecta**: confira IP/MAC, reserva DHCP, e se o ARP spoof está
  ativo (`systemctl status bms-tap`).
- **`clientId is invalid`/`permission deny`**: são da API do Tuya, não deste
  projeto; aqui não usamos a API do Tuya.
- **Sem dados no HA**: veja `bms_state.json`, `bms_tap.log` e
  `journalctl -u bms-tap -f`.
