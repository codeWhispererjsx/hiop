"""
Integration History Tracking System

Tracks historical data for external integrations including success/failure patterns.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, desc


class IntegrationEventType(str, Enum):
    """Types of integration events"""
    SUCCESS = "success"
    FAILURE = "failure"
    TEST = "test"
    CONFIGURATION_CHANGE = "configuration_change"
    TIMEOUT = "timeout"
    DEGRADED = "degraded"


@dataclass
class IntegrationEvent:
    """An integration event for historical tracking"""
    integration_name: str
    event_type: IntegrationEventType
    timestamp: datetime
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    organization_id: Optional[str] = None
    property_id: Optional[str] = None


class IntegrationHistoryTracker:
    """
    Tracks historical events for integrations.
    
    Provides historical analysis and pattern detection for integration reliability.
    """
    
    def __init__(self, max_events_per_integration: int = 1000):
        self._events: List[IntegrationEvent] = []
        self._max_events = max_events_per_integration
    
    def record_event(self, event: IntegrationEvent):
        """Record an integration event"""
        self._events.append(event)
        
        # Prune old events if we exceed the limit
        self._prune_events()
    
    def _prune_events(self):
        """Remove old events to prevent memory issues"""
        integration_counts: Dict[str, int] = {}
        events_to_keep: List[IntegrationEvent] = []
        
        # Count events per integration
        for event in self._events:
            integration_counts[event.integration_name] = integration_counts.get(event.integration_name, 0) + 1
        
        # Keep only the most recent events per integration
        for event in reversed(self._events):
            if integration_counts[event.integration_name] > self._max_events:
                integration_counts[event.integration_name] -= 1
            else:
                events_to_keep.append(event)
        
        self._events = list(reversed(events_to_keep))
    
    def get_events(
        self,
        integration_name: Optional[str] = None,
        event_type: Optional[IntegrationEventType] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[IntegrationEvent]:
        """Get integration events with optional filtering"""
        events = self._events
        
        if integration_name:
            events = [e for e in events if e.integration_name == integration_name]
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if since:
            events = [e for e in events if e.timestamp >= since]
        
        # Return most recent events first
        events = sorted(events, key=lambda e: e.timestamp, reverse=True)
        
        return events[:limit]
    
    def get_success_rate(
        self,
        integration_name: str,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Calculate success rate for an integration"""
        events = self.get_events(integration_name, since=since)
        
        if not events:
            return {
                "success_rate": 0.0,
                "total_events": 0,
                "successes": 0,
                "failures": 0,
            }
        
        successes = sum(1 for e in events if e.event_type == IntegrationEventType.SUCCESS)
        failures = sum(1 for e in events if e.event_type == IntegrationEventType.FAILURE)
        
        return {
            "success_rate": successes / len(events) if events else 0.0,
            "total_events": len(events),
            "successes": successes,
            "failures": failures,
        }
    
    def get_failure_patterns(
        self,
        integration_name: str,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Analyze failure patterns for an integration"""
        events = self.get_events(integration_name, event_type=IntegrationEventType.FAILURE, since=since)
        
        patterns = []
        error_counts: Dict[str, int] = {}
        
        for event in events:
            if event.error_message:
                error_counts[event.error_message] = error_counts.get(event.error_message, 0) + 1
        
        for error, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True):
            patterns.append({
                "error": error,
                "count": count,
                "percentage": count / len(events) if events else 0.0,
            })
        
        return patterns
    
    def get_uptime(
        self,
        integration_name: str,
        since: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Calculate uptime percentage for an integration"""
        events = self.get_events(integration_name, since=since)
        
        if not events:
            return {
                "uptime_percentage": 0.0,
                "total_time_ms": 0.0,
                "downtime_ms": 0.0,
            }
        
        # Simple uptime calculation based on success rate
        success_rate = self.get_success_rate(integration_name, since)
        
        return {
            "uptime_percentage": success_rate["success_rate"] * 100,
            "total_events": success_rate["total_events"],
            "successes": success_rate["successes"],
            "failures": success_rate["failures"],
        }


# Global integration history tracker
_history_tracker = IntegrationHistoryTracker()


def get_history_tracker() -> IntegrationHistoryTracker:
    """Get the global integration history tracker"""
    return _history_tracker