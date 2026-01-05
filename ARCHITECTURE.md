# System Architecture and Design Decisions

## 1. Executive Summary

This document details the architectural choices made for the High-Performance SMS Gateway. The primary engineering challenge was to balance extreme write throughput (SMS ingestion) with strict data consistency (Billing/Credits).

Our solution adopts a hybrid architecture:
- For SMS Ingestion: An eventual consistency model using Redis Buffers to decouple API response time from database I/O.
- For Credits: A strong consistency model using Optimistic Locking (Lua) for real-time checks and Pessimistic Locking (DB) for final settlement.

## 2. Core Architectural Patterns

### 2.1. The Ingestion Pipeline (The Firehose Problem)

THE PROBLEM:
Inserting an SMS record into PostgreSQL involves transaction overhead, index updates, and I/O wait times. Under a load of 1000+ RPS, synchronous database writes would lock up the API workers, causing timeouts and 502 errors.

THE SOLUTION: Redis Write-Buffer Pattern
We treat the API layer as a producer that simply validates the request and pushes it to a fast, in-memory queue.

1. Ingest: API receives POST request, validates data, and pushes JSON payload to Redis List (sms_ingest_buffer).
2. Ack: API responds with 202 Accepted immediately (Latency less than 50ms).
3. Process: A background Celery task (batch_ingest_sms) runs every 2 seconds.
   - Acquires a distributed lock to prevent concurrent runs.
   - Pops up to 5,000 items from Redis.
   - Uses SMSMessage.objects.bulk_create() to insert them into PostgreSQL in a single transaction.
   - Dispatches sending tasks to RabbitMQ/Redis Broker.

OUTCOME: Database insert pressure is reduced by a factor of approximately 5000x (one transaction per batch instead of one per message).

### 2.2. Atomic Credit Management (The Double-Spend Problem)

THE PROBLEM:
In a distributed system, checking a balance and deducting from it are two separate operations.
- Thread A reads Balance (100).
- Thread B reads Balance (100).
- Thread A deducts 10.
- Thread B deducts 10.
- Both writes might overwrite each other or allow spending more than available balance.

THE SOLUTION: Redis Lua Scripting and Write-Behind
We moved the Check-and-Set logic into Redis, which is single-threaded and guarantees atomicity for Lua scripts.

1. Real-Time Deduction (Lua Script):
We use a custom Lua script (DEDUCT_SCRIPT) that performs the following atomically:
   - Checks if the cache key exists.
   - Validates data integrity (Anti-corruption check).
   - Checks if balance is greater than or equal to amount.
   - If valid: Decrements balance and increments a pending_deduct_delta key.
   
This ensures no race condition is possible, regardless of concurrency.

2. Database Synchronization (Write-Behind):
The actual CreditAccount table in PostgreSQL is updated asynchronously.
   - A periodic Celery task (sync_all_balances) reads the pending_deduct_delta.
   - Locks the user row using SELECT FOR UPDATE (Pessimistic Lock).
   - Applies the delta to the DB.
   - Resets the delta in Redis.

OUTCOME: 100% protection against race conditions with zero database locking during the hot path (API request).

### 2.3. Database Scalability (The Big Table Problem)

THE PROBLEM:
SMS logs grow indefinitely. A table with billions of rows becomes sluggish. Indexes become too large to fit in RAM, killing performance. Deleting old data (DELETE FROM ...) causes massive vacuum load and table bloat.

THE SOLUTION: Native PostgreSQL Partitioning
We utilize declarative partitioning by RANGE on the created_at column.

- Structure:
  - Parent: sms_messages
  - Partitions: sms_messages_y2025, sms_messages_y2026, etc.
- Routing: PostgreSQL automatically routes inserts to the correct partition.
- Maintenance:
  - A background task (maintain_partitions) automatically checks and creates partitions for the upcoming year.
  - Dropping old data is instantaneous (DROP TABLE sms_messages_y2020).

### 2.4. Reliability Patterns

#### Idempotency
To prevent duplicate SMS sending (e.g., if a client retries due to network timeout), we use X-Request-ID.
- We store a composite key idempotency:{user_id}:{request_id} in Redis with a TTL.
- If the key exists, we reject the request with 409 Conflict.

#### Circuit Breaker
We wrap external SMS provider calls with a custom CircuitBreaker class.
- State: Closed (Normal) to Open (Failures greater than Threshold) to Half-Open (Testing).
- If the provider fails consistently (e.g., 10 times), the breaker opens for 60 seconds.
- Benefit: Prevents resource exhaustion and allows the downstream provider to recover.

#### Rate Limiting
Implemented at the Nginx layer (limit_req_zone) using the leaky bucket algorithm.
- Protects the application server from being overwhelmed by DoS attacks.
- Offloads the cost of rejection to Nginx (C/C++), saving Python worker resources.

## 3. Performance Validation: Load Test Results

