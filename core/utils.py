import time
from django_redis import get_redis_connection


class CircuitBreaker:
    def __init__(self, service_name, failure_threshold=10, recovery_timeout=60):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.redis = get_redis_connection("default")

    @property
    def _fail_key(self):
        return f"circuit_breaker:{self.service_name}:failures"

    @property
    def _state_key(self):
        return f"circuit_breaker:{self.service_name}:open"

    def is_open(self):
        return self.redis.exists(self._state_key)

    def record_failure(self):
        failures = self.redis.incr(self._fail_key)
        self.redis.expire(self._fail_key, self.recovery_timeout * 2)

        if failures >= self.failure_threshold:
            self.open_circuit()

    def record_success(self):
        self.redis.delete(self._fail_key)

    def open_circuit(self):
        self.redis.setex(self._state_key, self.recovery_timeout, "1")
        print(f"⚠️ Circuit Breaker OPEN for {self.service_name}")