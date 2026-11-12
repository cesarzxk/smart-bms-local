# AGENTS.md — guia para assistentes de IA (Claude, Copilot, OpenCode, etc.)

Este arquivo é a **fonte da verdade** para qualquer agente que for mexer neste
projeto. Leia inteiro antes de alterar código, rodar comandos com `sudo` ou
mexer na rede.

## 1. Objetivo do projeto

Ler um **BMS LiFePO4 8S** através do dongle Wi‑Fi/BT do fabricante, **sem
depender da API de nuvem do Tuya**, e entregar os dados no **Home Assistant**
via **MQTT**, com automação local (inclusive controlando dispositivos Tuya pela
LAN com **LocalTuya**).

O dongle fala MQTT/TLS com a nuvem do fabricante (Aliyun). O projeto faz um
**proxy transparente local** (MITM) que:

1. intercepta o dongle (ARP spoof + DNAT),
2. termina o TLS (o dongle **não valida** o certificado),
3. repassa o tráfego para a nuvem real (para o app do fabricante continuar),
4. **injeta requisições Modbus** via MQTT para pedir os dados sob demanda,
5. decodifica as respostas e publica no Mosquitto → Home Assistant.

## 2. Arquitetura

```
BMS ──UART──► dongle ──TLS/MQTT:1883──► proxy (src/bms_proxy.py) ──TLS──► Aliyun
                                          │
                                          ├─ injeta Modbus (property/set WIFI_AP_BSSID)
                                          ├─ decodifica WIFI_Band (src/bms_codec.py)
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

| Caminho | Papel |
|---|---|
| `src/bms_proxy.py` | proxy TLS/MQTT + injeção do polling Modbus |
| `src/bms_codec.py` | decodifica os blocos Modbus (`WIFI_Band`) e grava `bms_state.json` |
| `src/bms_mqtt.py` | publica `bms/state` e registra entidades no HA (discovery) |
| `src/arp_spoof.py` | ARP spoof unidirecional do dongle |
| `scripts/bms-service.sh` | serviço permanente: ARP + DNAT + proxy |
| `scripts/bms_tap.sh` | versão manual (teste) por N segundos |
| `deploy/*.service` | units systemd (ajuste caminho/usuário) |
| `docker-compose.yml` | Home Assistant + Mosquitto |
| `mosquitto/config/mosquitto.conf` | broker (anônimo no teste) |
| `ha-config/configuration.yaml` | `default_config:` (MQTT é configurado pela UI) |
| `.env.example` | TODAS as configurações (copie para `.env`) |
| `README.md` | setup do usuário |

## 4. Regras de ouro (não viole)

1. **Nunca commitar segredos.** `.env`, `cert.pem`, `key.pem`, `tuya.json`,
   `bms_state.json`, `bms_tap.log`, `*.pcap`, `ha-config/.storage` e `mosquitto/data`
   estão no `.gitignore`. Não remova essas entradas.
2. **Nunca tentar a API de nuvem do Tuya de novo.** O caminho foi abandonado:
   o modelo de produto (TuyaLink/TuyaOS) não era publicado e o data center
   respondia `28841107 — data center is suspended`. O app mostra o rascunho de
   desenvolvimento, mas a API vê o modelo de produção vazio
   (`functions: []`, `command or value not support`). **Não gaste tempo nisso.**
   A integração com o Smart Life, se necessária, é por **Matter** (com hub) ou
   por um **medidor DC Tuya com shunt**.
3. **Tudo é configurável por `.env`.** Não hardcode IPs, MACs, ProductKey,
   DeviceName ou chaves. Use `os.environ.get(...)` com defaults seguros.
4. **Peça confirmação antes de**: `sudo`, ARP spoof, `iptables`, `sysctl`,
   reiniciar serviços, alterar `.env` ou mexer na rede. Explique o efeito.
5. **Mudanças mínimas e consistentes.** Respeite `src/`/`scripts/`/`deploy/`.
   Não reescreva o que funciona.
6. **Valide sempre** com `systemctl status`, `journalctl -u bms-tap -f`,
   `mosquitto_sub -t bms/state` e as entidades do HA.
7. **Segurança/legal**: o MITM é para o **dongle do próprio usuário**. Não
   ajude a interceptar terceiros nem a expor o HA/MQTT na internet sem VPN.

## 5. Cheat sheet do protocolo (o que foi descoberto)

- Dongle: Bouffalo **BL606**; o **MAC** costuma estar codificado no serial
  (`DL-F` + MAC sem dois‑pontos). IP fixo/reserva DHCP é obrigatório.
- Endpoint: `public.iot-as-mqtt.us-east-1.aliyuncs.com:1883` com **TLS**.
- O dongle **não valida** o certificado do servidor → um self‑signed local
  funciona. O CONNECT é MQTT 3.1.1, `clean=False`, keepalive 120.
- ClientID: `<ProductKey>.<DeviceName>|securemode=2,...`; username
  `<DeviceName>&<ProductKey>`; password é HMAC (não é o DeviceSecret).
- **Polling**: publicar no tópico
  `/sys/<PK>/<DN>/thing/service/property/set` com
  `{"method":"thing.service.property.set","id":"...","params":{"WIFI_AP_BSSID":"<CMD>"},"version":"1.0.0"}`
  onde `<CMD>` é uma **requisição Modbus RTU em hex**:
  - dados: `D2030000007ED649` (126 registradores a partir de 0x0000)
  - temperaturas/info: `D203008000705665` (112 registradores a partir de 0x0080)
- **Resposta**: `thing/event/property/post` com `params.WIFI_Band` = resposta
  Modbus em hex (`D2 03 <count> <data> <crc16 little-endian>`).
- Mapa de registradores (bloco 0x0000, conferido):
  - `regs[0..7]` = tensões das células (mV)
  - `regs[0x28] / 10` = tensão do pack (V)
  - `(regs[0x29] - 30000) / 10` = corrente (A)
  - `regs[0x2A] / 10` = SOC (%)
  - `regs[0x2B]` / `regs[0x2C]` = célula máx/mín (mV)
  - temperaturas no bloco 0x0080: `regs[0x0A..0x0E] / 100` (°C)
- **Cuidado com offsets**: `regs[i]` é **índice de registrador** (2 bytes),
  não offset de byte. Essa confusão já gerou tensão 64,7 V e corrente -2993 A.
- O dongle só envia os blocos grandes quando a nuvem pede (property/set). Sem
  o polling, ficam só os DPs de MOS.

## 6. Armadilhas já resolvidas (não repita)

| Sintoma | Causa | Correção |
|---|---|---|
| Dongle fica em loop de DNS (`iot-auth-global`) | ARP spoof **bidirecional** quebra o DNS | Use spoof **unidirecional** (`arp_spoof.py ... oneway`) |
| Tunel cai a cada ~10 s | socket de saída com timeout=10 | `up.settimeout(None)` (bloqueante) |
| Dongle autentica (`rc=0`) mas não recebe dados/servidor | Docker deixa `FORWARD` em `DROP` | `iptables -I FORWARD -s/-d <dongle> -j ACCEPT` (o script faz) |
| HA não aceita `mqtt:` no YAML | integração MQTT virou UI | remova do YAML e adicione em *Add Integration → MQTT* |
| Porta 1883 em conflito | proxy e Mosquitto | Mosquitto no host **1884** (`1884:1883`) |
| Entidades com `unavailable`/avisos de template | publicador pegou estado parcial | `bms_mqtt.py` só publica com `voltage`/`soc`/`cells` e faz merge |
| Dongle muda de IP | DHCP | reserva DHCP pelo MAC |

## 7. Como reproduzir do zero

1. **Descobrir o dongle**: reserva DHCP no roteador; anote IP e MAC.
2. **Configurar**: `cp .env.example .env` e preencha `BMS_DONGLE_IP`,
   `BMS_DONGLE_MAC`, `BMS_HOST_IP` (ou auto).
3. **Descobrir ProductKey/DeviceName**: rode
   `sudo bash scripts/bms_tap.sh 60` e leia o `CONNECT` no log/`journalctl`.
   Preencha no `.env`.
4. **Python**: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
5. **HA + MQTT**: `docker compose up -d`; abra `http://<host>:8123`, crie a conta
   e adicione **MQTT** (broker `mosquitto`, porta `1883`, sem auth).
6. **Serviços**: ajuste `deploy/*.service` (`/opt/bms`, `User=`) e
   `systemctl enable --now bms-tap bms-mqtt`.
7. **Validar**: `mosquitto_sub -t bms/state -v` e as entidades no HA.
8. **LocalTuya** (opcional): instale o custom component em
   `ha-config/custom_components/localtuya`, adicione IP/Device ID/Local Key e
   versão 3.4; mapeie o DP 1 como switch/light.

## 8. Como o agente deve ajudar

- Comece lendo `README.md`, `AGENTS.md` e `.env.example`.
- Antes de codar, **descreva o plano** e peça OK se envolver rede/root.
- Prefira editar `src/`/`scripts/` com mudanças pequenas e testáveis.
- Use `rg`/`grep`, `systemctl`, `journalctl`, `mosquitto_sub` para diagnosticar.
- Não exponha valores de `.env` em respostas, commits ou logs de exemplo.
- Se o usuário pedir “Smart Life/Tuya”, explique o caminho **Matter** ou
  **medidor DC**; não reabra a API de nuvem do Tuya.
- Se algo não puder ser feito sem a senha/root, **peça ao usuário** para rodar o
  comando; nunca peça a senha.
