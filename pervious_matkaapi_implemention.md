# Previous Matka API Implementation Record

**Document Version:** 1.0  
**Date:** 2026-10-13  
**Status:** Archived / Superseded by MatkaWebhook API  

This document serves as an exhaustive reference record of the **previous (legacy) Matka API implementation** used by `resultApi` before migrating to the rotating-token `matkawebhook.matkaapi.net` integration.

---

## 1. Overview & Architecture

The previous integration communicated directly with `matkaapi.com` via a single GET endpoint:
- **Base Endpoint:** `https://www.matkaapi.com/mapi/market_api.php`
- **Protocol:** HTTP GET
- **Authentication Strategy:** Static Domain Key (`domain_key`) + Origin Domain (`domain`) + **Strict Server IP Whitelisting**
- **Rate Limit Requirement:** Minimum 5 to 10 seconds between requests
- **Provider Cache Window:** 45 seconds server-side cache

---

## 2. Environment Variables & Configuration

The legacy implementation relied on the following environment variables (defined in `.env` and `config/settings.py`):

```bash
# Previous Matka API Configuration
RESULT_API_URL=https://www.matkaapi.com/mapi/market_api.php
RESULT_API_KEY=6dc0d710909e4710a1df481c6e095be8
RESULT_API_DOMAIN=quebix.in

# Polling & Rate Limiting
RESULT_POLL_INTERVAL=5
# RESULT_MAX_POLL_MINUTES=
# RESULT_MAX_RETRIES=
```

In `config/settings.py`:
```python
RESULT_API_URL = config('RESULT_API_URL', default='https://www.matkaapi.com/mapi/market_api.php')
RESULT_API_KEY = config('RESULT_API_KEY', default='')
RESULT_API_DOMAIN = config('RESULT_API_DOMAIN', default='')
RESULT_POLL_INTERVAL = config('RESULT_POLL_INTERVAL', default=5, cast=int)
```

---

## 3. API Request Specification

Outbound requests were made using Python `requests.Session()` with HTTP GET:

### Primary Request (Single Market)
```http
GET https://www.matkaapi.com/mapi/market_api.php?market=padmavathi&domain_key=6dc0d710909e4710a1df481c6e095be8&domain=quebix.in&date=2026-10-13
Accept: application/json
User-Agent: ResultsManagementSystem/1.0
```

- `market`: Sanitized lowercased market code (spaces and dashes stripped, e.g. `PADMAVATHI` → `padmavathi`).
- `domain_key`: The customer API key registered with matkaapi.com.
- `domain`: The verified domain name registered with the API key.
- `date`: Optional date in `YYYY-MM-DD` format.

### Fallback Request (All Markets)
When a single market query did not return a match, the system queried `market=all`:
```http
GET https://www.matkaapi.com/mapi/market_api.php?market=all&domain_key=6dc0d710909e4710a1df481c6e095be8&domain=quebix.in
```
The results were cached for 5 seconds, and local fuzzy matching was applied on `external_name`.

---

## 4. Response Payload & Format Handling

### Expected JSON Structure
```json
{
  "status": true,
  "data": [
    {
      "name": "PADMAVATHI",
      "result": "150-6"
    }
  ],
  "message": "Success"
}
```

Or for close result:
```json
{
  "status": true,
  "data": [
    {
      "name": "PADMAVATHI",
      "result": "227-18-440"
    }
  ]
}
```

### Result String Format Validation
The system strictly enforced regex parsing on the `result` string:
1. **OPEN Result:**
   - Must match 3 digits - 1 digit: `^\d{3}-\d$` (e.g. `150-6`, `234-9`).
   - Partial strings like `234-9*`, `234-9*-***`, or `234-9**-***` were sanitized to extract `234-9`.
2. **CLOSE Result:**
   - Must match 3 digits - 2 digits - 3 digits: `^\d{3}-\d{2}-\d{3}$` (e.g. `227-18-440` or `234-99-289`).
   - If asterisks (`*`) or partial open results were present, it was considered not yet declared.

### Cleaning Polluted Responses (`_parse_response_json`)
Due to PHP notices, warnings, and HTML error pages frequently emitted by the legacy server, the client implemented defensive parsing:
- Direct JSON parsing fallback to bracket/brace substring extraction (`start = min(brace, bracket)` to `end = max(last_brace, last_bracket)`).
- HTML title extraction for Cloudflare/WAF/Nginx 403 blocks.
- Forced IPv4 name resolution via `urllib3_conn.allowed_gai_family = lambda: socket.AF_INET`.

---

## 5. Rate Limiting & Caching Architecture

1. **In-Memory Rate Limit Lock (`_enforce_rate_limit`)**:
   - Monitored `_last_request_timestamp`.
   - Enforced sleep if elapsed time < `RESULT_POLL_INTERVAL` (5 seconds).
2. **Django Cache (`cache.get` / `cache.set`)**:
   - `matka_api_cache_{market}_{date}_{type}` cached valid responses for **45 seconds** (matching server cache duration).
   - Negative responses cached for **5 seconds** to prevent flood while polling.
   - `matka_api_cache_all_{date}` cached all-market fallback list for **5 seconds**.

---

## 6. Project Integration Points

1. **`markets/services/result_api.py`**:
   - Contained `ResultAPIClient` implementing rate-limiting, caching, and regex validation.
2. **`markets/services/result_fetcher.py`**:
   - `ResultFetcherService` injected `ResultAPIClient`.
   - Handled database transactions, `FetchAttempt` audits, and idempotent result persistence in `Result` model.
3. **`markets/tasks.py`**:
   - `check_and_schedule_result_fetches`: Celery beat periodic task running every 60 seconds to inspect active markets and queue fetches when `current_time >= open_time` or `current_time >= close_time`.
   - `fetch_market_result_task`: Celery worker task that polled `ResultFetcherService` and scheduled retries with countdown.

---

## 7. Known Issues & Reasons for Migration

1. **Strict IP Whitelisting Failures:**
   The legacy API rejected requests whenever the outbound server IP changed (e.g. AWS EC2 elastic IP reassignment or local development machines), returning `(Your Server IP: x.x.x.x, Whitelisted IP: y.y.y.y)`.
2. **Static Key Risk:**
   A single compromised API key had no rotation mechanism.
3. **No Webhook or Batch Multi-Market Support:**
   The new `matkawebhook.matkaapi.net` provides authenticated rotating session tokens, bulk today market results in one call, and user account management.
