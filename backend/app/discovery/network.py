"""Conservative network observation helpers for Discovery."""

import ipaddress
import re
import subprocess
from collections.abc import Iterable

import dns.exception
import dns.resolver
import dns.reversename

from app.network.utils import ping_host


MAC_PATTERN = re.compile(r"(?i)\b([0-9a-f]{2}(?:[:-][0-9a-f]{2}){5})\b")
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def normalize_mac(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"[^0-9a-fA-F]", "", value)
    if len(compact) != 12:
        return None
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2)).lower()


def validate_private_network(value: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value.strip(), strict=False)
    except ValueError as exc:
        raise ValueError(f"Invalid CIDR range: {value}") from exc
    if network.version != 4:
        raise ValueError("Discovery currently supports private IPv4 ranges only")
    if not network.is_private:
        raise ValueError("Discovery is restricted to private network ranges")
    return network


def parse_networks(values: str | Iterable[str], *, allow_empty: bool = False) -> list[ipaddress.IPv4Network]:
    items = values.split(",") if isinstance(values, str) else values
    networks = [validate_private_network(item) for item in items if item and item.strip()]
    if not networks and not allow_empty:
        raise ValueError("At least one private CIDR range is required")
    return networks


def ensure_authorized(
    requested: str,
    authorized_ranges: str | Iterable[str],
    ignore_ranges: str | Iterable[str] = (),
    *,
    max_hosts: int,
) -> tuple[ipaddress.IPv4Network, list[ipaddress.IPv4Network]]:
    network = validate_private_network(requested)
    authorized = parse_networks(authorized_ranges)
    ignored = parse_networks(ignore_ranges, allow_empty=True)
    if not any(network.subnet_of(parent) for parent in authorized):
        raise ValueError("Requested range is outside the authorized discovery ranges")
    usable_hosts = network.num_addresses if network.prefixlen >= 31 else max(0, network.num_addresses - 2)
    if usable_hosts > max_hosts:
        raise ValueError(f"Requested range exceeds the {max_hosts}-host discovery limit")
    return network, ignored


def is_ignored(address: ipaddress.IPv4Address, ignored: Iterable[ipaddress.IPv4Network]) -> bool:
    return any(address in network for network in ignored)


def inspect_arp_table(timeout_seconds: float = 3.0) -> dict[str, str]:
    """Read the operating system's existing neighbor cache; sends no packets."""
    commands = (["arp", "-a"], ["ip", "neigh", "show"])
    output = ""
    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                shell=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
        if result.stdout:
            output = result.stdout
            break
    entries: dict[str, str] = {}
    for line in output.splitlines():
        ip_match = IP_PATTERN.search(line)
        mac_match = MAC_PATTERN.search(line)
        if not ip_match or not mac_match:
            continue
        try:
            address = ipaddress.ip_address(ip_match.group(0))
        except ValueError:
            continue
        mac = normalize_mac(mac_match.group(1))
        if address.version == 4 and mac and mac != "ff:ff:ff:ff:ff:ff":
            entries[str(address)] = mac
    return entries


def reverse_dns(ip_address: str, timeout_seconds: float = 1.0) -> str | None:
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout_seconds
        resolver.lifetime = timeout_seconds
        answer = resolver.resolve(dns.reversename.from_address(ip_address), "PTR")
        hostname = str(answer[0]).rstrip(".")
        return hostname[:255] or None
    except (dns.exception.DNSException, ValueError, OSError):
        return None


def icmp_probe(ip_address: str, timeout_seconds: int) -> tuple[bool, float | None]:
    result = ping_host(ip_address, timeout=timeout_seconds)
    return result["status"].lower() == "online", result["response_time"]
