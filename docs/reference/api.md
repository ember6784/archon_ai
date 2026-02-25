# API Endpoints

REST API документация для Archon AI.

---

## Base URL

```
http://localhost:8000
```

OpenAPI docs: http://localhost:8000/docs

---

## Health

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0-alpha",
  "environment": "dev"
}
```

---

## Circuit Breaker

### GET /api/v1/circuit_breaker/status

Get current autonomy level.

**Response:**
```json
{
  "level": "GREEN",
  "last_human_contact": "2026-02-08T12:00:00Z",
  "backlog_size": 0,
  "critical_issues": 0
}
```

### POST /api/v1/circuit_breaker/record_activity

Record human activity (resets AMBER/RED timers).

**Request:**
```json
{
  "action": "manual_review"
}
```

**Response:**
```json
{
  "status": "recorded",
  "new_level": "GREEN"
}
```

---

## Siege Mode

### POST /api/v1/siege/activate

Activate offline autonomy mode.

**Response:**
```json
{
  "status": "activated",
  "message": "Siege mode active - operating autonomously"
}
```

### POST /api/v1/siege/deactivate

Deactivate siege mode.

**Response:**
```json
{
  "status": "deactivated",
  "message": "Siege mode disabled"
}
```

---

## Debate Pipeline

### POST /api/v1/debate/start

Start a code review debate.

**Request:**
```json
{
  "code": "def add(a, b): return a + b",
  "requirements": "Create a function that adds two numbers",
  "file_path": "math.py",
  "language": "python"
}
```

**Response:**
```json
{
  "verdict": "approved",
  "confidence": 0.95,
  "consensus_score": 0.88,
  "final_code": "def add(a: int, b: int) -> int:\n    return a + b",
  "debate_rounds": 3,
  "participants": ["gpt-4o", "claude-3.5-sonnet", "llama-3.1"]
}
```

---

## RBAC

### GET /api/v1/rbac/roles

List all available roles.

**Response:**
```json
{
  "roles": [
    {
      "name": "admin",
      "permissions": ["read", "write", "delete", "admin"]
    },
    {
      "name": "operator",
      "permissions": ["read", "write"]
    },
    {
      "name": "viewer",
      "permissions": ["read"]
    }
  ]
}
```

### POST /api/v1/rbac/assign

Assign role to user.

**Request:**
```json
{
  "user_id": "user123",
  "role": "operator"
}
```

**Response:**
```json
{
  "status": "assigned",
  "user_id": "user123",
  "role": "operator"
}
```

---

## Audit

### GET /api/v1/audit/events

Query audit log.

**Query Parameters:**
- `limit` - Max events to return (default: 100)
- `offset` - Pagination offset
- `start_time` - Filter by start time (ISO 8601)
- `end_time` - Filter by end time (ISO 8601)
- `user_id` - Filter by user
- `operation` - Filter by operation type

**Response:**
```json
{
  "events": [
    {
      "id": "evt_123",
      "timestamp": "2026-02-08T12:00:00Z",
      "user_id": "user123",
      "operation": "write_file",
      "resource": "/path/to/file.py",
      "result": "approved",
      "hash": "abc123..."
    }
  ],
  "total": 150,
  "has_more": true
}
```

### GET /api/v1/audit/verify

Verify audit chain integrity.

**Response:**
```json
{
  "status": "valid",
  "events_verified": 150,
  "chain_intact": true,
  "last_hash": "abc123..."
}
```

---

## Error Responses

All endpoints return consistent error format:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request body",
    "details": {
      "field": "code",
      "reason": "Field is required"
    }
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request |
| `UNAUTHORIZED` | 401 | Authentication required |
| `FORBIDDEN` | 403 | Permission denied |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

---

## Authentication

Most endpoints require authentication via JWT token:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/rbac/roles
```

---

## Rate Limiting

API has rate limiting:
- **Default:** 100 requests/minute
- **Burst:** 20 requests/second

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1704393600
```