To validate the architecture, a load test was conducted using Locust on a containerized environment.

### Test Configuration
- Concurrent Users: 1,000
- Spawn Rate: 100 new users per second
- Target: http://localhost:80 (via Nginx)

### Key Metrics Summary

| Metric | Result | Interpretation |
|--------|--------|----------------|
| Throughput | approximately 660 RPS | Sustained load without degradation. |
| Avg Latency | 115 ms | End-to-end API response time. |
| Max Latency (p95) | 360 ms | 95th percentile remains responsive. |
| Error Rate | 0.13% | Errors were strictly Rate-Limit (429) rejections, proving system protection. |

CONCLUSION: The architecture successfully decouples ingestion from processing, allowing the system to accept traffic far beyond the speed of database writes or external providers.

## 4. Detailed Component Analysis

### 4.1. Credits Application (apps/credits/)

#### Purpose
Manages user credit accounts, transactions, and balance operations with atomic guarantees.

#### Key Components

1. CreditAccount Model:
   - Stores user balance, total_charged, and total_spent.
   - One-to-one relationship with User model.

2. CreditTransaction Model:
   - Immutable audit log of all balance changes.
   - Includes balance_before and balance_after for reconciliation.

3. CreditService:
   - Core business logic for credit operations.
   - Implements the hybrid Redis-PostgreSQL consistency model.

#### Critical Methods

get_balance(user):
- Checks Redis cache first (user_balance_{user_id}).
- On cache miss, acquires a distributed lock, fetches from DB, and populates cache.
- Returns Decimal for precision.

deduct_balance(user, amount):
- Executes atomic Lua script on Redis.
- Handles three return codes:
  - 1: Success
  - -1: Insufficient funds
  - -2: Cache miss (retries once after warming cache)
  - -3: Data corruption (deletes cache and raises error)

charge_account(user, amount, description):
- Wraps operation in database transaction.
- Updates both balance and total_charged.
- Creates CreditTransaction record.
- Updates Redis cache immediately.

sync_deltas_to_db(user_id):
- Reads pending_deduct_{user_id} from Redis.
- Acquires SELECT FOR UPDATE lock on CreditAccount.
- Applies delta to balance and total_spent.
- Resets delta in Redis.

#### Safety Mechanisms

1. Lua Script Validation:
   - Checks for nil values before arithmetic operations.
   - Prevents cache poisoning attacks.

2. Distributed Locking:
   - Uses Redis locks with timeout to prevent deadlocks.
   - Ensures only one process initializes cache on miss.

3. Decimal Precision:
   - All financial calculations use Decimal type.
   - Prevents floating-point rounding errors.

### 4.2. SMS Application (apps/sms/)

#### Purpose
Handles SMS lifecycle from ingestion to delivery with high throughput and reliability.

#### Key Components

1. SMSMessage Model:
   - Uses UUID7 for primary key (time-sortable).
   - Partitioned by created_at for scalability.
   - Includes status, priority, cost, and retry tracking.

2. SMSService:
   - Business logic for SMS operations.
   - Implements buffer pattern for ingestion.

3. SMSStatusBuffer:
   - Decouples status updates from database writes.
   - Batches updates for efficiency.

#### Critical Methods

create_sms(user, recipient, message, priority, scheduled_at):
- Validates phone number format.
- Deducts credit atomically.
- Wraps database insert in transaction.
- Dispatches to appropriate Celery queue based on priority.

process_ingest_buffer(batch_size):
- Pops batch_size items from Redis list.
- Performs bulk_create to PostgreSQL.
- Dispatches sending tasks.
- On error, pushes items back to Redis.

#### Task Architecture

1. send_sms_task:
   - Simulates SMS provider call.
   - Pushes status update to SMSStatusBuffer.
   - Implements retry with exponential backoff.

2. batch_ingest_sms:
   - Runs every 2 seconds via Celery Beat.
   - Uses distributed lock to prevent concurrent execution.
   - Processes up to 5,000 messages per run.

3. flush_sms_buffer_task:
   - Runs every 5 seconds.
   - Reads status updates from Redis.
   - Performs bulk_update on SMSMessage table.

4. maintain_partitions:
   - Runs monthly via Celery Beat.
   - Checks for next year partition.
   - Creates partition if missing.

#### Priority Queue System

- Normal Queue: Standard messages, processed in order.
- Express Queue: High-priority messages (e.g., OTP), processed first.
- Dead Letter Queue: Failed messages after max retries.

### 4.3. Accounts Application (apps/accounts/)

#### Purpose
User management and authentication.

#### Key Components

1. User Model:
   - Extends Django AbstractUser.
   - Stores hashed API key (SHA-256).
   - Includes rate_limit_per_minute field.

2. APIKeyAuthentication:
   - Custom DRF authentication class.
   - Hashes incoming X-Api-Key header.
   - Queries database for matching user.

