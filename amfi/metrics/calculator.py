"""Fund metrics computation layer.

Provides two public classes:

:class:`MetricsBuilder`
    Pure-polars builder.  Accepts a pivoted ``pl.DataFrame`` (one ``date``
    column plus one NAV column per scheme), a benchmark column name, a
    frequency, and a list of metric names.  ``build()`` returns a wide
    ``pl.DataFrame`` with one row per scheme and ``<metric>_<period>``
    columns.

:class:`DatabaseMetricsAdapter`
    Thin adapter that loads data from DuckDB, calls :class:`MetricsBuilder`
    per frequency × metric-group, and writes results back to the existing
    ``metrics_*`` tables + per-period views.

Metric groups
~~~~~~~~~~~~~
- **basic**: ``r``, ``cagr``, ``sr``, ``vol``
- **risk**: ``md``, ``calmar``, ``var95``, ``var99``, ``cvar95``, ``cvar99``, ``ui``
- **benchmark**: ``beta``, ``alpha``, ``r_sq``, ``ir``, ``m2``
- **performance** (yearly only): ``sharpe``, ``sortino``

Returns are simple daily returns :math:`r_i = nav_i / nav_{i-1} - 1`.
Annualisation assumes 252 trading days.  Covariance/variance/std use the
sample estimator (``ddof=1``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import polars as pl

from .tables import (
    METRICS_TABLES,
    Frequency,
    MetricsConfig,
    MetricsPerformanceYearlyTable,
    all_periods,
    basic_table,
    benchmark_table,
    metrics_columns,
    period_order,
    risk_table,
)

if TYPE_CHECKING:
    from .db import Database

LOGGER = logging.getLogger(__name__)

_FREQUENCIES: tuple[Frequency, ...] = ("yearly", "quarterly", "monthly")

# ======================================================================
# Metric & MetricGroup dataclasses
# ======================================================================

# Formulas reference ``pl.col("_td")`` and ``pl.col("_rf")`` which are
# injected as literal columns by ``_apply_metrics`` from the runtime
# ``MetricsConfig``.


@dataclass(frozen=True)
class Metric:
    """Single metric definition.

    Attributes
    ----------
    prefix : str
        Short column name used in output (e.g. ``"r"``, ``"beta"``).
    name : str
        Human-readable name.
    formula : pl.Expr
        Self-contained Polars expression referencing pre-aggregated columns
        produced by the builder.
    scale : float
        Post-formula multiplier (e.g. ``100.0`` for percentage scaling).
    """

    prefix: str
    name: str
    formula: pl.Expr
    scale: float = 1.0


@dataclass(frozen=True)
class MetricGroup:
    """Logical grouping of metrics.

    Attributes
    ----------
    name : str
        Group identifier (``"basic"``, ``"risk"``, …).
    metrics : tuple[Metric, ...]
        Ordered metrics in this group.
    frequencies : tuple[Frequency, ...]
        Which frequencies this group supports.
    """

    name: str
    metrics: tuple[Metric, ...]
    frequencies: tuple[Frequency, ...] = ("yearly", "quarterly", "monthly")


# ------------------------------------------------------------------
# Individual metric definitions
# ------------------------------------------------------------------

R = Metric(
    prefix="r",
    name="Returns",
    formula=pl.col("last_nav") / pl.col("first_nav") - 1.0,
    scale=100.0,
)
"""Simple period return.

Measures the total percentage change in price over a period.
A value of 12 means the series gained 12 %.

Formula: `(close_last / close_first) - 1`
"""

CAGR = Metric(
    prefix="cagr",
    name="CAGR",
    formula=pl.when(pl.col("n") > 0)
    .then(
        (pl.col("last_nav") / pl.col("first_nav")) ** (pl.col("_td") / pl.col("n"))
        - 1.0
    )
    .otherwise(None),
    scale=100.0,
)
"""Compound Annual Growth Rate.

Annualised return that accounts for compounding.  A CAGR of 15 means the
series grew at an equivalent annual rate of 15 %, regardless of the actual
period length.

Formula: `(close_last / close_first) ^ (trading_days / n) - 1`
"""

SR = Metric(
    prefix="sr",
    name="Success Ratio",
    formula=pl.when(pl.col("ret_count") > 0)
    .then(pl.col("pos_count") / pl.col("ret_count"))
    .otherwise(None),
    scale=100.0,
)
"""Success Ratio (hit rate).

Percentage of days with a positive return.  A value of 55 means the series
closed higher than the previous day on 55 % of trading days.

