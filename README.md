# AMFI NAV Loader

Async Python client and ETL for the public [AMFI India](https://www.amfiindia.com)
mutual-fund data. Fetches fund-house, scheme, document, AUM, and daily NAV
history into DuckDB as raw tables plus typed views for analysis.

## Requirements

- Python `>=3.10`
- [uv](https://docs.astral.sh/uv/) for dependency management

Install deps:

```bash
uv sync
```

## CLI

All commands share a single optional flag:

- `--db <path>`: DuckDB file (default `amfi.duckdb`).

### Fetch scheme metadata

```bash
uv run python main.py fetch plans
```

Fetches fund houses → scheme list → scheme details, documents, and AUM.
Populates `raw_fund_house`, `raw_scheme`, `raw_scheme_document`,
`raw_scheme_aum`.

### Fetch NAV history

```bash
# Only dates missing from raw_nav (default)
uv run python main.py fetch nav --dates new

# Full history from 2010-01-01 (re-fetches even existing dates)
uv run python main.py fetch nav --dates all

# A specific year / month / day, or a comma-separated mix
uv run python main.py fetch nav --dates 2024
uv run python main.py fetch nav --dates 2024-03
uv run python main.py fetch nav --dates 2024-03-15
uv run python main.py fetch nav --dates 2023,2024-01,2024-02-10
```

Populates `raw_nav` (bulk append, no dedup) and `raw_nav_plan_details`
(`INSERT … ON CONFLICT DO NOTHING` keyed on `sd_id`).

### Fetch everything

```bash
uv run python main.py fetch all
```

Runs scheme metadata then NAV history for missing dates.

## Architecture

```
main.py
  └── App (amfi/app.py)             orchestrator: chooses dates, runs stages
        ├── AmfiClient (client.py)  async HTTP + rate limiting + retries
        │     └── MultiWindowRateLimiter, RateLimitRule
        ├── Database (db.py)        DuckDB connection + typed inserts
        ├── ParallelRunner (utility.py)  bounded-concurrency worker pool
        └── WriteQueue (utility.py)      serialises DuckDB writes
```

Key data contracts live in `amfi/data.py`:

- `Raw*Response` dataclasses validate and normalise API payloads.
- `Raw*` table classes declare DuckDB schemas, insert columns, and
  `insert_sql()` (plus `ON CONFLICT` variants where applicable).
- `*View` classes declare DuckDB views with validation `pre_check()` SQL.

## DuckDB schema

### Raw tables (all TEXT columns + `loaded_at TIMESTAMP`)

| Table                   | Purpose                                        |
|-------------------------|------------------------------------------------|
| `raw_fund_house`        | Fund-house metadata (`mf_id`, AMC URLs, …)     |
| `raw_scheme`            | Per-scheme attributes from `scheme-details`    |
| `raw_scheme_document`   | Document URLs per scheme                       |
| `raw_scheme_aum`        | AUM history per plan (`str_sd_id`)             |
| `raw_nav_plan_details`  | Fund house/scheme/plan lookup keyed by `sd_id` |
| `raw_nav`               | NAV rows per date (append-only, no dedup)      |

### Views (typed, deduplicated by latest `loaded_at`)

| View                  | Key                     | Source                     |
|-----------------------|-------------------------|----------------------------|
| `fund_house_v`        | `mf_id`                 | `raw_fund_house`           |
| `scheme_v`            | `scheme_id`             | `raw_scheme`               |
| `scheme_document_v`   | `scheme_id`             | `raw_scheme_document`      |
| `scheme_aum_v`        | `plan`                  | `raw_scheme_aum`           |
| `nav_plan_details_v`  | `sd_id`                 | `raw_nav_plan_details`     |
| `nav_v`               | `(sd_id, hnav_date)`    | `raw_nav`                  |

Each view runs a `pre_check()` query first and raises `DataValidationError`
on schema drift (e.g. non-numeric `mf_id`, unparseable dates).

## Rate limiting & retries

`AmfiClient` accepts a list of `RateLimitRule` windows applied globally
across worker tasks:

```python
from amfi import AmfiClient, RateLimitRule

client = AmfiClient(
    parallel_requests=4,
    rate_limits=[
        RateLimitRule.per_seconds(2, 1),    # 2 req/s
        RateLimitRule.per_seconds(60, 60),  # 60 req/min
    ],
    max_retries=3,
)
```

Per-date failures are recorded in `ParallelRunner.failed_by_type` and
summarised by exception class at INFO level.

## Logging

Configured via `configure_logging()` (called from `main.py`). Each stage
emits `*_START`, `*_FILTERED` / `*_SKIP`, and `*_SUMMARY` lines, e.g.:

```
SAVE_NAV_SUMMARY. TOTAL=365 SUCCESS=364 FAILED=1
SAVE_NAV_FAILED RequestExecutionError: ['2024-08-15']
```

## Testing

```bash
# Unit tests (fast, no network)
uv run pytest tests/unit

# Live integration tests against amfiindia.com (opt-in)
AMFI_RUN_LIVE_TESTS=1 uv run pytest tests/integration -m integration
```

Lint & type-check:

```bash
uv run ruff check amfi tests
uv run mypy amfi tests/unit
```
