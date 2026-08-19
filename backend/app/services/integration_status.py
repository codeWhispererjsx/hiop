"""
Integration Status Tracking System

Tracks the health and status of external integrations for HIOP.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, update


class IntegrationStatus(str, Enum):
    """Integration status levels"""
    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    REACHABLE = "reachable"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class IntegrationHealth:
    """Health status for an integration"""
    status: IntegrationStatus
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_test: Optional[datetime] = None
    error_count: int = 0
    consecutive_failures: int = 0
    last_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IntegrationStatusTracker:
    """
    Tracks integration health and status.
    
    Provides centralized status tracking for all external integrations
    with support for history and error counting.
    """
    
    def __init__(self):
        self._integrations: Dict[str, IntegrationHealth] = {}
    
    def register_integration(self, name: str, initial_status: IntegrationStatus = IntegrationStatus.NOT_CONFIGURED):
        """Register a new integration for tracking"""
        if name not in self._integrations:
            self._integrations[name] = IntegrationHealth(status=initial_status)
    
    def record_success(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        """Record a successful operation for an integration"""
        if name not in self._integrations:
            self.register_integration(name)
        
        health = self._integrations[name]
        health.last_success = datetime.now()
        health.consecutive_failures = 0
        health.last_error = None
        
        if metadata:
            health.metadata.update(metadata)
        
        # Update status based on consecutive successes
        if health.status in [IntegrationStatus.FAILED, IntegrationStatus.DEGRADED]:
            health.status = IntegrationStatus.REACHABLE
        elif health.status == IntegrationStatus.CONFIGURED:
            health.status = IntegrationStatus.REACHABLE
    
    def record_failure(self, name: str, error: str, metadata: Optional[Dict[str, Any]] = None):
        """Record a failed operation for an integration"""
        if name not in self._integrations:
            self.register_integration(name)
        
        health = self._integrations[name]
        health.last_failure = datetime.now()
        health.error_count += 1
        health.consecutive_failures += 1
        health.last_error = error
        
        if metadata:
            health.metadata.update(metadata)
        
        # Update status based on consecutive failures
        if health.consecutive_failures >= 3:
            health.status = IntegrationStatus.FAILED
        elif health.consecutive_failures >= 1:
            health.status = IntegrationStatus.DEGRADED
    
    def record_test(self, name: str, success: bool, error: Optional[str] = None):
        """Record a configuration test result"""
        if name not in self._integrations:
            self.register_integration(name)
        
        health = self._integrations[name]
        health.last_test = datetime.now()
        
        if success:
            health.status = IntegrationStatus.REACHABLE
            health.consecutive_failures = 0
            health.last_error = None
        else:
            health.status = IntegrationStatus.FAILED
            health.last_error = error
            health.consecutive_failures += 1
    
    def mark_configured(self, name: str):
        """Mark an integration as configured"""
        if name not in self._integrations:
            self.register_integration(name)
        
        self._integrations[name].status = IntegrationStatus.CONFIGURED
    
    def mark_not_configured(self, name: str):
        """Mark an integration as not configured"""
        if name not in self._integrations:
            self.register_integration(name)
        
        self._integrations[name].status = IntegrationStatus.NOT_CONFIGURED
    
    def get_status(self, name: str) -> Optional[IntegrationHealth]:
        """Get the current health status of an integration"""
        return self._integrations.get(name)
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all tracked integrations"""
        result = {}
        for name, health in self._integrations.items():
            result[name] = {
                "status": health.status.value,
                "last_success": health.last_success.isoformat() if health.last_success else None,
                "last_failure": health.last_failure.isoformat() if health.last_failure else None,
                "last_test": health.last_test.isoformat() if health.last_test else None,
                "error_count": health.error_count,
                "consecutive_failures": health.consecutive_failures,
                "last_error": health.last_error,
                "metadata": health.metadata,
            }
        return result
    
    def reset_integration(self, name: str):
        """Reset an integration's health status"""
        if name in self._integrations:
            self._integrations[name] = IntegrationHealth(status=IntegrationStatus.NOT_CONFIGURED)


# Global integration status tracker
_integration_tracker = IntegrationStatusTracker()


def get_integration_tracker() -> IntegrationStatusTracker:
    """Get the global integration status tracker"""
    return _integration_tracker


# Initialize known integrations
def initialize_integrations():
    """Initialize the integration tracker with known integrations"""
    tracker = get_integration_tracker()
    
    known_integrations = [
        "dns",
        "dhcp",
        "snmp",
        "active_directory",
        "smtp",
        "agent",
        "discovery",
        "monitoring",
    ]
    
    for integration in known_integrations:
        tracker.register_integration(integration)