from contextlib import contextmanager
from threading import BoundedSemaphore, Lock
from uuid import UUID

from app.core.config import settings
from app.services.snmp_client_service import SNMPClientError

_guard = Lock()
_active_targets: set[str] = set()
_active_credentials: set[str] = set()
_global = BoundedSemaphore(settings.snmp_poll_concurrency)


@contextmanager
def snmp_operation_lock(target_id: UUID | str, credential_id: UUID | str):
    target_key, credential_key = str(target_id), str(credential_id)
    if not _global.acquire(blocking=False):
        raise SNMPClientError("configuration_error", "Global SNMP concurrency limit is reached.")
    with _guard:
        if target_key in _active_targets or credential_key in _active_credentials:
            _global.release()
            raise SNMPClientError("configuration_error", "SNMP target or credential is already in use.")
        _active_targets.add(target_key)
        _active_credentials.add(credential_key)
    try:
        yield
    finally:
        with _guard:
            _active_targets.discard(target_key)
            _active_credentials.discard(credential_key)
        _global.release()


def target_active(target_id) -> bool:
    with _guard:
        return str(target_id) in _active_targets


def credential_active(credential_id) -> bool:
    with _guard:
        return str(credential_id) in _active_credentials
