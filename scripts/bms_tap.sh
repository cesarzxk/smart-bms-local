#!/usr/bin/env bash
# Versão manual (teste): ARP spoof + DNAT + proxy por N segundos.
# Uso: sudo bash scripts/bms_tap.sh [segundos]
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
GW="${BMS_GATEWAY_IP:-$(ip route | awk '/^default/{print $3; exit}')}"
GW_MAC="${BMS_GATEWAY_MAC:-$(ip neigh show "$GW" | awk '{print $5; exit}')}"
OUR_MAC="$(cat "/sys/class/net/$IFACE/address")"
ME="${BMS_HOST_IP:-$(ip -4 addr show "$IFACE" | awk '/inet /{print $2}' | cut -d/ -f1 | head -1)}"
SRC="${BMS_DONGLE_IP:?defina BMS_DONGLE_IP no .env}"
SRC_MAC="${BMS_DONGLE_MAC:?defina BMS_DONGLE_MAC no .env}"
DUR="${1:-180}"

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: rode com sudo"
  exit 1
fi

if [ ! -f "$ROOT/cert.pem" ] || [ ! -f "$ROOT/key.pem" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$ROOT/key.pem" -out "$ROOT/cert.pem" \
    -days 3650 -subj "/CN=bms-local" 2>/dev/null
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
  echo "[*] regras removidas e ARP restaurado"
}
trap cleanup EXIT INT TERM

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3

echo "[*] tap ativo por ${DUR}s"
timeout "$DUR" "$PY" -u "$ROOT/src/bms_proxy.py"
echo "[*] encerrando"
