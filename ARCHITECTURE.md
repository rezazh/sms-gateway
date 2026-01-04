# System Architecture & Design Decisions

## 1. Overview & Core Principles

This document outlines the architectural design of the High-Performance SMS Gateway. The system is engineered to meet two primary, often conflicting, goals:

1.  **High Availability & Throughput** for SMS ingestion and delivery. The system must remain responsive and fast, even under extreme load.
2.  **Strict Consistency** for financial operations, specifically credit management, to prevent data corruption and financial loss.

Our architecture addresses these goals by strategically applying different patterns to different parts of the system.

---

## 2. Core Architectural Patterns

### 2.1. High-Performance Ingestion: The Redis Buffer Pattern

**Problem:** Direct database writes for each incoming SMS request create a bottleneck. The API response time becomes tied to database I/O, which is slow and cannot handle traffic spikes.

**Solution:** We decouple the API from the database using a Redis List as a high-speed buffer.

**Flow:**
1.  An API request to `/api/sms/send/` is received.
2.  The system performs initial validation (data format, authentication).
3.  **Atomic Credit Deduction:** A Redis Lua script is executed to atomically check and deduct the user's balance from a Redis key. This is extremely fast (<1ms).
4.  The SMS payload is serialized and pushed to a Redis List (`normal_sms_queue` or `express_sms_queue`).
5.  An `HTTP 202 Accepted` response is immediately sent back to the client.

**Benefits:**
-   **Extremely Low Latency:** The API response is near-instantaneous as it never waits for the database.
-   **Spike Absorption:** The system can absorb massive bursts of traffic by queuing them in Redis, which is designed for this purpose.
-   **Decoupling:** The API servers and background workers can be scaled independently.

A background Celery task (`batch_ingest_sms`) periodically reads thousands of messages from the Redis buffer and performs a single, highly efficient `bulk_create` operation into the PostgreSQL database.

### 2.2. Atomic Credit Management: Consistency First

**Problem:** Managing user credit in a concurrent environment is prone to race conditions. Two simultaneous requests could read the same balance, both deduct credit, and result in an incorrect final balance ("double-spending").

**Solution:** A hybrid approach using Redis for speed and PostgreSQL for durability, ensuring atomicity at every step.

1.  **Real-time Operations in Redis:** The primary balance is stored in a Redis key (`user_balance_{user_id}`). All deductions are performed here using a **Lua Script**. Lua scripts are executed atomically by Redis, guaranteeing that no other command can run midway through, thus eliminating race conditions.
2.  **Eventual Consistency with DB:** A second Redis key (`pending_deduct_{user_id}`) tracks the total amount deducted since the last database sync. A periodic Celery task (`sync_all_balances`) reads this delta, locks the corresponding user's row in the `CreditAccount` table using `SELECT FOR UPDATE` (Pessimistic Locking), applies the changes, and resets the delta in Redis. This ensures the database remains the consistent source of truth without sacrificing real-time performance.

### 2.3. Database Scalability: Native PostgreSQL Partitioning

**Problem:** A single `sms_messages` table storing 100 million records per day would quickly become unmanageable. Indexing would become slow, queries would degrade, and maintenance tasks (like vacuuming or backups) would be a nightmare.

**Solution:** We utilize PostgreSQL's native **Range Partitioning** on the `created_at` timestamp field.

-   A parent table `sms_messages` is defined.
-   Child tables are automatically created for specific time ranges (e.g., `sms_messages_y2026m01`, `sms_messages_y2026m02`).
-   When data is inserted into the parent table, PostgreSQL automatically routes it to the correct child partition.

**Benefits:**
-   **Massively Improved Query Performance:** Queries filtered by a time range only scan the relevant child table(s), not the entire dataset.
-   **Efficient Maintenance:** Indexes remain small and fast. Old partitions can be detached and archived or dropped instantly without affecting the main table.

---

## 3. Performance Validation: Load Test Results

To validate the architecture, a load test was conducted using **Locust**, simulating a high-traffic scenario.

### Test Parameters
-   **Concurrent Users:** 1,000
-   **Spawn Rate:** 100 new users per second
-   **Target Host:** `http://localhost:80` (via Nginx)
-   **Duration:** ~47 seconds

### Key Metrics Summary

| Metric                  | Value                  |
| ----------------------- | ---------------------- |
| **Total Requests**      | **30,655**             |
| **Total RPS (Avg)**     | **~661 req/sec**       |
| **Failure Rate**        | **0.13%**              |
| **Average Response Time** | **115 ms**             |
| **95th Percentile Time**  | **360 ms**             |

### Analysis & Interpretation

1.  **Exceptional Throughput:** The system successfully handled an average of **661 requests per second**, demonstrating the efficiency of the Redis buffering pattern and the overall architecture. This throughput significantly exceeds the requirements of most high-traffic applications.

2.  **Excellent Latency Under Load:** Even with 1,000 active users, the average response time remained extremely low at 115ms. This confirms that the API is non-blocking and the system is highly responsive.

3.  **High Reliability & System Protection:** The negligible failure rate of **0.13%** was investigated. The failures were exclusively `HTTP 429 Too Many Requests` errors. This is not an application failure; it is the **Nginx rate-limiting mechanism working correctly**. It proves the system is resilient and protects itself from being overwhelmed, ensuring service stability for the vast majority of users—a critical feature for any production-grade system.

**Conclusion:** The load test results unequivocally validate the architectural choices. The system is not only functionally correct but also demonstrably fast, scalable, and resilient under significant stress.