Formula: `positive_days / total_days`
"""

VOL = Metric(
    prefix="vol",
    name="Volatility",
    formula=pl.col("ret_std") * pl.col("_td").sqrt(),
    scale=100.0,
)
"""Annualised Volatility.

Standard deviation of daily returns scaled to a yearly figure.  A volatility
of 20 means the series fluctuates roughly ±20 % per year.

Formula: `std(daily_returns) × √(trading_days)`
"""

MD = Metric(
    prefix="md",
    name="Max Drawdown",
    formula=pl.col("md"),
    scale=100.0,
)
"""Maximum Drawdown.

Largest peak-to-trough decline during the period, expressed as a negative
percentage.  A value of −30 means the series fell 30 % from its high before
recovering.

Formula: `min(close / cumulative_max - 1)`
"""

CALMAR = Metric(
    prefix="calmar",
    name="Calmar Ratio",
    formula=pl.when(pl.col("md").abs() > 0)
    .then(
        (
            (pl.col("last_nav") / pl.col("first_nav")) ** (pl.col("_td") / pl.col("n"))
            - 1.0
        )
        / pl.col("md").abs()
    )
    .otherwise(None),
)
"""Calmar Ratio.

CAGR divided by the absolute max drawdown.  Higher is better — a Calmar of 2
means the annualised return was twice the worst drawdown.

Formula: `CAGR / |max_drawdown|`
"""

VAR95 = Metric(
    prefix="var95",
    name="VaR 95%",
    formula=pl.col("var95"),
    scale=100.0,
)
"""Value at Risk — 95 % confidence.

The 5th-percentile daily return.  A VaR95 of −2 means on 95 % of days the
loss did not exceed 2 %.

Formula: `quantile(daily_returns, 0.05)`
"""

VAR99 = Metric(
    prefix="var99",
    name="VaR 99%",
    formula=pl.col("var99"),
    scale=100.0,
)
"""Value at Risk — 99 % confidence.

The 1st-percentile daily return.  More extreme than VaR95; a VaR99 of −4
means only 1 % of days saw a loss worse than 4 %.

Formula: `quantile(daily_returns, 0.01)`
"""

CVAR95 = Metric(
    prefix="cvar95",
    name="CVaR 95%",
    formula=pl.col("cvar95"),
    scale=100.0,
)
"""Conditional VaR (Expected Shortfall) — 95 %.

Average loss on the worst 5 % of days.  Always more negative than VaR95.
A CVaR95 of −3 means the average daily loss in the worst tail is 3 %.

Formula: `mean(daily_returns where return ≤ VaR95)`
"""

CVAR99 = Metric(
    prefix="cvar99",
    name="CVaR 99%",
    formula=pl.col("cvar99"),
    scale=100.0,
)
"""Conditional VaR (Expected Shortfall) — 99 %.

Average loss on the worst 1 % of days.  The most extreme tail-risk measure
available here.

Formula: `mean(daily_returns where return ≤ VaR99)`
"""

UI = Metric(
    prefix="ui",
    name="Ulcer Index",
    formula=pl.col("ui"),
    scale=100.0,
)
"""Ulcer Index.

Root-mean-square of drawdowns — captures both depth and duration of declines.
Lower is better.  A UI of 5 indicates moderate, sustained drawdown stress.

Formula: `√(mean(drawdown²))`
"""

BETA = Metric(
    prefix="beta",
    name="Beta",
    formula=pl.when(pl.col("var_b") > 0)
    .then(pl.col("cov_fb") / pl.col("var_b"))
    .otherwise(None),
)
"""Beta.

Sensitivity of the series to the benchmark.  A beta of 1.2 means the series
tends to move 1.2 % for every 1 % move in the benchmark.

Formula: `cov(r_fund, r_bench) / var(r_bench)`
"""

ALPHA = Metric(
    prefix="alpha",
    name="Alpha",
    formula=(
        pl.col("period_return")
        - (
            pl.col("rf_period")
            + pl.when(pl.col("var_b") > 0)
            .then(pl.col("cov_fb") / pl.col("var_b"))
            .otherwise(None)
            * (pl.col("bench_period_return") - pl.col("rf_period"))
        )
    ),
)
"""Jensen's Alpha.

Excess return over what CAPM predicts given the series' beta.  A positive
alpha means the series outperformed its risk-adjusted expectation.

Formula: `r_fund - (r_f + β × (r_bench - r_f))`
"""

R_SQ = Metric(
    prefix="r_sq",
    name="R-squared",
    formula=pl.col("corr_fb") ** 2,
)
"""R-squared.

