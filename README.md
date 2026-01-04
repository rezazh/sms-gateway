# High-Performance SMS Gateway

A scalable, production-ready SMS Gateway designed to handle high-throughput traffic (100M+ messages/day). Built with a focus on high availability, consistency, and resilience using Django, Celery, Redis, and PostgreSQL Partitioning.

This project demonstrates a complete, end-to-end solution for a real-world engineering challenge, including architectural design, implementation, comprehensive testing, and performance validation.

**For a deep dive into the design decisions, architectural patterns, and performance analysis, please read the [ARCHITECTURE.md](ARCHITECTURE.md) document.**

---

## 🚀 Key Features

-   **High Throughput Ingestion:** Non-blocking API using a Redis buffer pattern to handle traffic bursts with response times under 120ms.
-   **Atomic Credit Management:** Concurrency-safe balance deduction using Redis Lua scripts to prevent race conditions.
-   **Database Partitioning:** Native PostgreSQL partitioning by year for long-term scalability and efficient queries.
-   **Priority Queues:** Dedicated processing channels for `Normal` and `Express` (e.g., OTP) messages.
-   **System Resilience:**
    -   **Idempotency:** Safe handling of duplicate requests via `X-Request-ID`.
    -   **Rate Limiting:** Nginx layer protection against DoS attacks and abusive clients.
    -   **Circuit Breaker:** Prevents cascading failures when communicating with external providers.
-   **Monitoring:** Health checks and metrics endpoints ready for Prometheus/Grafana integration.

## 🛠 Tech Stack

-   **Backend:** Python 3.10, Django 5.0, Django Rest Framework
-   **Database:** PostgreSQL 15 (with native partitioning)
-   **Cache & Message Broker:** Redis 7
-   **Asynchronous Tasks:** Celery 5.3
-   **Web/Proxy Server:** Nginx with Gunicorn
-   **Containerization:** Docker & Docker Compose
-   **Testing:** Pytest, Locust

---

## 📦 Quick Start Guide

### Prerequisites

-   Docker & Docker Compose

### 1. Setup & Run

Clone the repository and run the entire stack using Docker Compose.

```bash
# Clone the repository
git clone <your-repo-url>
cd <project-folder>

# Copy the environment file
cp .env.example .env

# Build and start all services in the background
docker-compose up -d --build
```

### 2. Initialize Database

Run database migrations and seed it with test users (`heavy_user` with high credit and `normal_user`).

```bash
# Apply database migrations
docker-compose exec web python manage.py migrate

# Seed the database with test data
docker-compose exec web python manage.py seed_data
```

### 3. Run Automated Tests

Execute the comprehensive test suite, which covers business logic, concurrency, and partitioning.

```bash
docker-compose exec web pytest
```

---

## 📖 API Documentation & Usage

Interactive Swagger UI is available at:
-   **URL:** `http://localhost/api/docs/`

### Authentication

The API uses API Key authentication.

1.  **Get an API Key** (after running the `seed_data` command):
    ```bash
    docker-compose exec web python manage.py shell -c "from apps.accounts.models import User; print(f'API Key for heavy_user: {User.objects.get(username=\'heavy_user\').api_key}')"
    ```
2.  Include the key in your request headers:
    -   `X-API-KEY: <YOUR_KEY>`

---

## 📊 Monitoring

-   **Health Check:** `http://localhost/health/` (Verifies DB, Redis, Celery connectivity)
-   **Metrics:** `http://localhost/metrics` (Prometheus-compatible format)