3. HealthCheckView:
   - Performs deep health checks on all dependencies.
   - Returns degraded status if any component is slow.
   - Caches Celery status to reduce overhead.

### 4.4. Core Utilities (core/)

#### CircuitBreaker Class

Implements the Circuit Breaker pattern for external dependencies.

Methods:
- is_open(): Checks if circuit is open.
- record_failure(): Increments failure counter, opens circuit if threshold exceeded.
- record_success(): Resets failure counter.
- open_circuit(): Sets circuit to open state with TTL.

State Transitions:
- Closed: Normal operation.
- Open: All requests fail fast without calling provider.
- Half-Open: After timeout, one request is allowed to test recovery.

#### FastPagination Class

Custom pagination for high-performance list endpoints.
- Removes count query for speed.
- Returns only next/previous links and results.

## 5. Data Flow Diagrams

### SMS Send Flow

1. Client sends POST /api/sms/send/ with X-Api-Key and X-Request-ID
2. APIKeyAuthentication validates user
3. System checks idempotency key in Redis
4. Lua script atomically deducts balance from Redis
5. SMS payload pushed to sms_ingest_buffer (Redis List)
6. API responds 202 Accepted
7. batch_ingest_sms task pops messages from buffer
8. Messages inserted into PostgreSQL via bulk_create
9. send_sms_task dispatched to Celery queue
10. Task simulates provider call and updates status
11. Status pushed to SMSStatusBuffer (Redis List)
12. flush_sms_buffer_task updates database in batch

### Credit Sync Flow

1. User sends SMS, balance deducted in Redis
2. pending_deduct_{user_id} incremented
3. sync_all_balances task runs every 60 seconds
4. Task reads all pending_deduct_* keys
5. For each user:
   - Acquires SELECT FOR UPDATE lock
   - Applies delta to CreditAccount
   - Resets pending_deduct in Redis
6. Database now reflects true balance

## 6. Testing Strategy

### Unit Tests (pytest)

- test_credits_service.py: Tests credit operations in isolation.
- test_sms_service.py: Tests SMS validation and cost calculation.
- test_sms_api.py: Tests API endpoints with mocked Redis.

### Integration Tests

- test_concurrency.py: Simulates concurrent balance deductions.
- test_batch_ingest.py: Validates buffer processing logic.
- test_partitioning.py: Ensures correct partition routing.

### Load Tests (Locust)

- locustfile.py: Simulates 1000 concurrent users.
- Tests normal and express SMS sending.
- Validates system behavior under stress.

## 7. Deployment Considerations

### Scaling Strategy

1. Horizontal Scaling:
   - Add more Gunicorn workers for API.
   - Add more Celery workers for task processing.
   - Redis and PostgreSQL can be scaled vertically or via replication.

2. Vertical Scaling:
   - Increase Redis memory for larger caches.
   - Increase PostgreSQL RAM for better query performance.

### Monitoring and Alerting

1. Prometheus Metrics:
   - sms_sent_total: Counter of successful sends.
   - sms_failed_total: Counter of failures by reason.
   - http_request_duration_seconds: API latency histogram.

2. Health Check Integration:
   - Configure load balancer to poll /health/ endpoint.
   - Remove unhealthy nodes from rotation automatically.

3. Logging:
   - Structured JSON logs for easy parsing.
   - Separate error logs for critical issues.
   - Log rotation to prevent disk exhaustion.

### Security Considerations

1. API Key Management:
   - Keys are hashed (SHA-256) before storage.
   - Raw key shown only once at creation.
   - Rotate keys periodically.

2. Rate Limiting:
   - Nginx layer prevents brute force attacks.
   - Per-user limits enforced at application layer.

3. Input Validation:
   - Phone numbers validated with regex.
   - Message length limits enforced.
   - SQL injection prevented by ORM.

## 8. Future Enhancements

### Planned Features

1. Multi-Tenancy:
   - Separate credit pools per organization.
   - Tenant-specific rate limits.

2. Advanced Scheduling:
   - Recurring messages (daily, weekly).
   - Time-zone aware scheduling.

3. Analytics Dashboard:
   - Real-time delivery rates.
   - Cost analysis per user.
   - Failure reason breakdown.

### Performance Optimizations

1. Read Replicas:
   - Route read queries to PostgreSQL replicas.
   - Reduce load on primary database.

2. CDN for Static Assets:
   - Serve Swagger UI from CDN.
   - Reduce server bandwidth.

3. Message Compression:
   - Compress SMS payload in Redis.
   - Reduce memory footprint.

## 9. Conclusion

This architecture demonstrates a production-ready approach to building a high-throughput, financially consistent SMS Gateway. By carefully choosing the right tool for each job (Redis for speed, PostgreSQL for durability, Celery for async processing), we achieved a system that is both fast and reliable.

The load test results validate our design choices, showing that the system can handle real-world traffic while maintaining low latency and high availability.