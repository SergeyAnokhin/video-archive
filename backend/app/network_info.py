"""LAN address discovery for the Settings -> Network section (post-V1, user
request -- "connect from a phone on the same network / phone hotspot").
Pure best-effort: every lookup is wrapped so a sandboxed or offline machine
still returns whatever it can rather than raising.
"""

import socket


def get_lan_addresses() -> list[str]:
    addresses: list[str] = []

    # The outbound-facing address for this host, found via a UDP socket
    # connect() -- no packet is actually sent, this only asks the OS which
    # local interface/IP would be used to reach that destination, so it
    # works offline too and reliably picks the "primary" LAN IP over e.g.
    # virtual adapters.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.append(sock.getsockname()[0])
    except OSError:
        pass

    # Any other IPv4 addresses bound to this host, covering multi-adapter
    # setups (e.g. Ethernet + Wi-Fi, or a phone-hotspot adapter) that the
    # trick above wouldn't surface.
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in addresses and not ip.startswith("127."):
                addresses.append(ip)
    except OSError:
        pass

    return addresses
