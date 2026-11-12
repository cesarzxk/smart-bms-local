#!/usr/bin/env bash
# Serviço permanente: ARP spoof + DNAT + proxy TLS para o servidor do fabricante.
# Configuração via .env na raiz do projeto (veja .env.example).
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi
export BMS_DATA_DIR="${BMS_DATA_DIR:-$ROOT}"

IFACE="${BMS_IFACE:-$(ip route | awk '/^default/{print $5; exit}')}"
if [ -z "$IFACE" ] || [ ! -d "/sys/class/net/$IFACE" ]; then
  echo "ERRO: interface '$IFACE' nao existe nesta maquina."
  echo "      Defina BMS_IFACE no .env ou deixe vazio para auto-detectar."
  echo "      Interfaces: $(ls /sys/class/net | tr '\n' ' ')"
  exit 1
fi
GW="${BMS_GATEWAY_IP:-$(ip route | awk '/^default/{print $3; exit}')}"
GW_MAC="${BMS_GATEWAY_MAC:-$(ip neigh show "$GW" | awk '{print $5; exit}')}"
OUR_MAC="$(cat "/sys/class/net/$IFACE/address")"
if [ -z "$OUR_MAC" ]; then
  echo "ERRO: nao consegui ler a MAC da interface $IFACE"
  exit 1
fi
ME="${BMS_HOST_IP:-$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)}"
SRC="${BMS_DONGLE_IP:?defina BMS_DONGLE_IP no .env}"
SRC_MAC="${BMS_DONGLE_MAC:?defina BMS_DONGLE_MAC no .env}"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: precisa rodar como root (systemd)"
  exit 1
fi

if [ -z "$GW_MAC" ]; then
  ping -c 1 -W 1 "$GW" >/dev/null 2>&1
  GW_MAC="$(ip neigh show "$GW" | awk '{print $5; exit}')"
fi
if [ -z "$GW_MAC" ]; then
  echo "ERRO: nao consegui resolver a MAC do gateway"
  exit 1
fi

if [ ! -f "$BMS_DATA_DIR/cert.pem" ] || [ ! -f "$BMS_DATA_DIR/key.pem" ]; then
  echo "[servico] gerando certificado self-signed em $BMS_DATA_DIR"
  if ! openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$BMS_DATA_DIR/key.pem" -out "$BMS_DATA_DIR/cert.pem" \
    -days 3650 -subj "/CN=bms-local"; then
    echo "ERRO: falha ao gerar certificado em $BMS_DATA_DIR"
    exit 1
  fi
fi

sysctl -w net.ipv4.ip_forward=1 >/dev/null

python3 "$ROOT/src/arp_spoof.py" "$IFACE" "$SRC" "$SRC_MAC" "$GW" "$GW_MAC" "$OUR_MAC" oneway &
SPOOF=$!
sleep 2

iptables -I FORWARD 1 -s "$SRC" -j ACCEPT
iptables -I FORWARD 1 -d "$SRC" -j ACCEPT
iptables -t nat -A PREROUTING -s "$SRC" -p tcp --dport 1883 -j DNAT --to-destination "$ME":1883
iptables -t nat -A PREROUTING -s "$SRC" -p tcp --dport 8883 -j DNAT --to-destination "$ME":1883

cleanup() {
  iptables -t nat -D PREROUTING -s "$SRC" -p tcp --dport 1883 -j DNAT --to-destination "$ME":1883 2>/dev/null
  iptables -t nat -D PREROUTING -s "$SRC" -p tcp --dport 8883 -j DNAT --to-destination "$ME":1883 2>/dev/null
  iptables -D FORWARD -s "$SRC" -j ACCEPT 2>/dev/null
  iptables -D FORWARD -d "$SRC" -j ACCEPT 2>/dev/null
  kill -TERM "$SPOOF" 2>/dev/null
  wait "$SPOOF" 2>/dev/null
  echo "[servico] regras removidas e ARP restaurado"
}
trap cleanup EXIT INT TERM

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

echo "[servico] tap ativo; iniciando proxy"
"$PY" -u "$ROOT/src/bms_proxy.py" &
PROXY=$!
wait "$PROXY"
echo "[servico] proxy terminou"
