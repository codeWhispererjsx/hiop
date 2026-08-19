"""
Circuit Breaker Pattern Implementation for HIOP Integrations

Provides simple circuit-breaker behavior to prevent hammering failing external systems.
"""
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Optional
from functools import wraps


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if system has recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5          # Number of failures before opening
    recovery_timeout: int = 60           # Seconds to wait before attempting recovery
    success_threshold: int = 2           # Number of successes needed to close circuit
    timeout: float = 30.0                # Individual operation timeout


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_calls: int = 0


class CircuitBreakerError(Exception):
    """Circuit breaker is open"""
    def __init__(self, message: str, stats: CircuitBreakerStats):
        super().__init__(message)
        self.stats = stats


class CircuitBreaker:
    """
    Simple circuit breaker implementation for external integrations.
    
    Prevents hammering failing systems by:
    - Opening circuit after threshold failures
    - Waiting before attempting recovery
    - Closing circuit after successful recovery
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._last_state_change = datetime.now()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.state != CircuitState.OPEN:
            return False
        
        if self.stats.last_failure_time is None:
            return True
        
        time_since_failure = datetime.now() - self.stats.last_failure_time
        return time_since_failure.total_seconds() >= self.config.recovery_timeout
    
    def _record_success(self):
        """Record a successful operation"""
        self.stats.successes += 1
        self.stats.consecutive_successes += 1
        self.stats.consecutive_failures = 0
        self.stats.last_success_time = datetime.now()
        self.stats.total_calls += 1
        
        # If in half-open state, check if we should close
        if self.state == CircuitState.HALF_OPEN:
            if self.stats.consecutive_successes >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self._last_state_change = datetime.now()
    
    def _record_failure(self):
        """Record a failed operation"""
        self.stats.failures += 1
        self.stats.consecutive_failures += 1
        self.stats.consecutive_successes = 0
        self.stats.last_failure_time = datetime.now()
        self.stats.total_calls += 1
        
        # Check if we should open the circuit
        if self.stats.consecutive_failures >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            self._last_state_change = datetime.now()
    
    def call(self, func: Callable, *args, **kwargs):
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function return value
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: If function execution fails
        """
        # Check if circuit is open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self._last_state_change = datetime.now()
            else:
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is open. Too many failures.",
                    self.stats
                )
        
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise
    
    def get_state(self) -> dict:
        """Get current circuit breaker state and statistics"""
        return {
            "name": self.name,
            "state": self.state.value,
            "stats": {
                "failures": self.stats.failures,
                "successes": self.stats.successes,
                "consecutive_failures": self.stats.consecutive_failures,
                "consecutive_successes": self.stats.consecutive_successes,
                "total_calls": self.stats.total_calls,
                "last_failure_time": self.stats.last_failure_time.isoformat() if self.stats.last_failure_time else None,
                "last_success_time": self.stats.last_success_time.isoformat() if self.stats.last_success_time else None,
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "success_threshold": self.config.success_threshold,
            },
            "last_state_change": self._last_state_change.isoformat(),
        }
    
    def reset(self):
        """Manually reset the circuit breaker to closed state"""
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._last_state_change = datetime.now()


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create a circuit breaker for a given integration"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """
    Decorator to apply circuit breaker to a function.
    
    Usage:
        @circuit_breaker("snmp_polling", CircuitBreakerConfig(failure_threshold=3))
        def poll_snmp_device(device_id):
            # SNMP polling logic
            pass
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cb = get_circuit_breaker(name, config)
            return cb.call(func, *args, **kwargs)
        return wrapper
    return decorator


def get_all_circuit_breakers() -> dict[str, dict]:
    """Get state of all registered circuit breakers"""
    return {name: cb.get_state() for name, cb in _circuit_breakers.items()}


def reset_circuit_breaker(name: str):
    """Reset a specific circuit breaker"""
    if name in _circuit_breakers:
        _circuit_breakers[name].reset()