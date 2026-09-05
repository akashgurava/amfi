from ..core.base import Buildable, DerivedTable, DerivedView


class PlansActiveView(DerivedView):
    """Filter for active schemes(has nav data for atleast past 10 days).
    Adds helpful columns like aum, nav, in use, retail, not lockin, etf, growth, direct.
    """

    @classmethod
    def name(cls) -> str:
        return "plans_active_v"

    @classmethod
    def select_sql(cls) -> str:
        return r"""
        WITH plans AS (
            SELECT fund_house, scheme, plan, sd_id
                , NOT regexp_matches(
                    scheme, '(?i)(deactivate|closed 1|closed|not to use)'
                ) AS is_in_use
                , NOT regexp_matches(
                    plan,
                    '(?i)(unclaimed|bonus option|provident fund|bonus)'
                ) AS is_retail
                , (
                    plan ILIKE '%no lock in%'
                    OR NOT EXISTS (
                        SELECT 1 FROM nav_plan_details_v p2
                        WHERE p2.scheme = npd.scheme
                          AND p2.plan ILIKE '%no lock in%'
                    )
                ) AS is_not_lockin
                , (
                    plan ILIKE '%etf%'
                    AND NOT regexp_matches(plan, '(?i)(fund of fund|fof)')
                ) AS is_etf
                , (
                    regexp_matches(plan, '(?i)(growth|cumulative)')
                    AND plan NOT ILIKE '%growth%fund%'
                ) AS is_growth
                , (
                    plan ILIKE '%direct%'
                    AND plan NOT ILIKE '%indirect%'
                ) AS is_direct
            FROM nav_plan_details_v npd
        ),
        nav_agg AS (
            SELECT sd_id
                , min(date) AS start_date
                , max(date) AS latest_date
                , arg_max(nav, date) AS latest_nav
            FROM nav_v
            GROUP BY sd_id
        )
        SELECT fh.fund_house_id, fh.fund_house
            , sc.scheme_id, sc.scheme
            , p.sd_id, p.plan
            , sc.scheme_type
            , lower(regexp_replace(
                CASE
                    WHEN sc.scheme_category LIKE '%-%'
                        THEN trim(split_part(sc.scheme_category, '-', 1))
                    ELSE trim(sc.scheme_category)
                END,
                '(?i)\s*scheme$',
                ''
            )) AS category
            , CASE
                WHEN sc.scheme_category LIKE '%-%'
                    THEN lower(trim(regexp_replace(
                        split_part(sc.scheme_category, '-', 2),
                        '(?i)\s*fund$',
                        ''
                    )))
                ELSE NULL
            END AS subcategory
            , sa.aum
            , sc.launch_date, n.start_date, n.latest_date, n.latest_nav
            , p.is_in_use, p.is_not_lockin, p.is_retail
            , p.is_etf, p.is_growth, p.is_direct
        FROM plans p
        INNER JOIN nav_agg n USING (sd_id)
        INNER JOIN fund_house_v fh USING (fund_house)
        LEFT JOIN scheme_v sc USING (scheme)
        LEFT JOIN scheme_aum_v sa USING (plan)
        WHERE n.latest_date > current_date - 10
        """


class TaxCategoryTable(DerivedTable):
    """Maps every ``(category, subcategory)`` seen in ``plans_active_v`` to a
    capital-gains tax rate.
    """

    @classmethod
    def name(cls) -> str:
        return "tax_cat"

    @classmethod
    def columns(cls) -> str:
        return "category VARCHAR, subcategory VARCHAR, tax DECIMAL(4,3)"

    @classmethod
    def select_sql(cls) -> str:
        return """
        WITH cat AS (
            SELECT DISTINCT category, subcategory
            FROM plans_active_v
        )
        SELECT category, subcategory,
            CASE
                WHEN category IN ('debt', 'income', 'money market') THEN 0.3
                WHEN category IN ('elss', 'equity') THEN 0.125
                WHEN category = 'hybrid' AND subcategory IN (
                    'aggressive hybrid', 'arbitrage', 'equity savings'
                ) THEN 0.125
                WHEN category = 'hybrid' THEN 0.2
                WHEN category = 'other' AND subcategory IN (
                    'fof domestic', 'index funds'
                ) THEN 0.125
                WHEN category = 'other' THEN 0.2
                WHEN category = 'solution oriented' THEN 0.125
            END AS tax
        FROM cat
        ORDER BY category, subcategory
        """


