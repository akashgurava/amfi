"""Aditya Birla Sun Life Mutual Fund (ABSL) portfolio holdings scraper."""

import io
import logging
import re
import zipfile
from datetime import date, datetime
from typing import Any

import duckdb
import httpx
from python_calamine import CalamineWorkbook

from ..base import BasePortfolioScraper, normalize_scheme_name
from ..enums import DisclosureFrequency, ScraperFundHouse
from ..models import DisclosureMeta, HoldingCandidate, StatementMeta
from ..validator import RowValidator

logger = logging.getLogger(__name__)

ABSL_ACCORDION_API = (
    "https://mutualfund.adityabirlacapital.com/postlogin/CustomApi/Resources/"
    "FactsheetAccordionById?id=3ccab227-9de5-4494-b78d-2b4f7c0c054a"
    "&ctype=%2Fsitecore%2Fcontent%2FRoot%2FBSL%2FLibrary%2FLists%2FFAQ%2F"
    "Customer%20Types%2FIndividual&month= &year=0"
)

# Known historical scheme aliases / renames (fallback when historical AMC name does not match current AMFI name)
ABSL_SHORT_CODE_ALIASES: dict[str, int] = {
    "ADVG": 11571,  # Large & Mid Cap Fund (named 'Equity Advantage Fund' in 2025)
    "FTPTQ": 13070,  # Fixed Term Plan Series TQ (1879 Days)
}

MONTH_MAP = {
    "JAN": 1, "JANUARY": 1,
    "FEB": 2, "FEBRUARY": 2,
    "MAR": 3, "MARCH": 3,
    "APR": 4, "APRIL": 4,
    "MAY": 5,
    "JUN": 6, "JUNE": 6,
    "JUL": 7, "JULY": 7,
    "AUG": 8, "AUGUST": 8,
    "SEP": 9, "SEPT": 9, "SEPTEMBER": 9,
    "OCT": 10, "OCTOBER": 10,
    "NOV": 11, "NOVEMBER": 11,
    "DEC": 12, "DECEMBER": 12,
}


