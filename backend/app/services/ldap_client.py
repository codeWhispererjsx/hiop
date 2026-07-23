from __future__ import annotations

import ipaddress
import logging
import socket
import ssl
import struct
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from ldap3 import (
    ALL,
    ANONYMOUS,
    BASE,
    NONE,
    SIMPLE,
    SUBTREE,
    Connection,
    Server,
    Tls,
)
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn

from app.core.config import settings

logger = logging.getLogger(__name__)

PAGED_RESULTS_OID = "1.2.840.113556.1.4.319"
USER_FILTER = "(&(objectCategory=person)(objectClass=user)(!(objectClass=computer)))"
COMPUTER_FILTER = "(&(objectCategory=computer)(objectClass=computer))"
GROUP_FILTER = "(&(objectCategory=group)(objectClass=group))"
ROOT_DSE_ATTRIBUTES = (
    "defaultNamingContext",
    "rootDomainNamingContext",
    "configurationNamingContext",
    "schemaNamingContext",
    "supportedLDAPVersion",
    "supportedSASLMechanisms",
    "dnsHostName",
    "serverName",
)
USER_ATTRIBUTES = (
    "objectGUID", "objectSid", "sAMAccountName", "userPrincipalName", "displayName",
    "mail", "department", "title", "distinguishedName", "memberOf",
    "userAccountControl", "whenCreated", "whenChanged", "lastLogonTimestamp",
    "description",
)
COMPUTER_ATTRIBUTES = (
    "objectGUID", "objectSid", "sAMAccountName", "dNSHostName", "operatingSystem",
    "operatingSystemVersion", "distinguishedName", "description", "managedBy",
    "userAccountControl", "whenCreated", "whenChanged", "lastLogonTimestamp",
)
GROUP_ATTRIBUTES = (
    "objectGUID", "objectSid", "sAMAccountName", "cn", "distinguishedName",
    "description", "groupType", "whenCreated", "whenChanged",
)
SAFE_SEARCH_ATTRIBUTES = {
    "sAMAccountName", "userPrincipalName", "displayName", "mail", "dNSHostName", "cn",
}


class LdapError(Exception):
    def __init__(self, category: str, safe_message: str, *, retryable: bool = False):
        super().__init__(safe_message)
        self.category = category
        self.safe_message = safe_message
        self.retryable = retryable


@dataclass(slots=True)
class LdapClientConfig:
    connection_id: str
    host: str
    port: int
    use_ssl: bool
    use_start_tls: bool
    verify_tls: bool
    ca_certificate_reference: str | None
    authentication_method: str
    connect_timeout: int
    search_timeout: int
    page_size: int
    maximum_page_size: int
    maximum_objects: int
    domain_name: str
    environment: str
    allow_insecure_ldap: bool
    approved_hosts: tuple[str, ...] = ()
    allow_public_hosts: bool = False
    retry_count: int = 1


@dataclass(slots=True)
class LdapSearchResult:
    items: list[dict[str, Any]]
    truncated: bool
    page_count: int
    warnings: list[str] = field(default_factory=list)


def validate_dn_syntax(value: str) -> bool:
    try:
        return bool(value and parse_dn(value, escape=True))
    except (LDAPException, TypeError, ValueError):
        return False


def dn_within(child: str, parent: str) -> bool:
    if not validate_dn_syntax(child) or not validate_dn_syntax(parent):
        return False
    normalized_child = ",".join(part.strip().casefold() for part in child.split(","))
    normalized_parent = ",".join(part.strip().casefold() for part in parent.split(","))
    return normalized_child == normalized_parent or normalized_child.endswith("," + normalized_parent)


def escape_filter_value(value: str, *, allow_wildcard: bool = False) -> str:
    value = value.strip()
    if len(value) > 64:
        raise LdapError("configuration_error", "Search term is too long.")
    if not allow_wildcard and "*" in value:
        raise LdapError("configuration_error", "Wildcard characters are not accepted.")
    return escape_filter_chars(value)


