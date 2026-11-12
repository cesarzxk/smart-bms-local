FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    BMS_DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash ca-certificates iproute2 iptables iputils-ping openssl procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY scripts ./scripts

RUN mkdir -p /data
CMD ["bash", "scripts/bms-service.sh"]