Proportion of the series' variance explained by the benchmark.  Ranges 0–1.
An R² of 0.95 means 95 % of the series' movement tracks the benchmark.

Formula: `corr(r_fund, r_bench)²`
"""

IR = Metric(
    prefix="ir",
    name="Information Ratio",
    formula=pl.when(pl.col("std_diff") > 0)
    .then(pl.col("mean_diff") * pl.col("_td").sqrt() / pl.col("std_diff"))
    .otherwise(None),
)
"""Information Ratio.

Annualised excess return per unit of tracking error.  An IR above 0.5 is
generally considered good; above 1.0 is exceptional.

Formula: `mean(r_fund - r_bench) × √(trading_days) / std(r_fund - r_bench)`
"""

M2 = Metric(
    prefix="m2",
    name="M-squared",
    formula=pl.col("_rf")
    + pl.when(pl.col("std_fund") > 0)
    .then(
        (pl.col("mean_fund") * pl.col("_td") - pl.col("_rf"))
        / (pl.col("std_fund") * pl.col("_td").sqrt())
    )
    .otherwise(None)
    * pl.col("std_bench")
    * pl.col("_td").sqrt(),
)
"""Modigliani–Modigliani (M²) measure.

Risk-adjusted return expressed on the same scale as the benchmark.  If M² is
12 % and the benchmark returned 10 %, the series delivered 2 % more on a
risk-equivalent basis.

Formula: `r_f + sharpe_fund × σ_bench_annualised`
"""

SHARPE = Metric(
    prefix="sharpe",
    name="Sharpe Ratio",
    formula=pl.when(pl.col("std_ret") > 0)
    .then(
        (pl.col("ret_mean") * pl.col("_td") - pl.col("_rf"))
        / (pl.col("std_ret") * pl.col("_td").sqrt())
    )
    .otherwise(None),
)
"""Sharpe Ratio.

Annualised excess return per unit of total risk.  A Sharpe of 1 means each
unit of volatility was compensated by one unit of excess return; above 2 is
excellent.

Formula: `(mean(r) × trading_days - r_f) / (σ × √(trading_days))`
"""

SORTINO = Metric(
    prefix="sortino",
    name="Sortino Ratio",
    formula=pl.when(pl.col("downside_dev") > 0)
    .then(
        (pl.col("ret_mean") * pl.col("_td") - pl.col("_rf"))
        / (pl.col("downside_dev") * pl.col("_td").sqrt())
    )
    .otherwise(None),
)
"""Sortino Ratio.

Like Sharpe but penalises only downside volatility.  A Sortino of 3 means
the excess return was three times the downside deviation — the series earned
good returns without large drops.

