from ping3 import ping


def ping_host(ip: str):
    response = ping(ip, timeout=1)

    if response is None:
        return {
            "status": "Offline",
            "response_time": None
        }

    return {
        "status": "Online",
        "response_time": round(response * 1000, 2)
    }


def scan_range(network: str):
    results = []

    for i in range(1, 11):   # We'll scan only .1 - .10 first
        ip = f"{network}.{i}"

        result = ping_host(ip)

        results.append({
            "ip_address": ip,
            "status": result["status"],
            "response_time": result["response_time"]
        })

    return results