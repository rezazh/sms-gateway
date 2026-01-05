# High-Performance SMS Gateway

An enterprise-grade, high-throughput SMS Gateway designed to handle massive traffic bursts (100M+ messages/day) while maintaining strict financial consistency. This system leverages an event-driven architecture, in-memory buffering, and database partitioning to ensure scalability, reliability, and speed.

## Key Engineering Highlights

### High-Throughput Ingestion (The Buffer Pattern)
- Non-Blocking API: Decouples ingestion logic using Redis Lists as temporary write buffers. This allows the API to accept requests faster than the database can write.
- Performance: Capable of handling ~650+ RPS on a standard node with sub-120ms latency.
- Batch Processing: Background workers consume the buffer and perform efficient bulk_create operations to PostgreSQL (5,000 records per batch).

### Atomic Financial Consistency (The Hybrid Model)
- Race Condition Free: Utilizes Redis Lua Scripts for atomic balance checks and deductions, completely eliminating double-spending risks in concurrent environments.
- Write-Behind Consistency: Implements an eventual consistency model where credit deltas are synced to PostgreSQL asynchronously, preventing database lock contention during high traffic.

### Database Scalability (Partitioning)
- Native Partitioning: Implements PostgreSQL Range Partitioning on the sms_messages table (partitioned by year).
- Query Efficiency: Ensures indexes remain small and queries remain fast regardless of historical data volume.
- Automated Maintenance: Background tasks automatically provision future partitions.

### Resilience and Reliability
- Idempotency: Enforces strict idempotency using X-Request-ID and Redis keys to prevent duplicate processing.
- Circuit Breaker: Protects the system from cascading failures when upstream SMS providers are down or slow.
- Rate Limiting: Nginx-level protection using the leaky bucket algorithm against DDoS and abusive clients.
- Graceful Degradation: Automatic retry mechanisms with exponential backoff for transient failures.

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | Python 3.10, Django 5.0 | Core application logic and API |
| Database | PostgreSQL 15 | Persistent storage with Table Partitioning |
| Cache and Broker | Redis 7 | Hot storage for balances, task queues, and ingestion buffers |
| Async Tasks | Celery 5.3 | Background processing (Sending, Ingesting, Syncing) |
| Gateway | Nginx | Reverse proxy, static files, and rate limiting |
| Monitoring | Prometheus | Metrics collection (RPS, Latency, Error Rates) |
| Testing | Pytest, Locust | Unit testing, Integration testing, and Load testing |

## Quick Start Guide

### Prerequisites
- Docker Engine and Docker Compose

### 1. Installation and Execution
Clone the repository and start the full stack using Docker Compose.

git clone <your-repo-url>
cd <project-root>
cp .env.example .env
docker-compose up -d --build

### 2. Database Initialization and Seeding
Prepare the database with partitions and seed data for testing.

docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py seed_data

### 3. Verification and Testing
Run the comprehensive test suite to ensure system integrity.

docker-compose exec web pytest

## API Documentation

The system includes auto-generated Swagger/OpenAPI documentation.

- Swagger UI: http://localhost/api/docs/
- Redoc: http://localhost/api/schema/

### Authentication Flow
This API uses API Key Authentication.

1. Retrieve API Key:
After running seed_data, retrieve the key for the test user:

docker-compose exec web python manage.py shell -c "from apps.accounts.models import User; print(f'API Key: {User.objects.get(username=\"heavy_user\").api_key}')"

2. Make a Request:
Add the header X-Api-Key: <YOUR_KEY> to your requests.

## Monitoring and Health

- Health Check Endpoint: GET /health/
  Deep checks connectivity to DB, Redis, and Celery workers.
  Returns 200 OK (Healthy), 200 OK (Degraded), or 503 Service Unavailable.

- Prometheus Metrics: GET /metrics
  Exposes standard Django metrics plus Custom counters (e.g., sms_sent_total, sms_failed_total).

## Project Structure

apps/
  accounts/    # User management and Authentication
  credits/     # Wallet logic, Transactions and Lua Scripts
  sms/         # SMS logic, Tasks, Buffers and Partitioning
config/        # Project settings, Celery and ASGI config
core/          # Shared utilities (Circuit Breaker, Pagination)
nginx/         # Nginx configuration
tests/         # Pytest modules and Load tests

For a detailed breakdown of architectural decisions, please read ARCHITECTURE.md