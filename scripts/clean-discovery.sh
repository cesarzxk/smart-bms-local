#!/usr/bin/env bash
# Remove retained Home Assistant MQTT discovery configs antigos (entidades duplicadas).
# Uso:
#   sudo bash scripts/clean-discovery.sh
# Variáveis:
#   MOSQUITTO_CONTAINER=mosquitto   BMS_MQTT_CONTAINER=bms-mqtt
#   DISCOVERY_PREFIX=homeassistant  FILTER=bms
#   RESTART_PUBLISHER=1             DRY_RUN=0
set -euo pipefail

MOSQ_CONTAINER="${MOSQUITTO_CONTAINER:-mosquitto}"
PUB_CONTAINER="${BMS_MQTT_CONTAINER:-bms-mqtt}"
PREFIX="${DISCOVERY_PREFIX:-homeassistant}"
FILTER="${FILTER:-bms}"
RESTART="${RESTART_PUBLISHER:-1}"
DRY_RUN="${DRY_RUN:-0}"

have_docker() { command -v docker >/dev/null 2>&1; }
container_running() {
  have_docker && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$1"
}

if container_running "$MOSQ_CONTAINER"; then
  LIST=(docker exec "$MOSQ_CONTAINER" mosquitto_sub -t "$PREFIX/#" -W 3 -F '%t')
  DEL=(docker exec "$MOSQ_CONTAINER" mosquitto_pub -r -n -t)
  MODE="container:$MOSQ_CONTAINER"
elif command -v mosquitto_sub >/dev/null 2>&1 && command -v mosquitto_pub >/dev/null 2>&1; then
  HOST="${MQTT_HOST:-127.0.0.1}"
  PORT="${MQTT_PORT:-1884}"
  LIST=(mosquitto_sub -h "$HOST" -p "$PORT" -t "$PREFIX/#" -W 3 -F '%t')
  DEL=(mosquitto_pub -h "$HOST" -p "$PORT" -r -n -t)
  MODE="local:$HOST:$PORT"
else
  echo "ERRO: nao encontrei o container '$MOSQ_CONTAINER' nem mosquitto_sub/pub local."
  echo "      Rode no host do Portainer (ou ajuste MOSQUITTO_CONTAINER)."
  exit 1
fi

echo "[clean] broker: $MODE | prefix: $PREFIX | filtro: '$FILTER' | dry-run: $DRY_RUN"

mapfile -t TOPICS < <("${LIST[@]}" 2>/dev/null || true)
COUNT=0
for T in "${TOPICS[@]}"; do
  case "$T" in
    *"$FILTER"*/config)
      if [ "$DRY_RUN" = "1" ]; then
        echo "  [dry-run] removeria $T"
      else
        "${DEL[@]}" "$T" 2>/dev/null || true
        echo "  removido $T"
      fi
      COUNT=$((COUNT + 1))
      ;;
  esac
done

echo "[clean] $COUNT topico(s) de discovery retido(s) encontrados."

if [ "$DRY_RUN" != "1" ] && [ "$RESTART" = "1" ] && container_running "$PUB_CONTAINER"; then
  docker restart "$PUB_CONTAINER" >/dev/null
  echo "[clean] $PUB_CONTAINER reiniciado para republicar o discovery atual."
fi
