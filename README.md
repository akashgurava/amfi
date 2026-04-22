# AMFI NAV Loader

This project fetches AMFI NAV history, stores raw payload data in DuckDB, and builds typed post-fetch tables for analysis.

## Run

```bash
uv run python main.py
```

Optional flags:

- `--db <path>`: DuckDB file path (default: `amfi.duckdb`)
- `--fetch-all`: fetch all dates from `2010-01-01`
- `--fetch-new`: fetch only missing dates

## Data flow

1. `AmfiClient.fetch_dates` fetches NAV history for each date (async workers).
2. Raw payload is inserted into:
   - `raw_fund_details`
   - `raw_nav`
   - `date_run`
3. After all dates complete, transformed tables are refreshed:
   - `clean_nav`
   - `fund_details`

## Transformed tables

### `clean_nav`

Type-cleaned view of NAV rows from `raw_nav` with joined fund attributes:

- `fund_details_id` (INTEGER)
- `sd_id` (INTEGER, nullable via `TRY_CAST`)
- `nav_name` (VARCHAR)
- `nav_amount` (DECIMAL)
- `isin_ri`, `isin_po` (VARCHAR, empty -> NULL)
- `nav_date` (DATE)
- `nav_dtstamp` (TIMESTAMP)
- `nav_reissue`, `nav_repurchase` (DECIMAL)
- `nav_upload_ts` (TIMESTAMP from `hNAV_Upload_display`)
- `loaded_at` (TIMESTAMP)
- `fund_house_name`, `scheme_name`, `plan_name` (from `raw_fund_details`)

### `fund_details`

One row per fund plan from `raw_fund_details` with derived plan attributes:

- `id`
- `fund_house`
- `scheme`
- `plan`
- `is_direct`
- `is_growth`
- `is_idcw`
- `idcw_frequency` (`Daily`, `Weekly`, `Fortnightly`, `Monthly`, `Quarterly`, `HalfYearly`, `Annual`)
- `is_regular`
- `is_retail`
- `is_institutional`
- `refreshed_at`

## Logging

During `fetch_nav_data`, the app logs:

- date fetch range and progress
- fetch failures (if any)
- transformed table refresh start/end row counts
