import socket
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

import requests


def read_location(resp, keyword=None):
    if not isinstance(resp, str):
        resp = resp.decode('utf-8')

    for line in resp.splitlines():
        line = line.lower()
        header = "location: "
        if line.startswith(header):
            return line[len(header):]


def validate_location(location, keyword, timeout=5):
    if isinstance(keyword, str):
        keyword = keyword.encode()

    try:
        content = requests.get(location, timeout=timeout).content
        if not keyword:
            return True
        return keyword in content
    except requests.exceptions.RequestException:
        return False


# Adapted from Dan Krause (https://gist.github.com/dankrause/6000248)
def discover(service, keyword=None, hosts=False, retries=1, timeout=5, mx=3):
    group = ('239.255.255.250', 1900)
    locations = set()
    seen = set()

    message = "\r\n".join([
        'M-SEARCH * HTTP/1.1',
        'HOST: {0}:{1}',
        'MAN: "ssdp:discover"',
        'ST: {st}',
        'MX: {mx}',
        '', '']).format(*group, st=service, mx=mx).encode('ascii')

    for _ in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                             socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        sock.sendto(message, group)

        while True:
            try:
                location = read_location(sock.recv(1024))
                if location and location not in seen:
                    seen.add(location)
                    if validate_location(location, keyword, timeout=timeout):
                        locations.add(location)
            except socket.timeout:
                break

    if hosts:
        return {urlparse(x).hostname for x in locations}
    else:
        return {x for x in locations}