def build_search_filter(
    object_type: str,
    *,
    search_term: str | None = None,
    search_attribute: str | None = None,
    enabled: bool | None = None,
) -> str:
    templates = {"user": USER_FILTER, "computer": COMPUTER_FILTER, "group": GROUP_FILTER}
    if object_type not in templates:
        raise LdapError("configuration_error", "Unsupported directory object type.")
    clauses = [templates[object_type]]
    if search_term:
        attribute = search_attribute or {
            "user": "sAMAccountName",
            "computer": "dNSHostName",
            "group": "cn",
        }[object_type]
        if attribute not in SAFE_SEARCH_ATTRIBUTES:
            raise LdapError("configuration_error", "Search attribute is not allowed.")
        clauses.append(f"({attribute}=*{escape_filter_value(search_term)}*)")
    if enabled is not None and object_type in {"user", "computer"}:
        disabled = "(userAccountControl:1.2.840.113556.1.4.803:=2)"
        clauses.append(f"(!{disabled})" if enabled else disabled)
    return f"(&{''.join(clauses)})" if len(clauses) > 1 else clauses[0]


def convert_guid(value: Any) -> str | None:
    if value in (None, b"", ""):
        return None
    try:
        if isinstance(value, bytes):
            return str(uuid.UUID(bytes_le=value))
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def convert_sid(value: Any) -> str | None:
    if value in (None, b"", ""):
        return None
    if isinstance(value, str):
        return value if value.startswith("S-") else None
    try:
        revision, count = value[0], value[1]
        authority = int.from_bytes(value[2:8], "big")
        sub_authorities = struct.unpack(f"<{count}I", value[8:8 + 4 * count])
        return "-".join(["S", str(revision), str(authority), *map(str, sub_authorities)])
    except (IndexError, TypeError, struct.error):
        return None


def convert_filetime(value: Any) -> datetime | None:
    if value in (None, "", 0, "0", 9223372036854775807, "9223372036854775807"):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=int(value) / 10)
    except (TypeError, ValueError, OverflowError):
        return None


