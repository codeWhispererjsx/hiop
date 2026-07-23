from abc import ABC, abstractmethod
from typing import Any


class LdapClientInterface(ABC):
    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Test LDAP connection parameters without persisting or querying live directories."""
        pass

    @abstractmethod
    def bind(self, bind_dn: str, password: str) -> bool:
        """Bind to LDAP server using credentials."""
        pass

    @abstractmethod
    def unbind(self) -> None:
        """Unbind and close LDAP connection."""
        pass

    @abstractmethod
    def search_users(self, base_dn: str, filter_str: str | None = None) -> list[dict[str, Any]]:
        """Search directory users."""
        pass

    @abstractmethod
    def search_computers(self, base_dn: str, filter_str: str | None = None) -> list[dict[str, Any]]:
        """Search directory computers."""
        pass

    @abstractmethod
    def search_groups(self, base_dn: str, filter_str: str | None = None) -> list[dict[str, Any]]:
        """Search directory groups."""
        pass

    @abstractmethod
    def get_root_dse(self) -> dict[str, Any]:
        """Get Root DSE metadata."""
        pass

    @abstractmethod
    def validate_base_dn(self, base_dn: str) -> bool:
        """Validate base DN syntax."""
        pass


class MockLdapClient(LdapClientInterface):
    """Mock LDAP client for Epic 3A architecture validation without live domain access."""

    def __init__(self, host: str = "localhost", port: int = 389, use_ssl: bool = False):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.bound = False

    def test_connection(self) -> dict[str, Any]:
        return {
            "success": True,
            "message": "Mock connection test successful (Epic 3A architectural stub mode).",
            "host": self.host,
            "port": self.port,
            "use_ssl": self.use_ssl,
        }

    def bind(self, bind_dn: str, password: str) -> bool:
        self.bound = True
        return True

    def unbind(self) -> None:
        self.bound = False

    def search_users(self, base_dn: str, filter_str: str | None = None) -> list[dict[str, Any]]:
        return []

    def search_computers(self, base_dn: str, filter_str: str | None = None) -> list[dict[str, Any]]:
        return []

    def search_groups(self, base_dn: str, filter_str: str | None = None) -> list[dict[str, Any]]:
        return []

    def get_root_dse(self) -> dict[str, Any]:
        return {
            "defaultNamingContext": "DC=hotel,DC=internal",
            "supportedLDAPVersion": ["3"],
            "vendorName": "Microsoft Corporation",
        }

    def validate_base_dn(self, base_dn: str) -> bool:
        if not base_dn or not isinstance(base_dn, str):
            return False
        parts = [part.strip() for part in base_dn.split(",")]
        return len(parts) >= 1 and all("=" in part for part in parts)