Formula: `(mean(r) × trading_days - r_f) / (downside_dev × √(trading_days))`
"""

# ------------------------------------------------------------------
# Groups
# ------------------------------------------------------------------

BASIC_GROUP = MetricGroup(
    name="basic",
    metrics=(R, CAGR, SR, VOL),
)
"""Core return and hit-rate metrics derived from the close series alone."""

RISK_GROUP = MetricGroup(
    name="risk",
    metrics=(MD, CALMAR, VAR95, VAR99, CVAR95, CVAR99, UI),
)
"""Drawdown and tail-risk metrics derived from the close series alone."""

BENCHMARK_GROUP = MetricGroup(
    name="benchmark",
    metrics=(BETA, ALPHA, R_SQ, IR, M2),
)
"""Metrics that compare the series to a benchmark index."""

PERFORMANCE_GROUP = MetricGroup(
    name="performance",
    metrics=(SHARPE, SORTINO),
    frequencies=("yearly",),
)
"""Risk-adjusted performance ratios — computed yearly only."""

ALL_GROUPS: tuple[MetricGroup, ...] = (
    BASIC_GROUP,
    RISK_GROUP,
    BENCHMARK_GROUP,
    PERFORMANCE_GROUP,
)

METRIC_BY_PREFIX: dict[str, Metric] = {
    m.prefix: m for g in ALL_GROUPS for m in g.metrics
}

__all__ = [
    "ALL_GROUPS",
    "BASIC_GROUP",
    "BENCHMARK_GROUP",
    "DatabaseMetricsAdapter",
    "METRICS_TABLES",
    "METRIC_BY_PREFIX",
    "Frequency",
    "Metric",
    "MetricGroup",
    "MetricsBuilder",
    "MetricsConfig",
    "PERFORMANCE_GROUP",
    "RISK_GROUP",
    "all_periods",
    "metrics_columns",
    "period_order",
]


class MetricsBuilder:
    """Pure-polars metrics builder — no DuckDB dependency.

    Usage::

        result = MetricsBuilder(
            df,
            benchmark="NIFTY 50",
            frequency="yearly",
            metrics=["r", "cagr", "vol", "beta"],
        ).build()

    Parameters
    ----------
    df : pl.DataFrame
        Pivoted NAV prices: a ``date`` column (daily) plus one float column
        per scheme/index.  Column names become the scheme identifiers in the
        output.
    benchmark : str
        Column name in *df* used as the market benchmark for
        covariance-based metrics and coverage masking.
    frequency : Frequency
        ``"yearly"``, ``"quarterly"``, or ``"monthly"``.
    metrics : list[str] | None
        Which metrics to compute.  ``None`` computes all available for the
        chosen frequency.  Performance metrics (``sharpe``, ``sortino``) are
        only produced when ``frequency == "yearly"``.
    config : MetricsConfig | None
        Risk-free rate, trading days, start/end dates, coverage threshold.
    """

    def __init__(
        self,
        df: pl.DataFrame,
        benchmark: str,
        frequency: Frequency = "yearly",
        metrics: list[str] | list[Metric] | None = None,
        config: MetricsConfig | None = None,
    ) -> None:
        self._raw_df = df
        self.benchmark = benchmark
        self.frequency: Frequency = frequency
        self.config = config or MetricsConfig()

        if metrics is None:
            # All metrics whose group supports this frequency.
            self._metrics = [
                m for g in ALL_GROUPS if frequency in g.frequencies for m in g.metrics
            ]
        else:
            resolved: list[Metric] = []
            for item in metrics:
                if isinstance(item, Metric):
                    resolved.append(item)
                else:
                    resolved.append(METRIC_BY_PREFIX[item])
            self._metrics = resolved

    # ----------------------------------------------------------- data prep

    def _to_long(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Unpivot the wide input into ``(scheme, date, nav, ret)`` long form.

        Returns ``(all_rows, bench)`` where *bench* is the benchmark rows only.
        """
        scheme_cols = [c for c in self._raw_df.columns if c != "date"]
        long = self._raw_df.unpivot(
            index="date",
            on=scheme_cols,
            variable_name="scheme",
            value_name="nav",
        )
        long = long.filter(pl.col("nav").is_not_null() & (pl.col("nav") > 0))
        long = long.sort(["scheme", "date"])
        long = long.with_columns(
            ret=(pl.col("nav") / pl.col("nav").shift(1).over("scheme") - 1)
        )
        # Date filter
        start = self.config.start_date
        long = long.filter(pl.col("date") >= pl.lit(start))

        bench = long.filter(pl.col("scheme") == self.benchmark)
        return long, bench

    # ------------------------------------------------------------- period keys

    @staticmethod
    def _add_period(df: pl.DataFrame, freq: Frequency) -> pl.DataFrame:
        """Adds a string ``period`` column like ``"2026"`` / ``"2026_1"`` /
        ``"2026_03"`` based on ``date``.
        """
        year = pl.col("date").dt.year()
        if freq == "yearly":
            period = year.cast(pl.Utf8)
        elif freq == "quarterly":
            quarter = pl.col("date").dt.quarter().cast(pl.Utf8)
            period = year.cast(pl.Utf8) + pl.lit("_") + quarter
        else:  # monthly
            month = pl.col("date").dt.month().cast(pl.Utf8).str.zfill(2)
            period = year.cast(pl.Utf8) + pl.lit("_") + month
        return df.with_columns(period=period)

    # --------------------------------------------------------- coverage mask

    def _coverage_mask(
        self, grouped: pl.DataFrame, bench_counts: pl.DataFrame, freq: Frequency
    ) -> pl.DataFrame:
        """Add ``_valid`` bool column; True iff yearly or n>=90% of benchmark n."""
        out = grouped.join(bench_counts, on="period", how="left")
        if freq == "yearly":
            out = out.with_columns(_valid=pl.lit(True))
        else:
            thr = self.config.coverage_threshold
            out = out.with_columns(_valid=(pl.col("n") >= (pl.col("bench_n") * thr)))
        return out

    # ------------------------------------------------------------- per-group

    def _aggregate_fund(self, df: pl.DataFrame) -> pl.DataFrame:
        """Per (scheme, period) aggregates derived from fund rows alone."""
        g = df.group_by(["scheme", "period"]).agg(
            n=pl.len(),
            first_nav=pl.col("nav").sort_by("date").first(),
            last_nav=pl.col("nav").sort_by("date").last(),
            first_date=pl.col("date").min(),
            last_date=pl.col("date").max(),
            ret_std=pl.col("ret").std(ddof=1),
            ret_mean=pl.col("ret").mean(),
            pos_count=(pl.col("ret") > 0).sum(),
            ret_count=pl.col("ret").is_not_null().sum(),
            var95=pl.col("ret").quantile(0.05),
            var99=pl.col("ret").quantile(0.01),
            cvar95=pl.col("ret")
            .filter(pl.col("ret") <= pl.col("ret").quantile(0.05))
            .mean(),
            cvar99=pl.col("ret")
            .filter(pl.col("ret") <= pl.col("ret").quantile(0.01))
            .mean(),
        )
        return g

    def _aggregate_drawdowns(self, df: pl.DataFrame) -> pl.DataFrame:
        """Per (scheme, period) max drawdown and ulcer index using nav series."""
        dd = (
            df.sort(["scheme", "period", "date"])
            .with_columns(
                _cummax=pl.col("nav").cum_max().over(["scheme", "period"]),
            )
            .with_columns(
                _dd=(pl.col("nav") / pl.col("_cummax") - 1.0),
            )
            .group_by(["scheme", "period"])
            .agg(
                md=pl.col("_dd").min(),
                ui=(pl.col("_dd") ** 2).mean().sqrt(),
            )
        )
        return dd

    # ---------------------------------------------------------- metric build

    def _apply_metrics(
        self,
        df: pl.DataFrame,
        stage_metrics: list[Metric],
    ) -> pl.DataFrame:
        """Apply formula, validity mask, and scale for a list of metrics."""
        # Inject config values so metric formulas can reference them.
        df = df.with_columns(
            pl.lit(float(self.config.trading_days)).alias("_td"),
            pl.lit(self.config.risk_free_rate).alias("_rf"),
        )
        # Compute each metric from its formula.
        df = df.with_columns([m.formula.alias(m.prefix) for m in stage_metrics])
        # Apply validity mask (if present).
        if "_valid" in df.columns:
            df = df.with_columns(
                [
                    pl.when(pl.col("_valid"))
                    .then(pl.col(m.prefix))
                    .otherwise(None)
                    .alias(m.prefix)
                    for m in stage_metrics
                ]
            )
        # Apply scaling.
        scaled = [m for m in stage_metrics if m.scale != 1.0]
        if scaled:
            df = df.with_columns(
                [(pl.col(m.prefix) * m.scale).alias(m.prefix) for m in scaled]
            )
        return df

    def _compute_basic_and_risk(
        self,
        fund_df: pl.DataFrame,
        bench_counts: pl.DataFrame,
        freq: Frequency,
        stage_metrics: list[Metric],
    ) -> pl.DataFrame:
        """Return long-form aggregates joined with drawdowns and mask."""
        agg = self._aggregate_fund(fund_df)
        dd = self._aggregate_drawdowns(fund_df)
        joined = agg.join(dd, on=["scheme", "period"], how="left")
        joined = self._coverage_mask(joined, bench_counts, freq)
        return self._apply_metrics(joined, stage_metrics)

    def _compute_benchmark(
        self,
        fund_df: pl.DataFrame,
        bench_df: pl.DataFrame,
        bench_counts: pl.DataFrame,
        freq: Frequency,
        stage_metrics: list[Metric],
    ) -> pl.DataFrame:
        """Per (scheme, period) benchmark-relative metrics."""
        bench_slim = bench_df.select(
            "date", pl.col("ret").alias("bench_ret"), pl.col("nav").alias("bench_nav")
        )
        aligned = fund_df.join(bench_slim, on="date", how="inner")
        aligned = aligned.filter(
            pl.col("ret").is_not_null() & pl.col("bench_ret").is_not_null()
        )

        td = float(self.config.trading_days)
        rf = self.config.risk_free_rate

        grouped = aligned.group_by(["scheme", "period"]).agg(
            n=pl.len(),
            fund_first=pl.col("nav").sort_by("date").first(),
            fund_last=pl.col("nav").sort_by("date").last(),
            bench_first=pl.col("bench_nav").sort_by("date").first(),
            bench_last=pl.col("bench_nav").sort_by("date").last(),
            cov_fb=pl.cov(pl.col("ret"), pl.col("bench_ret"), ddof=1),
            var_b=pl.col("bench_ret").var(ddof=1),
            corr_fb=pl.corr(pl.col("ret"), pl.col("bench_ret")),
            std_diff=(pl.col("ret") - pl.col("bench_ret")).std(ddof=1),
            std_bench=pl.col("bench_ret").std(ddof=1),
            std_fund=pl.col("ret").std(ddof=1),
            mean_fund=pl.col("ret").mean(),
            mean_bench=pl.col("bench_ret").mean(),
            mean_diff=(pl.col("ret") - pl.col("bench_ret")).mean(),
        )
        grouped = self._coverage_mask(grouped, bench_counts, freq)

        # Derive intermediate columns needed by metric formulas.
        grouped = grouped.with_columns(
            period_return=(pl.col("fund_last") / pl.col("fund_first") - 1.0),
            bench_period_return=(pl.col("bench_last") / pl.col("bench_first") - 1.0),
            rf_period=rf * pl.col("n") / td,
        )
        return self._apply_metrics(grouped, stage_metrics)

    def _compute_performance(
        self, fund_df: pl.DataFrame, stage_metrics: list[Metric]
    ) -> pl.DataFrame:
        """Yearly annualised Sharpe + Sortino per (scheme, period).

        Both ratios use the standard form
        ``(mean(ret) * td - rf) / (sigma * sqrt(td))`` so the value is the
        annualised ratio regardless of how many trading days fall inside the
        period (avoids the partial-year scale mismatch).

        Sortino's downside deviation uses the textbook target-semivariance
        with target = 0: ``sqrt(sum(min(ret, 0)**2) / (n - 1))``. This
        differs from ``std()`` of a masked series in that it does not
        subtract the mean, so all-positive periods correctly produce 0
        (Sortino NULL) and noisy periods get a stable, well-scaled
        denominator.
        """
        g = fund_df.group_by(["scheme", "period"]).agg(
            n=pl.len(),
            ret_mean=pl.col("ret").mean(),
            std_ret=pl.col("ret").std(ddof=1),
            neg_sq_sum=pl.when(pl.col("ret") < 0)
            .then(pl.col("ret") ** 2)
            .otherwise(0.0)
            .sum(),
            ret_count=pl.col("ret").is_not_null().sum(),
        )
        g = g.with_columns(
            downside_dev=pl.when(pl.col("ret_count") > 1)
            .then((pl.col("neg_sq_sum") / (pl.col("ret_count") - 1)).sqrt())
            .otherwise(None),
        )
        return self._apply_metrics(g, stage_metrics)

    # --------------------------------------------------------------- pivot

    def _pivot_wide(
        self,
        long_df: pl.DataFrame,
        metrics: tuple[str, ...],
        freq: Frequency,
    ) -> pl.DataFrame:
        """Pivot long (scheme, period, <metric>...) to one row per scheme.

        The output has *exactly* the columns implied by
        :meth:`MetricsConfig.periods` (latest-first per metric), padded with
        NULL columns for periods that do not appear in ``long_df``. This
        keeps the wide layout stable across runs.
        """
        expected_periods = period_order(freq, self.config.periods(freq))
        wide = long_df.select(["scheme"]).unique().sort("scheme")
        for metric in metrics:
            sub = long_df.select(["scheme", "period", metric])
            pv = sub.pivot(on="period", index="scheme", values=metric)
            rename = {p: f"{metric}_{p}" for p in expected_periods if p in pv.columns}
            pv = pv.rename(rename)
            # Pad missing period columns with NULL.
            missing = [
                f"{metric}_{p}"
                for p in expected_periods
                if f"{metric}_{p}" not in pv.columns
            ]
            if missing:
                pv = pv.with_columns(
                    [pl.lit(None, dtype=pl.Float64).alias(c) for c in missing]
                )
            ordered = [f"{metric}_{p}" for p in expected_periods]
            pv = pv.select(["scheme", *ordered])
            wide = wide.join(pv, on="scheme", how="left")
        return wide

    # ------------------------------------------------------------- build

    def build(self) -> pl.DataFrame:
        """Compute all requested metrics and return a wide ``pl.DataFrame``.

        One row per scheme (benchmark included for basic/risk/performance
        metrics), columns are ``scheme`` plus ``<metric>_<period>``.
        """
        funds, bench = self._to_long()
        freq = self.frequency

        if funds.is_empty():
            LOGGER.info("METRICS_BUILD_SKIP. Empty fund input.")
            return pl.DataFrame({"scheme": []})

        fund_p = self._add_period(funds, freq)
        bench_p = self._add_period(bench, freq)

        bench_counts = (
            bench_p.group_by("period")
            .agg(bench_n=pl.len())
            .select(["period", "bench_n"])
        )

        # Partition requested metrics by compute path using group membership.
        _basic_set = {m.prefix for m in BASIC_GROUP.metrics}
        _risk_set = {m.prefix for m in RISK_GROUP.metrics}
        _bench_set = {m.prefix for m in BENCHMARK_GROUP.metrics}
        _perf_set = {m.prefix for m in PERFORMANCE_GROUP.metrics}

        basic_risk_metrics = [
            m for m in self._metrics if m.prefix in _basic_set | _risk_set
        ]
        bench_metrics = [m for m in self._metrics if m.prefix in _bench_set]
        perf_metrics = [m for m in self._metrics if m.prefix in _perf_set]

        parts: list[pl.DataFrame] = []

        # Basic + Risk share the same pre-aggregated df.
        if basic_risk_metrics:
            basic_risk = self._compute_basic_and_risk(
                fund_p, bench_counts, freq, basic_risk_metrics
            )
            prefixes = tuple(m.prefix for m in basic_risk_metrics)
            parts.append(self._pivot_wide(basic_risk, prefixes, freq))

        # Benchmark
        if bench_metrics and not bench.is_empty():
            fund_non_bench = fund_p.filter(pl.col("scheme") != self.benchmark)
            if not fund_non_bench.is_empty():
                bench_result = self._compute_benchmark(
                    fund_non_bench, bench_p, bench_counts, freq, bench_metrics
                )
                prefixes = tuple(m.prefix for m in bench_metrics)
                parts.append(self._pivot_wide(bench_result, prefixes, freq))

        # Performance (yearly only)
        if perf_metrics and freq == "yearly":
            perf = self._compute_performance(fund_p, perf_metrics)
            prefixes = tuple(m.prefix for m in perf_metrics)
            parts.append(self._pivot_wide(perf, prefixes, freq))

        if not parts:
            return pl.DataFrame({"scheme": funds.get_column("scheme").unique().sort()})

        # Merge all parts on scheme
        result = parts[0]
        for part in parts[1:]:
            result = result.join(part, on="scheme", how="full", coalesce=True)
        return result


