# Deploy no Portainer

Duas opções. A **B (imagem)** é a mais limpa para homelab: o GitHub Actions
builda a imagem e o Portainer só faz `pull`.

## Pré-requisitos

- Portainer no **mesmo L2/VLAN do dongle** (ARP spoof não atravessa roteador).
- Docker no host do Portainer.
- Portas livres: **8123** (HA), **1884** (Mosquitto), **1883** (proxy, host).
- O container `bms-tap` roda com `network_mode: host` + `privileged: true`,
  porque precisa de raw socket/ARP e de `iptables`/`sysctl` no host.
- Só **um** `bms-tap` na rede (pare o da máquina antiga).

## Opção A — build direto no Portainer (compose do repositório)

1. **Stacks → Add stack → Repository**
2. Repository URL: `https://github.com/cesarzxk/smart-bms-local`
3. Branch: `main`
4. Compose path: `docker-compose.portainer.yml`
5. Em **Environment variables**, cole o conteúdo de `stack.env.example` e
   preencha `BMS_DONGLE_IP`, `BMS_DONGLE_MAC`, `BMS_PRODUCT_KEY`,
   `BMS_DEVICE_NAME`.
6. **Deploy the stack**.

O Portainer clona o repo, builda `smart-bms-local:latest` e sobe HA +
Mosquitto + `bms-tap` + `bms-mqtt`.

## Opção B — imagem do GHCR (recomendada)

O workflow `.github/workflows/docker.yml` publica em:

```
ghcr.io/cesarzxk/smart-bms-local:latest
```

1. Espere o Action **build-image** terminar (GitHub → Actions).
2. Torne o pacote **público** (GitHub → seu perfil → Packages →
   `smart-bms-local` → Package settings → Change visibility → Public) **ou**
   cadastre no Portainer um registry `ghcr.io` com um PAT com `read:packages`.
3. **Stacks → Add stack → Repository**:
   - URL: `https://github.com/cesarzxk/smart-bms-local`
   - Compose path: `docker-compose.portainer-image.yml`
4. Preencha as **Environment variables** (mesmo `stack.env.example`) e
   **Deploy**.

Para fixar versão, use uma tag no GitHub (`v1.0.0`) e troque a imagem para
`ghcr.io/cesarzxk/smart-bms-local:v1.0.0`.

## Variáveis obrigatórias

| Variável | Exemplo |
|---|---|
| `BMS_DONGLE_IP` | `192.168.1.50` |
| `BMS_DONGLE_MAC` | `aa:bb:cc:dd:ee:ff` |
| `BMS_PRODUCT_KEY` | do `CONNECT` do dongle |
| `BMS_DEVICE_NAME` | do `CONNECT` do dongle |

Opcionais (`BMS_HOST_IP`, `BMS_IFACE`, `BMS_GATEWAY_*`) são auto-detectados.
`TZ`, `BMS_NAME`, `BMS_ID`, `MQTT_*` têm defaults.

## Depois do deploy

1. Abra `http://<host-do-portainer>:8123` e crie a conta do HA.
2. **Settings → Devices & Services → Add Integration → MQTT**
   - Broker: `mosquitto` (mesma rede do compose)
   - Port: `1883`
   - Sem usuário/senha (teste)
3. Valide:
   ```bash
   docker logs -f bms-tap        # CONNECT rc=0 e PUBLISH WIFI_Band
   docker logs -f bms-mqtt       # [mqtt] {...}
   ```
4. No HA, o dispositivo **BMS 8S 24V** aparece com SOC, tensão, corrente,
   potência, células e temperatura.

## Migrar o HA atual (opcional)

O compose usa o volume nomeado `ha_config`. Para levar o HA da máquina antiga:

```bash
# no host do Portainer, com o stack parado
docker run --rm -v <stack>_ha_config:/dest -v /caminho/ha-config:/src alpine \
  sh -c "cp -a /src/. /dest/"
```

Ou troque no compose `ha_config:/config` por um bind mount
(`/opt/bms/ha-config:/config`) e copie a pasta.

## Observações e troubleshooting

- `privileged: true` é necessário. Se o Portainer bloquear containers
  privilegiados, rode o `bms-tap` no host (systemd) e deixe só HA/Mosquitto no
  Portainer.
- Se o `iptables` do container não afetar o host (host com `iptables-legacy`),
  rode o tap no host ou ajuste a imagem para `iptables-legacy`.
- Se `ip_forward` não puder ser escrito no container, habilite no host:
  `sudo sysctl -w net.ipv4.ip_forward=1`.
- Porta 1883 ocupada: o proxy precisa dela no host; o Mosquitto usa 1884.
- HA/MQTT não aparecem: veja `docker logs bms-mqtt`, `docker logs mosquitto`.
- O dongle mudou de IP: ajuste `BMS_DONGLE_IP` nas env vars e reimplante.