def parse_disclosure_date_from_title(title: str) -> date | None:
    """Extract calendar date from disclosure title or filename."""
    # Try pattern like: 'July 31, 2026' or 'April-30-2026' or 'July_31_2026'
    m1 = re.search(r"([A-Za-z]+)[\s\-_]+(\d{1,2})[,\s\-_]+(\d{4})", title)
    if m1:
        month_name, day, year = m1.group(1).upper(), int(m1.group(2)), int(m1.group(3))
        if month_name in MONTH_MAP:
            try:
                return date(year, MONTH_MAP[month_name], day)
            except ValueError:
                pass

    # Try pattern like: '31 JAN 2026' or '30-APR-2026' or '31-OCT-2025'
    m2 = re.search(r"(\d{1,2})[\s\-_]+([A-Za-z]+)[\s\-_]+(\d{4})", title)
    if m2:
        day, month_name, year = int(m2.group(1)), m2.group(2).upper(), int(m2.group(3))
        if month_name in MONTH_MAP:
            try:
                return date(year, MONTH_MAP[month_name], day)
            except ValueError:
                pass

    # Try pattern like: '31052026' (DDMMYYYY) anywhere in filename or title
    m3 = re.search(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", title)
    if m3:
        day, month, year = int(m3.group(1)), int(m3.group(2)), int(m3.group(3))
        if 1 <= day <= 31 and 1 <= month <= 12:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    return None


def canonicalize_absl_url(url: str) -> str:
    """Rewrite Azure Edge CDN link to direct mutualfund.adityabirlacapital.com URL."""
    if not url:
        return ""
    clean = url.strip()
    clean = re.sub(r"^https?://abcscprod\.azureedge\.net", "https://mutualfund.adityabirlacapital.com", clean)
    return clean


class AbslPortfolioScraper(BasePortfolioScraper):
    """Scraper and parser for Aditya Birla Sun Life Mutual Fund portfolio disclosures."""

    fund_house_id = ScraperFundHouse.ABSL.value
    amc_name = "Aditya Birla Sun Life Mutual Fund"

    def __init__(self, db_conn: duckdb.DuckDBPyConnection | None = None):
        super().__init__(db_conn)
        self._scheme_id_cache: dict[str, int | None] = {}
        self._init_db_cache()

    def _init_db_cache(self) -> None:
        """Pre-populate scheme mapping cache from amfi.duckdb."""
        if not self.conn:
            return

        # Pre-load raw_amc_master_absl
        try:
            rows = self.conn.execute(
                "SELECT amc_sheet_name, scheme_id FROM raw_amc_master_absl WHERE scheme_id IS NOT NULL"
            ).fetchall()
            for sheet_name, s_id in rows:
                self._scheme_id_cache[sheet_name.strip().upper()] = int(s_id)
        except Exception:
            pass

        # Pre-load scheme_v for fund_house_id = 3
        try:
            db_schemes = self.conn.execute(
                "SELECT scheme_id, scheme FROM scheme_v WHERE fund_house_id = 3"
            ).fetchall()
            for s_id, s_name in db_schemes:
                norm = normalize_scheme_name(s_name)
                self._scheme_id_cache[norm] = int(s_id)
        except Exception:
            pass

    def list_disclosures(
        self,
        frequency: DisclosureFrequency = DisclosureFrequency.MONTHLY,
    ) -> list[DisclosureMeta]:
        """
        Query ABSL API to discover all monthly or fortnightly portfolio disclosures.
        """
        logger.info("Querying ABSL disclosures catalog from official API...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        }

        items = []
        try:
            with httpx.Client(verify=False, timeout=30.0) as client:
                resp = client.get(ABSL_ACCORDION_API, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("AccordionList", [])
        except Exception as e:
            logger.warning("ABSL Accordion API request failed: %s. Returning empty catalog.", e)
            return []

        disclosures: list[DisclosureMeta] = []
        for it in items:
            raw_url = it.get("pdfUrl") or it.get("shareMedia") or ""
            if not raw_url:
                continue
            download_url = canonicalize_absl_url(raw_url)
            title = str(it.get("ResourceLink") or it.get("shareTitle") or "").strip()

            as_on_date = parse_disclosure_date_from_title(title)
            if not as_on_date:
                # Try from filename
                as_on_date = parse_disclosure_date_from_title(download_url)
            if not as_on_date:
                continue

            # Check frequency from title
            t_upper = title.upper()
            disc_freq = DisclosureFrequency.MONTHLY
            if "FORTNIGHTLY" in t_upper:
                disc_freq = DisclosureFrequency.FORTNIGHTLY
            elif "HALF" in t_upper and "YEAR" in t_upper:
                disc_freq = DisclosureFrequency.HALF_YEARLY

            if frequency and disc_freq != frequency:
                continue

            disclosures.append(
                DisclosureMeta(
                    fund_house_id=self.fund_house_id,
                    as_on_date=as_on_date,
                    title=title or f"Monthly Portfolio as on {as_on_date}",
                    download_url=download_url,
                    frequency=disc_freq,
                )
            )

        # Sort by date descending
        disclosures.sort(key=lambda d: d.as_on_date, reverse=True)
        logger.info("Found %d %s disclosures for ABSL.", len(disclosures), frequency.value)
        return disclosures

    def resolve_scheme_id(
        self,
        amc_identifier: str,
        amc_scheme_name: str,
    ) -> int | None:
        """
        Resolve AMFI scheme_id using short code cache, master table, or normalized name.
        """
        clean_code = amc_identifier.strip().upper()

        # 1. First check normalized scheme name against scheme_v cache
        norm = normalize_scheme_name(amc_scheme_name)
        if norm in self._scheme_id_cache:
            res_id = self._scheme_id_cache[norm]
            self._scheme_id_cache[clean_code] = res_id
            return res_id

        # 2. Check if sheet code is already cached or in raw_amc_master_absl
        if clean_code in self._scheme_id_cache:
            return self._scheme_id_cache[clean_code]

        # 3. Check fallback aliases (e.g. historical fund renames)
        if clean_code in ABSL_SHORT_CODE_ALIASES:
            res_id = ABSL_SHORT_CODE_ALIASES[clean_code]
            self._scheme_id_cache[clean_code] = res_id
            return res_id

        return None

    def parse_disclosure(
        self,
        raw_bytes: bytes,
        disclosure: DisclosureMeta,
        filter_schemes: list[str] | None = None,
    ) -> list[StatementMeta]:
        """
        Parse multi-sheet Excel workbook from disclosure ZIP payload.
        """
        z = zipfile.ZipFile(io.BytesIO(raw_bytes))
        excel_names = [n for n in z.namelist() if n.lower().endswith((".xls", ".xlsx"))]
        if not excel_names:
            raise ValueError(f"No Excel file found inside ZIP archive: {z.namelist()}")

        excel_fname = excel_names[0]
        logger.info("Reading Excel workbook '%s' with Calamine...", excel_fname)
        wb = CalamineWorkbook.from_filelike(io.BytesIO(z.read(excel_fname)))

        # 1. Read Index sheet if present to extract scheme code -> scheme name mapping
        index_map: dict[str, str] = {}
        if "Index" in wb.sheet_names:
            idx_rows = wb.get_sheet_by_name("Index").to_python()
            for row in idx_rows[1:]:
                clean_row = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if len(clean_row) >= 2:
                    code = clean_row[0]
                    name = clean_row[-1]
                    if code not in ("Scheme Code", "FUND CODE") and name not in ("Scheme Name", "FUND NAME"):
                        index_map[code.upper()] = name

        filter_set = {s.upper().strip() for s in filter_schemes} if filter_schemes else None

        statements: list[StatementMeta] = []
        for sname in wb.sheet_names:
            if sname == "Index":
                continue

            sname_upper = sname.upper().strip()
            if filter_set and sname_upper not in filter_set:
                continue

            rows = wb.get_sheet_by_name(sname).to_python()
            if not rows:
                continue

            stmt = self._parse_scheme_sheet(
                sheet_name=sname,
                rows=rows,
                disclosure=disclosure,
                scheme_name_from_index=index_map.get(sname_upper),
                source_file=excel_fname,
            )
            if stmt:
                statements.append(stmt)

        return statements

    def _parse_scheme_sheet(
        self,
        sheet_name: str,
        rows: list[list[Any]],
        disclosure: DisclosureMeta,
        scheme_name_from_index: str | None,
        source_file: str,
    ) -> StatementMeta | None:
        """Parse an individual scheme sheet into a StatementMeta object."""
        # 1. Extract scheme name from Row 0 if not provided
        scheme_name = scheme_name_from_index
        if not scheme_name and len(rows) > 0 and len(rows[0]) >= 2:
            r0_clean = [str(c).strip() for c in rows[0] if c is not None and str(c).strip()]
            if len(r0_clean) >= 2:
                scheme_name = r0_clean[-1]
            elif len(r0_clean) == 1 and len(r0_clean[0]) > 5:
                scheme_name = r0_clean[0]

        if not scheme_name:
            scheme_name = f"Aditya Birla Sun Life {sheet_name} Fund"

        # Resolve scheme_id
        scheme_id = self.resolve_scheme_id(sheet_name, scheme_name)
        if scheme_id is None:
            # Generate fallback scheme_id for side-pockets or unmapped close-ended funds
            scheme_id = 9900000 + abs(hash(sheet_name)) % 100000
            logger.warning(
                "Scheme '%s' (sheet: %s) could not be mapped to existing scheme_id. Assigned placeholder ID %d.",
                scheme_name,
                sheet_name,
                scheme_id,
            )

        # Update raw_amc_master_absl in database if connection exists
        if self.db:
            self.db.upsert_amc_master_absl(
                amc_sheet_name=sheet_name,
                amc_scheme_name=scheme_name,
                scheme_id=scheme_id if scheme_id < 9000000 else None,
                statement_date=disclosure.as_on_date,
            )

        validator = RowValidator(amc_name=self.amc_name, scheme_name=scheme_name)

        # 2. Dynamic column detection in header (rows 0-15)
        h_idx = -1
        col_map: dict[str, int] = {}
        for idx, row in enumerate(rows[:15]):
            row_clean = [str(c).strip().replace("\r", " ").replace("\n", " ") if c is not None else "" for c in row]
            for c_idx, cell in enumerate(row_clean):
                cu = cell.upper()
                if "INSTRUMENT" in cu or "ISSUER" in cu:
                    col_map["instrument"] = c_idx
                elif cu == "ISIN" or "ISIN" in cu:
                    col_map["isin"] = c_idx
                elif "INDUSTRY" in cu or "RATING" in cu:
                    col_map["industry_rating"] = c_idx
                elif "QUANTITY" in cu or "QTY" in cu:
                    col_map["quantity"] = c_idx
                elif any(k in cu for k in ["MARKET", "FAIR VALUE", "LACS", "LAKHS"]):
                    col_map["market_value"] = c_idx
                elif any(k in cu for k in ["% TO AUM", "% OF AUM", "% TO NAV", "% TO NET ASSETS", "NET ASSET"]):
                    col_map["aum_pct"] = c_idx
                elif "YTC" in cu or "CALL" in cu:
                    col_map["ytc"] = c_idx
                elif "YTM" in cu or "YIELD" in cu:
                    col_map["ytm"] = c_idx

            if "market_value" in col_map and "aum_pct" in col_map and "instrument" in col_map:
                h_idx = idx
                break

        if h_idx == -1:
            logger.warning("Could not identify header columns for sheet %s. Skipping sheet.", sheet_name)
            return None

        # 3. Parse data rows
        stmt = StatementMeta(
            fund_house_id=self.fund_house_id,
            scheme_id=scheme_id,
            amc_sheet_name=sheet_name,
            amc_scheme_name=scheme_name,
            portfolio_date=disclosure.as_on_date,
            frequency=disclosure.frequency,
            source_file=source_file,
        )

        current_section = "General Portfolio"
        total_aum_lakhs = None

        for r_idx in range(h_idx + 1, len(rows)):
            row = rows[r_idx]
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue

            row_str = " ".join([str(c) for c in row if c is not None]).upper()

            # Stop parsing when Grand Total is reached
            if "GRAND TOTAL" in row_str:
                # Capture total AUM from Grand Total row
                mv_raw = row[col_map["market_value"]] if col_map["market_value"] < len(row) else None
                if mv_raw is not None:
                    total_aum_lakhs = validator.parse_market_value(mv_raw)
                break

            if "NOTES:" in row_str or "DISCLOSURE ON" in row_str:
                break

            # Skip subtotals
            if "SUB TOTAL" in row_str or "SUB-TOTAL" in row_str or "TOTAL" in row_str:
                continue

            mv_raw = row[col_map["market_value"]] if col_map["market_value"] < len(row) else None
            pct_raw = row[col_map["aum_pct"]] if col_map["aum_pct"] < len(row) else None

            # Check section header row (both market value and AUM % are empty)
            is_mv_empty = mv_raw is None or str(mv_raw).strip() in ("", "-")
            is_pct_empty = pct_raw is None or str(pct_raw).strip() in ("", "-")

            if is_mv_empty and is_pct_empty:
                sec_title = " ".join([str(c).strip() for c in row if c is not None and str(c).strip()])
                if sec_title:
                    current_section = sec_title
                continue

            # Extract fields
            inst_raw = row[col_map["instrument"]] if col_map["instrument"] < len(row) else None
            isin_raw = row[col_map["isin"]] if "isin" in col_map and col_map["isin"] < len(row) else None
            ind_raw = (
                row[col_map["industry_rating"]]
                if "industry_rating" in col_map and col_map["industry_rating"] < len(row)
                else None
            )
            qty_raw = (
                row[col_map["quantity"]]
                if "quantity" in col_map and col_map["quantity"] < len(row)
                else None
            )
            ytm_raw = row[col_map["ytm"]] if "ytm" in col_map and col_map["ytm"] < len(row) else None
            ytc_raw = row[col_map["ytc"]] if "ytc" in col_map and col_map["ytc"] < len(row) else None

            # Handle merged or offset instrument name column
            inst_name = str(inst_raw).strip() if inst_raw is not None else ""
            if not inst_name:
                for offset in [-1, 1]:
                    alt_idx = col_map["instrument"] + offset
                    if 0 <= alt_idx < len(row) and row[alt_idx] is not None and str(row[alt_idx]).strip():
                        inst_name = str(row[alt_idx]).strip()
                        break

            candidate = HoldingCandidate(
                sheet_name=sheet_name,
                line_number=r_idx + 1,
                raw_row=row,
                section_name=current_section,
                instrument_name=inst_name,
                isin=isin_raw,
                industry_or_rating=ind_raw,
                quantity=qty_raw,
                market_value_lakhs=mv_raw,
                aum_pct=pct_raw,
                ytm_pct=ytm_raw,
                ytc_pct=ytc_raw,
            )

            val_holding, rejected_rec = validator.validate(candidate)
            if val_holding:
                stmt.holdings.append(val_holding)
            elif rejected_rec:
                stmt.rejections.append(rejected_rec)

        stmt.total_aum_lakhs = total_aum_lakhs
        stmt.holding_count = len(stmt.holdings)
        stmt.rejected_count = len(stmt.rejections)

        logger.info(
            "Statement %s (%s) [%s]: %d holdings accepted, %d rejected.",
            sheet_name,
            scheme_name,
            disclosure.as_on_date,
            stmt.holding_count,
            stmt.rejected_count,
        )
        return stmt