class NavActiveView(DerivedView):
    """NAV rows restricted to plans surviving ``plans_active_v`` with
    strictly positive NAV."""

    @classmethod
    def name(cls) -> str:
        return "nav_active_v"

    @classmethod
    def select_sql(cls) -> str:
        return """
        SELECT sd_id, date, nav
        FROM nav_v
        WHERE sd_id IN (SELECT sd_id FROM plans_active_v)
          AND nav > 0
        """


_PLANS_FUNDS_COLUMNS = (
    "fund_house_id INTEGER, fund_house VARCHAR, "
    "scheme_id INTEGER, scheme VARCHAR, "
    "sd_id INTEGER, plan VARCHAR, "
    "scheme_type VARCHAR, "
    "category VARCHAR, subcategory VARCHAR, "
    "tax DECIMAL(4,3), "
    "aum DOUBLE, "
    "launch_date DATE, start_date DATE, latest_date DATE, "
    "latest_nav DOUBLE, "
    "is_in_use BOOLEAN, is_not_lockin BOOLEAN, is_retail BOOLEAN, "
    "is_etf BOOLEAN, is_growth BOOLEAN, is_direct BOOLEAN"
)

_NAV_FUNDS_COLUMNS = "sd_id INTEGER, date DATE, nav DOUBLE, raw_nav DOUBLE"


class PlansFundsTable(DerivedTable):
    """Create table for plans. This will be used for plain funds.
    :class:`PlansPortfoliosTable` is for plan details of portfolios.

    Excludes close-ended schemes, prefers plans that are in-use + retail +
    no-lock-in + (ETF or growth-direct).
    """

    @classmethod
    def name(cls) -> str:
        return "plans_funds"

    @classmethod
    def columns(cls) -> str:
        return _PLANS_FUNDS_COLUMNS

    @classmethod
    def select_sql(cls) -> str:
        return """
        WITH candidate_plans AS (
            SELECT *,
                (is_in_use AND is_retail AND is_not_lockin
                 AND (is_etf OR (is_growth AND is_direct))) AS is_preferred
            FROM plans_active_v
            WHERE scheme_type <> 'Close Ended'
        ),
        ranked_plans AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY scheme_id
                    ORDER BY is_preferred DESC,
                        latest_nav DESC, latest_date DESC, start_date DESC,
                        is_in_use DESC, is_not_lockin DESC, is_retail DESC,
                        is_growth DESC, is_direct DESC
                ) AS rn
            FROM candidate_plans
        ),
        aum_data AS (
            SELECT scheme_id, sum(aum) AS aum
            FROM plans_active_v
            GROUP BY scheme_id
        )
        SELECT fund_house_id, fund_house,
            scheme_id, scheme,
            sd_id, plan,
            scheme_type, r.category, r.subcategory, t.tax,
            a.aum, launch_date, start_date, latest_date, latest_nav,
            is_in_use, is_not_lockin, is_retail, is_etf, is_growth, is_direct
        FROM ranked_plans r
        LEFT JOIN tax_cat t
          ON (r.category IS NOT DISTINCT FROM t.category)
         AND (r.subcategory IS NOT DISTINCT FROM t.subcategory)
        LEFT JOIN aum_data a USING (scheme_id)
        WHERE rn = 1
        ORDER BY scheme_id
        """


class PlansPortfoliosTable(DerivedTable):
    """Create table for plans. This will be used for portfolios.
    :class:`PlansFundsTable` is for plan details of funds.

    This table is populated by :meth:`PortfolioBuilder.build_plans`.
    """

    @classmethod
    def name(cls) -> str:
        return "plans_portfolios"

    @classmethod
    def columns(cls) -> str:
        return _PLANS_FUNDS_COLUMNS

    @classmethod
    def select_sql(cls) -> str:
        raise NotImplementedError("This table is populated by PortfolioBuilder")


