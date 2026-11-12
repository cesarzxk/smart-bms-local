# Deploy no homelab

Guia para levar o projeto da máquina de desenvolvimento para um host fixo
(homelab). O ponto crítico: **o homelab precisa estar no mesmo L2 (mesma VLAN)
que o dongle do BMS** — o ARP spoof não atravessa VLAN/roteador.

## 1. Pré-requisitos

- Host Linux (VM ou bare metal) ligado 24/7, na mesma rede do dongle.
- `python3`, `python3-venv`, `openssl`, `iptables`, Docker + Compose.
- IP fixo (ou reserva DHCP) para o host e para o dongle.
- Portas livres: **8123** (HA), **1884** (Mosquitto no host), **1883** (proxy,
  só na interface LAN).

> Evite LXC/container para o proxy: ele precisa de raw socket/ARP/iptables.
> Rode o `bms-tap` no **host** (ou numa VM com NIC em bridge).

## 2. Clonar e configurar

```bash
git clone https://github.com/cesarzxk/smart-bms-local.git /opt/bms
cd /opt/bms
cp .env.example .env
nano .env
```

Preencha no mínimo:

```env
BMS_DONGLE_IP=192.168.x.y          # IP do dongle (reserva DHCP)
BMS_DONGLE_MAC=aa:bb:cc:dd:ee:ff   # MAC do dongle
BMS_PRODUCT_KEY=...                # do CONNECT do dongle
BMS_DEVICE_NAME=...                # do CONNECT do dongle
# BMS_HOST_IP/BMS_IFACE podem ficar vazios (auto-detecta)
```

Se você já tem o `.env` funcionando na máquina antiga, copie só ele e ajuste
`BMS_HOST_IP`/`BMS_IFACE` se a interface/IP forem diferentes:

```bash
scp usuario@maquina-antiga:/caminho/bms/.env /opt/bms/.env
```

## 3. Dependências Python

```bash
cd /opt/bms
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 4. Home Assistant + Mosquitto

```bash
docker compose up -d
docker compose ps
```

- HA: `http://<IP_DO_HOMELAB>:8123`
- MQTT (host): `127.0.0.1:1884`

### Migrar o HA atual (opcional, recomendado para manter tudo)

Se quiser levar usuário, integração MQTT, LocalTuya e automações:

```bash
# na máquina antiga
rsync -a --exclude '*.log' --exclude 'home-assistant_v2.db' \
  ~/Desktop/bms/ha-config/ usuario@homelab:/opt/bms/ha-config/
```

Depois `docker compose restart homeassistant`. O broker continua sendo o
serviço `mosquitto` da mesma compose.

Se preferir começar limpo: abra o HA, crie a conta e adicione **MQTT**
(broker `mosquitto`, porta `1883`, sem auth). O discovery cria as entidades do
BMS sozinho.

## 5. Serviços systemd

Ajuste os units de `deploy/` para o caminho/usuário reais:

```bash
sed -i 's|/opt/bms|/opt/bms|g' deploy/*.service   # ajuste se instalou em outro lugar
sed -i 's|User=bms|User=SEU_USUARIO|' deploy/bms-mqtt.service
sudo cp deploy/bms-tap.service deploy/bms-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bms-tap bms-mqtt
```

> `bms-tap` roda como **root** (ARP/iptables). `bms-mqtt` roda como o usuário
> dono do projeto (só lê o estado e publica no MQTT local).

## 6. Cutover (importante)

Só **um** proxy pode interceptar o dongle. Antes de subir no homelab, pare o
tap na máquina antiga:

```bash
# na máquina antiga
sudo systemctl disable --now bms-tap bms-mqtt
# se o HA antigo não for mais usado:
# sudo docker compose down
```

O dongle vai reconectar no homelab em até ~1 minuto (o proxy reencaminha para a
nuvem do fabricante, então o app continua funcionando).

## 7. Validar

```bash
systemctl status bms-tap bms-mqtt
journalctl -u bms-tap -f          # deve mostrar CONNECT rc=0 e PUBLISH WIFI_Band
mosquitto_sub -t bms/state -v     # JSON com voltage/soc/cells/temps
```

No HA: **Settings → Devices & Services → MQTT → BMS 8S 24V** deve atualizar a
cada ~30 s.

Teste uma automação (ex.: SOC baixo → desligar luz via LocalTuya) com **Run**.

## 8. Troubleshooting

| Sintoma | Verifique |
|---|---|
| Dongle não conecta | IP/MAC no `.env`, reserva DHCP, `systemctl status bms-tap`, mesma VLAN |
| Loop de DNS `iot-auth-global` | spoof bidirecional (use `oneway`), `FORWARD` em DROP |
| Tunel cai a cada 10 s | socket com timeout (deve ser `settimeout(None)`) |
| HA não recebe | `mosquitto_sub`, integração MQTT, `docker compose ps` |
| Entidades `unavailable` | estado parcial (o publicador espera voltage/soc/cells) |
| Porta ocupada | 8123/1883/1884 já em uso no homelab |

## 9. Segurança

- `.env`, certificados e `ha-config/.storage` **não** vão para o Git.
- Não exponha HA/MQTT na internet sem VPN (Tailscale/WireGuard).
- Para produção, ative autenticação no Mosquitto.
- O MITM é só para o seu próprio dongle.