# ======================================================================
# DuckDB adapter — keeps Database.build_metrics working
# ======================================================================


class DatabaseMetricsAdapter:
    """Loads NAV data from DuckDB, runs :class:`MetricsBuilder`, writes back.

    This is the bridge between the pure-polars builder and the existing
    ``metrics_*`` table / per-period view infrastructure.

    Usage::

        DatabaseMetricsAdapter(db, benchmark_sd_id=120716, config=cfg).build()
    """

    def __init__(
        self,
        db: Database,
        benchmark_sd_id: int = 120716,
        config: MetricsConfig | None = None,
    ) -> None:
        self.db = db
        self.benchmark_sd_id = benchmark_sd_id
        self.config = config or MetricsConfig()

    # ------------------------------------------------------------------ load

    def _load_pivoted(self) -> pl.DataFrame:
        """Load NAV from DuckDB as a pivoted df (date + one column per sd_id).

        The benchmark ``sd_id`` column is renamed to its string
        representation so it can be used as a benchmark name.
        """
        from ..derived import NavView, PlansView

        sql = f"""
        SELECT n.sd_id, n.date, n.nav
        FROM {NavView.name()} n
        WHERE n.date >= DATE '{self.config.start_date.isoformat()}'
          AND (n.sd_id IN (SELECT sd_id FROM {PlansView.name()}) OR n.sd_id = ?)
          AND n.nav > 0
        ORDER BY n.sd_id, n.date
        """
        long = self.db.conn.execute(sql, [self.benchmark_sd_id]).pl()
        if long.is_empty():
            return pl.DataFrame()
        long = long.with_columns(
            pl.col("nav").cast(pl.Float64),
            pl.col("sd_id").cast(pl.Utf8).alias("sd_id"),
        )
        pivoted = long.pivot(on="sd_id", index="date", values="nav")
        return pivoted

    # ------------------------------------------------------------------- io

    def _write_table(
        self,
        name: str,
        metrics: tuple[str, ...],
        freq: Frequency,
        df: pl.DataFrame,
    ) -> None:
        """``DELETE FROM`` + ``INSERT INTO`` with explicit column ordering.

        Translates scheme (string sd_id) back to integer sd_id and joins
        the scheme name from ``plans``.
        """
        from ..derived import PlansView

        expected_periods = period_order(freq, self.config.periods(freq))
        metric_cols = metrics_columns(metrics, expected_periods)
        insert_cols = ["sd_id", "scheme", *metric_cols]

        # The builder output has ``scheme`` = str(sd_id); rename for insert.
        df = df.with_columns(pl.col("scheme").cast(pl.Int64).alias("sd_id"))
        src_cols = ["sd_id", *metric_cols]
        # Pad missing metric columns with NULL
        for c in metric_cols:
            if c not in df.columns:
                df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias(c))

        self.db.conn.execute(f"DELETE FROM {name}")
        arrow = df.select(src_cols).to_arrow()
        self.db.conn.register("__metrics_tmp", arrow)
        try:
            insert_sql = (
                f"INSERT INTO {name} ({', '.join(insert_cols)})\n"
                f"SELECT t.sd_id, p.scheme, "
                f"{', '.join('t.' + c for c in metric_cols)}\n"
                f"FROM __metrics_tmp t "
                f"LEFT JOIN {PlansView.name()} p ON p.sd_id = t.sd_id"
            )
            self.db.conn.execute(insert_sql)
        finally:
            self.db.conn.unregister("__metrics_tmp")
        LOGGER.info("METRICS_WRITE. TABLE=%s", name)

    # ------------------------------------------------------------- build all

    def build(self) -> None:
        """Full metrics build cycle: load → compute → write → views."""
        LOGGER.info(
            "METRICS_BUILD_START. BENCH=%d RF=%.4f START=%s END=%s",
            self.benchmark_sd_id,
            self.config.risk_free_rate,
            self.config.start_date.isoformat(),
            self.config.end_date.isoformat(),
        )
        pivoted = self._load_pivoted()
        if pivoted.is_empty():
            LOGGER.info("METRICS_BUILD_SKIP. Empty nav input.")
            return

        bench_col = str(self.benchmark_sd_id)
        has_bench = bench_col in pivoted.columns

        if not has_bench:
            LOGGER.warning(
                "METRICS_BUILD_NO_BENCH. sd_id=%d missing from nav; "
                "benchmark metrics will be empty.",
                self.benchmark_sd_id,
            )

        for freq in _FREQUENCIES:
            # Basic + Risk (share a single builder call)
            basic_risk = list(BASIC_GROUP.metrics) + list(RISK_GROUP.metrics)
            builder = MetricsBuilder(
                pivoted,
                benchmark=bench_col,
                frequency=freq,
                metrics=basic_risk,
                config=self.config,
            )
            result = builder.build()

            if not result.is_empty():
                filtered = result.filter(pl.col("scheme") != bench_col)
                if filtered.is_empty():
                    LOGGER.info(
                        "METRICS_WRITE_SKIP_BENCH. TABLE=%s FREQ=%s",
                        basic_table(freq).name(),
                        freq,
                    )
                else:
                    basic_prefixes = tuple(m.prefix for m in BASIC_GROUP.metrics)
                    self._write_table(
                        basic_table(freq).name(), basic_prefixes, freq, filtered
                    )
                    risk_prefixes = tuple(m.prefix for m in RISK_GROUP.metrics)
                    self._write_table(
                        risk_table(freq).name(), risk_prefixes, freq, filtered
                    )

            # Benchmark
            if has_bench:
                bench_builder = MetricsBuilder(
                    pivoted,
                    benchmark=bench_col,
                    frequency=freq,
                    metrics=list(BENCHMARK_GROUP.metrics),
                    config=self.config,
                )
                bench_result = bench_builder.build()
                if not bench_result.is_empty():
                    bench_prefixes = tuple(m.prefix for m in BENCHMARK_GROUP.metrics)
                    self._write_table(
                        benchmark_table(freq).name(),
                        bench_prefixes,
                        freq,
                        bench_result,
                    )

        # Performance: yearly only.
        perf_builder = MetricsBuilder(
            pivoted,
            benchmark=bench_col,
            frequency="yearly",
            metrics=list(PERFORMANCE_GROUP.metrics),
            config=self.config,
        )
        perf_result = perf_builder.build()
        if not perf_result.is_empty():
            perf_result = perf_result.filter(pl.col("scheme") != bench_col)
            if perf_result.is_empty():
                LOGGER.info("PERFORMANCE_SKIP_BENCH_ONLY")
            else:
                perf_prefixes = tuple(m.prefix for m in PERFORMANCE_GROUP.metrics)
                self._write_table(
                    MetricsPerformanceYearlyTable.name(),
                    perf_prefixes,
                    "yearly",
                    perf_result,
                )
        LOGGER.info("METRICS_BUILD_SUCCESS")