def convert_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    for pattern in ("%Y%m%d%H%M%S.0Z", "%Y%m%d%H%M%SZ"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def organizational_unit(dn: str | None) -> str | None:
    if not dn:
        return None
    parts = [part.strip()[3:] for part in dn.split(",") if part.strip().upper().startswith("OU=")]
    return "/".join(reversed(parts)) or None


def account_enabled(value: Any) -> bool:
    try:
        return not bool(int(value or 0) & 2)
    except (TypeError, ValueError):
        return True


def convert_group_type(value: Any) -> dict[str, Any]:
    try:
        unsigned = int(value or 0) & 0xFFFFFFFF
    except (TypeError, ValueError):
        unsigned = 0
    scope = "universal" if unsigned & 0x8 else "domain_local" if unsigned & 0x4 else "global"
    return {"scope": scope, "security": bool(unsigned & 0x80000000), "raw": unsigned}


def _first(attributes: dict[str, Any], name: str) -> Any:
    value = attributes.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def convert_entry(
    object_type: str,
    attributes: dict[str, Any],
    raw_attributes: dict[str, list[bytes]] | None = None,
    *,
    include_members: bool = False,
    member_limit: int = 100,
) -> dict[str, Any]:
    raw_attributes = raw_attributes or {}
    errors: list[str] = []
    guid = convert_guid(_first(raw_attributes, "objectGUID") or _first(attributes, "objectGUID"))
    sid = convert_sid(_first(raw_attributes, "objectSid") or _first(attributes, "objectSid"))
    if not guid:
        errors.append("objectGUID could not be parsed")
    common = {
        "object_guid": guid,
        "object_sid": sid,
        "distinguished_name": _first(attributes, "distinguishedName"),
        "sam_account_name": _first(attributes, "sAMAccountName"),
        "description": _first(attributes, "description"),
        "when_created": convert_datetime(_first(attributes, "whenCreated")),
        "when_changed": convert_datetime(_first(attributes, "whenChanged")),
        "parse_warnings": errors,
    }
    common["organizational_unit"] = organizational_unit(common["distinguished_name"])
    if object_type == "user":
        common.update({
            "user_principal_name": _first(attributes, "userPrincipalName"),
            "display_name": _first(attributes, "displayName"),
            "email": _first(attributes, "mail"),
            "department": _first(attributes, "department"),
            "job_title": _first(attributes, "title"),
            "group_memberships": list(attributes.get("memberOf") or []),
            "enabled": account_enabled(_first(attributes, "userAccountControl")),
            "last_logon_at": convert_filetime(_first(attributes, "lastLogonTimestamp")),
        })
    elif object_type == "computer":
        hostname = _first(attributes, "dNSHostName")
        common.update({
            "dns_hostname": str(hostname).lower() if hostname else None,
            "operating_system": _first(attributes, "operatingSystem"),
            "operating_system_version": _first(attributes, "operatingSystemVersion"),
            "managed_by": _first(attributes, "managedBy"),
            "enabled": account_enabled(_first(attributes, "userAccountControl")),
            "last_logon_at": convert_filetime(_first(attributes, "lastLogonTimestamp")),
        })
    else:
        members = list(attributes.get("member") or []) if include_members else []
        common.update({
            "common_name": _first(attributes, "cn"),
            "group_type": convert_group_type(_first(attributes, "groupType")),
            "members": members[:member_limit],
            "members_truncated": include_members and len(members) > member_limit,
            "member_count_returned": min(len(members), member_limit),
        })
    return common


def classify_ldap_error(error: Exception | dict[str, Any]) -> LdapError:
    text = str(error).casefold()
    if isinstance(error, dict):
        text = f"{error.get('description', '')} {error.get('message', '')}".casefold()
    mapping = (
        (("invalidcredential", "invalid credentials"), "bind_failed", "Directory credentials were rejected.", False),
        (("insufficientaccess", "insufficient access"), "access_denied", "Directory permissions are insufficient.", False),
        (("no such object", "nosuchobject"), "base_dn_not_found", "The configured directory base was not found.", False),
        (("certificate", "hostname mismatch"), "certificate_invalid", "The directory certificate could not be validated.", False),
        (("tls", "ssl"), "tls_failed", "The secure LDAP handshake failed.", False),
        (("time limit", "timeout", "timed out"), "timeout", "The directory operation timed out.", True),
        (("socket", "connection refused", "unreachable", "name or service"), "host_unreachable", "The directory server could not be reached.", True),
    )
    for needles, category, message, retryable in mapping:
        if any(needle in text for needle in needles):
            return LdapError(category, message, retryable=retryable)
    return LdapError("unknown_error", "The directory operation failed.")


class LdapClientInterface(ABC):
    @abstractmethod
    def test_connection(self) -> dict[str, Any]: ...

    @abstractmethod
    def bind(self, bind_dn: str | None, password: str | None) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def get_root_dse(self) -> dict[str, Any]: ...

    @abstractmethod
    def validate_base_dn(self, base_dn: str) -> bool: ...

    @abstractmethod
    def search_users(self, base_dn: str, **kwargs) -> LdapSearchResult: ...

    @abstractmethod
    def search_computers(self, base_dn: str, **kwargs) -> LdapSearchResult: ...

    @abstractmethod
    def search_groups(self, base_dn: str, **kwargs) -> LdapSearchResult: ...

    @abstractmethod
    def search_by_dn(self, distinguished_name: str, attributes: tuple[str, ...]) -> dict[str, Any] | None: ...

    def unbind(self) -> None:
        self.close()


class SecureLdapClient(LdapClientInterface):
    def __init__(
        self,
        config: LdapClientConfig,
        *,
        server_factory: Callable[..., Server] = Server,
        connection_factory: Callable[..., Connection] = Connection,
    ):
        self.config = config
        self.server_factory = server_factory
        self.connection_factory = connection_factory
        self.connection: Connection | None = None
        self._validate_configuration()

    def _validate_configuration(self) -> None:
        host = self.config.host.strip().lower()
        if "://" in host or "@" in host or any(char.isspace() for char in host):
            raise LdapError("configuration_error", "Directory server host is invalid.")
        approved = {item.casefold() for item in self.config.approved_hosts}
        domain_aligned = host == self.config.domain_name.casefold() or host.endswith(
            "." + self.config.domain_name.casefold()
        )
        try:
            address = ipaddress.ip_address(host)
            safe_address = address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            safe_address = domain_aligned
        if not self.config.allow_public_hosts and not safe_address and host not in approved:
            raise LdapError("configuration_error", "Directory server is outside the approved host policy.")
        if not self.config.use_ssl and not self.config.use_start_tls:
            if self.config.environment != "development" or not self.config.allow_insecure_ldap:
                raise LdapError("configuration_error", "Plain LDAP is allowed only by explicit development policy.")
        if not self.config.verify_tls and self.config.environment != "development":
            raise LdapError("configuration_error", "TLS verification cannot be disabled outside development.")
        if self.config.page_size < 1 or self.config.page_size > self.config.maximum_page_size:
            raise LdapError("configuration_error", "LDAP page size exceeds the configured limit.")
        if self.config.ca_certificate_reference:
            ca_path = Path(self.config.ca_certificate_reference).expanduser()
            if not ca_path.is_file():
                raise LdapError("configuration_error", "Configured LDAP CA certificate was not found.")

    def _tls(self) -> Tls | None:
        if not (self.config.use_ssl or self.config.use_start_tls):
            return None
        validate = ssl.CERT_REQUIRED if self.config.verify_tls else ssl.CERT_NONE
        return Tls(
            validate=validate,
            ca_certs_file=self.config.ca_certificate_reference,
            version=ssl.PROTOCOL_TLS_CLIENT,
        )

    def bind(self, bind_dn: str | None, password: str | None) -> None:
        authentication = ANONYMOUS if self.config.authentication_method == "anonymous" else SIMPLE
        attempts = max(1, min(self.config.retry_count + 1, 3))
        last_error: LdapError | None = None
        for attempt in range(attempts):
            try:
                server = self.server_factory(
                    self.config.host,
                    port=self.config.port,
                    use_ssl=self.config.use_ssl,
                    tls=self._tls(),
                    connect_timeout=self.config.connect_timeout,
                    get_info=ALL,
                )
                connection = self.connection_factory(
                    server,
                    user=bind_dn,
                    password=password,
                    authentication=authentication,
                    auto_bind=NONE,
                    receive_timeout=self.config.search_timeout,
                    raise_exceptions=True,
                )
                connection.open()
                if self.config.use_start_tls and not connection.start_tls():
                    raise LdapError("tls_failed", "The secure LDAP handshake failed.")
                if not connection.bind():
                    raise classify_ldap_error(connection.result)
                self.connection = connection
                return
            except LdapError as error:
                last_error = error
            except (LDAPException, OSError, socket.error) as error:
                last_error = classify_ldap_error(error)
            if last_error and (not last_error.retryable or attempt == attempts - 1):
                break
            time.sleep(0.05 * (attempt + 1))
        raise last_error or LdapError("unknown_error", "The directory bind failed.")

    def close(self) -> None:
        if self.connection is not None:
            try:
                self.connection.unbind()
            finally:
                if hasattr(self.connection, "password"):
                    self.connection.password = None
                self.connection = None

    def _require_connection(self) -> Connection:
        if self.connection is None:
            raise LdapError("configuration_error", "Directory client is not bound.")
        return self.connection

    def get_root_dse(self) -> dict[str, Any]:
        connection = self._require_connection()
        try:
            connection.search("", "(objectClass=*)", BASE, attributes=list(ROOT_DSE_ATTRIBUTES), time_limit=self.config.search_timeout)
            if not connection.entries:
                raise LdapError("malformed_response", "Directory RootDSE response was empty.")
            values = connection.entries[0].entry_attributes_as_dict
            safe = {key: values.get(key) for key in ROOT_DSE_ATTRIBUTES}
            versions = [str(item) for item in (safe.get("supportedLDAPVersion") or [])]
            safe["appears_active_directory"] = bool(safe.get("defaultNamingContext") and safe.get("configurationNamingContext"))
            safe["ldap_v3_supported"] = "3" in versions
            return safe
        except LdapError:
            raise
        except (LDAPException, OSError) as error:
            raise classify_ldap_error(error) from error

    def validate_base_dn(self, base_dn: str) -> bool:
        if not validate_dn_syntax(base_dn):
            raise LdapError("search_base_invalid", "Directory search base syntax is invalid.")
        connection = self._require_connection()
        try:
            connection.search(base_dn, "(objectClass=*)", BASE, attributes=["distinguishedName"], size_limit=1, time_limit=self.config.search_timeout)
            return bool(connection.entries)
        except (LDAPException, OSError) as error:
            classified = classify_ldap_error(error)
            if classified.category == "base_dn_not_found":
                return False
            raise classified from error

    def search_by_dn(self, distinguished_name: str, attributes: tuple[str, ...]) -> dict[str, Any] | None:
        if not validate_dn_syntax(distinguished_name):
            raise LdapError("search_base_invalid", "Directory object DN syntax is invalid.")
        disallowed = set(attributes) - set(USER_ATTRIBUTES) - set(COMPUTER_ATTRIBUTES) - set(GROUP_ATTRIBUTES)
        if disallowed:
            raise LdapError("configuration_error", "One or more requested attributes are not allowed.")
        connection = self._require_connection()
        try:
            connection.search(distinguished_name, "(objectClass=*)", BASE, attributes=list(attributes), size_limit=1, time_limit=self.config.search_timeout)
            return connection.entries[0].entry_attributes_as_dict if connection.entries else None
        except (LDAPException, OSError) as error:
            classified = classify_ldap_error(error)
            if classified.category == "unknown_error":
                classified = LdapError("query_failed", "The directory query failed.")
            raise classified from error

    def _search(
        self,
        object_type: str,
        base_dn: str,
        attributes: tuple[str, ...],
        *,
        search_term: str | None = None,
        enabled: bool | None = None,
        limit: int | None = None,
        include_members: bool = False,
        member_limit: int = 100,
    ) -> LdapSearchResult:
        if not validate_dn_syntax(base_dn):
            raise LdapError("search_base_invalid", "Directory search base syntax is invalid.")
        connection = self._require_connection()
        maximum = min(limit or self.config.maximum_objects, self.config.maximum_objects)
        page_size = min(self.config.page_size, self.config.maximum_page_size, maximum)
        query_attributes = list(attributes)
        if object_type == "group" and include_members:
            query_attributes.append("member")
        filter_value = build_search_filter(object_type, search_term=search_term, enabled=enabled)
        items: list[dict[str, Any]] = []
        cookie: bytes | str | None = None
        pages = 0
        seen_cookies: set[bytes | str] = set()
        try:
            while len(items) < maximum:
                connection.search(
                    base_dn,
                    filter_value,
                    SUBTREE,
                    attributes=query_attributes,
                    paged_size=min(page_size, maximum - len(items)),
                    paged_cookie=cookie,
                    time_limit=self.config.search_timeout,
                )
                pages += 1
                for entry in connection.entries:
                    items.append(convert_entry(
                        object_type,
                        entry.entry_attributes_as_dict,
                        getattr(entry, "entry_raw_attributes", {}),
                        include_members=include_members,
                        member_limit=member_limit,
                    ))
                    if len(items) >= maximum:
                        break
                control = (connection.result.get("controls") or {}).get(PAGED_RESULTS_OID, {})
                next_cookie = (control.get("value") or {}).get("cookie")
                if not next_cookie:
                    cookie = None
                    break
                if next_cookie in seen_cookies:
                    raise LdapError("malformed_response", "Directory paging returned a repeated cookie.")
                seen_cookies.add(next_cookie)
                cookie = next_cookie
                if pages > max(2, (maximum // max(1, page_size)) + 2):
                    raise LdapError("page_limit_exceeded", "Directory paging exceeded the safe page limit.")
        except LdapError:
            raise
        except (LDAPException, OSError) as error:
            classified = classify_ldap_error(error)
            if classified.category == "unknown_error":
                classified = LdapError("query_failed", "The directory query failed.")
            raise classified from error
        truncated = len(items) >= maximum and bool(cookie)
        warnings = ["Result limit reached; additional directory objects were not returned."] if truncated else []
        return LdapSearchResult(items=items, truncated=truncated, page_count=pages, warnings=warnings)

    def search_users(self, base_dn: str, **kwargs) -> LdapSearchResult:
        return self._search("user", base_dn, USER_ATTRIBUTES, **kwargs)

    def search_computers(self, base_dn: str, **kwargs) -> LdapSearchResult:
        return self._search("computer", base_dn, COMPUTER_ATTRIBUTES, **kwargs)

    def search_groups(self, base_dn: str, **kwargs) -> LdapSearchResult:
        return self._search("group", base_dn, GROUP_ATTRIBUTES, **kwargs)

    def test_connection(self) -> dict[str, Any]:
        root = self.get_root_dse()
        return {
            "success": bool(root.get("ldap_v3_supported")),
            "message": "Directory connection and RootDSE query succeeded.",
            "root_dse": root,
        }


class MockLdapClient(LdapClientInterface):
    """Offline client used exclusively by automated tests and explicit dependency injection."""

    def __init__(self, host: str = "localhost", port: int = 389, use_ssl: bool = False):
        self.host, self.port, self.use_ssl = host, port, use_ssl
        self.bound = False

    def bind(self, bind_dn: str | None, password: str | None) -> None:
        self.bound = True

    def close(self) -> None:
        self.bound = False

    def get_root_dse(self) -> dict[str, Any]:
        return {
            "defaultNamingContext": ["DC=example,DC=invalid"],
            "rootDomainNamingContext": ["DC=example,DC=invalid"],
            "configurationNamingContext": ["CN=Configuration,DC=example,DC=invalid"],
            "schemaNamingContext": ["CN=Schema,CN=Configuration,DC=example,DC=invalid"],
            "supportedLDAPVersion": ["3"],
            "supportedSASLMechanisms": [],
            "dnsHostName": ["dc.example.invalid"],
            "serverName": [],
            "appears_active_directory": True,
            "ldap_v3_supported": True,
        }

    def validate_base_dn(self, base_dn: str) -> bool:
        return validate_dn_syntax(base_dn)

    def search_users(self, base_dn: str, **kwargs) -> LdapSearchResult:
        return LdapSearchResult([], False, 1)

    def search_computers(self, base_dn: str, **kwargs) -> LdapSearchResult:
        return LdapSearchResult([], False, 1)

    def search_groups(self, base_dn: str, **kwargs) -> LdapSearchResult:
        return LdapSearchResult([], False, 1)

    def search_by_dn(self, distinguished_name: str, attributes: tuple[str, ...]) -> dict[str, Any] | None:
        return None

    def test_connection(self) -> dict[str, Any]:
        return {"success": True, "message": "Mock-only LDAP test succeeded.", "root_dse": self.get_root_dse()}