class NavFundsTable(DerivedTable):
    """Create table for nav. This will be used for funds.
    :class:`NavPortfoliosTable` is for nav details of portfolios.

    Split/blip-adjusted NAV series for real AMFI funds.
    Applies a two-pass fix over ``nav_active_v``: (1) smooths single-day blips
    where a >20% move reverts within one day, (2) detects remaining >20%
    day-over-day moves as split factors and back-adjusts the series so the
    terminal NAV equals the raw terminal NAV. ``skip_sd_ids`` excludes funds
    whose large moves are legitimate.
    """

    @classmethod
    def name(cls) -> str:
        return "nav_funds"

    @classmethod
    def columns(cls) -> str:
        return _NAV_FUNDS_COLUMNS

    @classmethod
    def select_sql(cls) -> str:
        return """
        WITH config AS (
            SELECT 0.20 AS outlier_threshold
        ),
        config_exclude AS (
            SELECT ARRAY[133868,132989,130050,138358,120035,150615] AS skip_sd_ids
        ),
        nav_context AS (
            SELECT sd_id, date, nav,
                LAG(nav) OVER (PARTITION BY sd_id ORDER BY date ASC) AS prev_nav,
                LEAD(nav) OVER (PARTITION BY sd_id ORDER BY date ASC) AS next_nav
            FROM nav_active_v
            WHERE date >= '2015-01-01'
        ),
        de_blipped AS (
            SELECT
                c.sd_id, c.date, c.nav AS raw_nav,
                CASE
                    WHEN c.sd_id IN (SELECT UNNEST(skip_sd_ids) FROM config_exclude)
                        THEN c.nav
                    WHEN ABS((c.nav / c.prev_nav) - 1)
                         > (SELECT outlier_threshold FROM config)
                     AND ABS((c.next_nav / c.prev_nav) - 1) < 0.10
                        THEN (c.prev_nav + c.next_nav) / 2.0
                    ELSE c.nav
                END AS clean_nav
            FROM nav_context c
        ),
        split_detection AS (
            SELECT sd_id, date, raw_nav, clean_nav,
                LAG(clean_nav) OVER (PARTITION BY sd_id ORDER BY date ASC)
                    AS prev_clean_nav
            FROM de_blipped
        ),
        split_factors AS (
            SELECT sd_id, date, raw_nav, clean_nav,
                CASE
                    WHEN prev_clean_nav IS NULL THEN 1.0
                    WHEN sd_id IN (SELECT UNNEST(skip_sd_ids) FROM config_exclude)
                        THEN 1.0
                    WHEN ABS((clean_nav / prev_clean_nav) - 1)
                         > (SELECT outlier_threshold FROM config)
                        THEN (clean_nav / prev_clean_nav)
                    ELSE 1.0
                END AS daily_factor
            FROM split_detection
        ),
        cumulative_splits AS (
            SELECT sd_id, date, raw_nav, clean_nav, daily_factor,
                EXP(SUM(LN(daily_factor))
                    OVER (PARTITION BY sd_id ORDER BY date ASC)) AS running_factor
            FROM split_factors
        ),
        terminal_splits AS (
            SELECT sd_id, arg_max(running_factor, date) AS terminal_factor
            FROM cumulative_splits
            GROUP BY sd_id
        )
        SELECT c.sd_id, c.date,
            CASE
                WHEN c.sd_id IN (SELECT UNNEST(skip_sd_ids) FROM config_exclude)
                    THEN c.raw_nav
                ELSE c.clean_nav * (t.terminal_factor / c.running_factor)
            END AS nav,
            c.raw_nav
        FROM cumulative_splits c
        JOIN terminal_splits t ON c.sd_id = t.sd_id
        ORDER BY c.sd_id, c.date
        """


class NavPortfoliosTable(DerivedTable):
    """Create table for nav. This will be used for portfolios.
    :class:`NavFundsTable` is for nav details of funds.

    This table is populated by :meth:`PortfolioBuilder.build_nav`.
    """

    @classmethod
    def name(cls) -> str:
        return "nav_portfolios"

    @classmethod
    def columns(cls) -> str:
        return _NAV_FUNDS_COLUMNS

    @classmethod
    def select_sql(cls) -> str:
        raise NotImplementedError("This table is populated by PortfolioBuilder")


class PlansView(DerivedView):
    """View for all plans (funds and portfolios)."""

    @classmethod
    def name(cls) -> str:
        return "plans"

    @classmethod
    def select_sql(cls) -> str:
        return (
            f"SELECT * FROM {PlansFundsTable.name()}\n"
            "UNION ALL\n"
            f"SELECT * FROM {PlansPortfoliosTable.name()}"
        )


class NavView(DerivedView):
    """View for all nav (funds and portfolios)."""

    @classmethod
    def name(cls) -> str:
        return "nav"

    @classmethod
    def select_sql(cls) -> str:
        return (
            f"SELECT * FROM {NavFundsTable.name()}\n"
            "UNION ALL\n"
            f"SELECT * FROM {NavPortfoliosTable.name()}"
        )


DERIVED_OBJECTS: tuple[type[Buildable], ...] = (
    PlansActiveView,
    TaxCategoryTable,
    NavActiveView,
    PlansFundsTable,
    PlansPortfoliosTable,
    NavFundsTable,
    NavPortfoliosTable,
    PlansView,
    NavView,
)
