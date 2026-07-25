"""SNMP client contract only; live transport is deliberately unavailable in Epic 4A."""
from abc import ABC, abstractmethod


class SNMPTransportUnavailable(RuntimeError):
    pass


class SNMPClient(ABC):
    @abstractmethod
    def test_target(self): ...
    @abstractmethod
    def get(self, oid: str): ...
    @abstractmethod
    def get_many(self, oids: list[str]): ...
    @abstractmethod
    def walk(self, oid: str): ...
    @abstractmethod
    def bulk_walk(self, oid: str): ...
    @abstractmethod
    def get_system_identity(self): ...
    @abstractmethod
    def get_interfaces(self): ...
    @abstractmethod
    def close(self): ...


class DisabledSNMPClient(SNMPClient):
    def _disabled(self):
        raise SNMPTransportUnavailable("Live SNMP transport is not available in Epic 4A.")
    test_target = get = get_many = walk = bulk_walk = get_system_identity = get_interfaces = close = lambda self, *args, **kwargs: self._disabled()
