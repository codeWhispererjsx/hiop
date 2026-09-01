import ipaddress
import os
import re
import subprocess
import time

from ping3 import ping


def ping_host(ip: str, timeout: int = 1):
    try:
        if os.name == "nt":
            started = time.perf_counter()
            result = subprocess.run(
                ["ping", "-n", "1", "-w", str(max(250, int(timeout * 1000))), ip],
                capture_output=True,
                text=True,
                timeout=max(2.0, float(timeout) + 1.0),
                check=False,
                shell=False,
            )
            online = result.returncode == 0 and re.search(r"(?i)TTL[=:]", result.stdout or "") is not None
            return {
                "status": "Online" if online else "Offline",
                "response_time": round((time.perf_counter() - started) * 1000, 2) if online else None,
            }
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

    except (Exception, subprocess.SubprocessError):
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
