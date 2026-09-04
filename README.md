# Order Processing System — Saga Pattern

A production-grade order processing system demonstrating distributed systems patterns:
- Saga Orchestration with compensating transactions
- Idempotency via Redis deduplication
- Optimistic concurrency control
- Outbox pattern for reliable event delivery
- Dead Letter Queue for failed events
- Daily reconciliation

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   API Layer  │────▶│  Application │────▶│    Domain       │
│  (FastAPI)   │     │   (Saga)     │     │  (Aggregates)   │
└─────────────┘     └──────────────┘     └─────────────────┘
                           │                     │
                    ┌──────┴──────┐       ┌─────┴──────┐
                    │ Infrastructure│      │   Events   │
                    │ (Redis, DB)  │       │  (Outbox)  │
                    └─────────────┘       └────────────┘
```

## Quick Start

```bash
# Start infrastructure
docker-compose up -d redis postgres

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start API
uvicorn src.api.main:app --reload

# Start workers
celery -A src.workers.celery_app worker --loglevel=info
```

## Saga Flow

```
CREATE_ORDER → RESERVE_STOCK → PROCESS_PAYMENT → CONFIRM_ORDER
     │              │                  │               │
     ▼              ▼                  ▼               ▼
   FAILED      COMPENSATE         COMPENSATE       COMPENSATE
   (cancel)    (release stock)    (refund)         (release all)
```
