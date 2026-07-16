import ipaddress

from ping3 import ping


def ping_host(ip: str, timeout: int = 1):
    try:
        response = ping(ip, timeout=timeout)

        if response is None or response is False:
            return {
                "status": "Offline",
                "response_time": None
            }

        return {
            "status": "Online",
            "response_time": round(response * 1000, 2)
        }

    except Exception:
        return {
            "status": "Offline",
            "response_time": None
        }


def scan_range(network: str):
    """
    Scan all hosts in a CIDR network.

    Example:
        scan_range("192.168.1.0/24")
    """

    results = []

    net = ipaddress.ip_network(network, strict=False)

    for host in net.hosts():
        ip = str(host)

        result = ping_host(ip)

        results.append({
            "ip_address": ip,
            "status": result["status"],
            "response_time": result["response_time"],
        })

    return results
