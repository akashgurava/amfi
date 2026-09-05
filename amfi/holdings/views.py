"""Analytical views for AMC portfolio holdings."""

from __future__ import annotations

from ..core.base import View


class SchemeHoldingsView(View):
    """Analytical view joining raw scheme holdings with statements, sections, instruments, and schemes."""

    @classmethod
    def name(cls) -> str:
        return "scheme_holdings_v"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE OR REPLACE VIEW" if replace else "CREATE VIEW IF NOT EXISTS"
        return f"""
        {prefix} {cls.name()} AS
        SELECT 
            ps.statement_id,
            ps.fund_house_id,
            fh.fund_house,
            ps.scheme_id,
            sc.scheme,
            ps.portfolio_date,
            ps.frequency,
            ps.total_aum_lakhs AS scheme_total_aum_lakhs,
            hs.section_name,
            hs.broad_category,
            im.instrument_name,
            im.isin,
            im.industry_or_rating,
            sh.quantity,
            sh.market_value_lakhs,
            sh.aum_pct,
            sh.ytm_pct,
            sh.ytc_pct,
            sh.insert_ts
        FROM raw_scheme_holdings sh
        INNER JOIN raw_portfolio_statement ps ON sh.statement_id = ps.statement_id
        INNER JOIN raw_holding_sections hs ON sh.section_id = hs.section_id
        INNER JOIN raw_instrument_master im ON sh.instrument_id = im.instrument_id
        LEFT JOIN scheme_v sc ON ps.scheme_id = sc.scheme_id
        LEFT JOIN fund_house_v fh ON ps.fund_house_id = fh.fund_house_id;
        """


class PortfolioStatementView(View):
    """Analytical view joining statement headers with schemes and fund houses."""

    @classmethod
    def name(cls) -> str:
        return "portfolio_statement_v"

    @classmethod
    def create_sql(cls, if_not_exists: bool = True, replace: bool = False) -> str:
        prefix = "CREATE OR REPLACE VIEW" if replace else "CREATE VIEW IF NOT EXISTS"
        return f"""
        {prefix} {cls.name()} AS
        SELECT 
            ps.statement_id,
            ps.fund_house_id,
            fh.fund_house,
            ps.scheme_id,
            sc.scheme,
            ps.portfolio_date,
            ps.frequency,
            ps.total_aum_lakhs,
            ps.holding_count,
            ps.rejected_count,
            ps.source_file,
            ps.insert_ts
        FROM raw_portfolio_statement ps
        LEFT JOIN scheme_v sc ON ps.scheme_id = sc.scheme_id
        LEFT JOIN fund_house_v fh ON ps.fund_house_id = fh.fund_house_id;
        """


HOLDINGS_VIEWS: tuple[type[View], ...] = (
    PortfolioStatementView,
    SchemeHoldingsView,
)
