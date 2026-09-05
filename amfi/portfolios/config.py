"""Configuration loader for user-defined synthetic portfolios."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_t
from pathlib import Path
from typing import Any

import yaml

from ..error import AppConfigError
from ..utils import LOGGER


@dataclass(frozen=True)
class PortfolioConfig:
    """A single portfolio declared in ``config.yml``."""

    name: str
    index: int
    weights: dict[int, float]
    fund_house_id: int | None = None
    fund_house: str | None = None
    category: str | None = None
    subcategory: str | None = None
    start_date: date_t | None = None

    @property
    def synthetic_id(self) -> int:
        return 9_000_000 + self.index + 1

    @property
    def sd_id(self) -> int:
        return self.synthetic_id

    @property
    def scheme_id(self) -> int:
        return self.synthetic_id

    @property
    def effective_fund_house_id(self) -> int:
        if self.fund_house_id is not None:
            return self.fund_house_id
        return self.synthetic_id

    @property
    def effective_fund_house(self) -> str:
        return self.fund_house or self.name

    @property
    def effective_category(self) -> str:
        return (self.category or "equity").strip().lower()

    @property
    def effective_subcategory(self) -> str:
        return (self.subcategory or "multi cap").strip().lower()


def load_portfolios(config_path: Path | str | None = None) -> list[PortfolioConfig]:
    """Parse ``config.yml`` and return validated :class:`PortfolioConfig` instances."""
    path = Path(config_path or "config.yml")
    if not path.exists():
        LOGGER.info("PORTFOLIO_LOAD_SKIP. path=%s reason=FILE_NOT_FOUND", path)
        return []

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AppConfigError(str(path), "YAML_PARSE_ERROR", str(exc)) from exc

    if not isinstance(data, dict):
        LOGGER.info("PORTFOLIO_LOAD_SKIP. path=%s reason=EMPTY_OR_NON_MAPPING", path)
        return []

    raw = data.get("portfolios")
    if raw is None:
        LOGGER.info("PORTFOLIO_LOAD_SKIP. path=%s reason=NO_PORTFOLIOS_KEY", path)
        return []
    if not isinstance(raw, dict):
        raise AppConfigError("portfolios", "MUST_BE_MAPPING", raw)

    out: list[PortfolioConfig] = []
    for idx, (name, body) in enumerate(raw.items()):
        if not isinstance(body, dict):
            raise AppConfigError(
                f"portfolios[{name!r}]", "MUST_BE_MAPPING", body
            )

        weights_raw = body.get("weights")
        if not isinstance(weights_raw, dict) or not weights_raw:
            raise AppConfigError(
                f"portfolios[{name!r}].weights",
                "MUST_BE_NONEMPTY_MAPPING",
                weights_raw,
            )
        weights: dict[int, float] = {}
        for sd_key, amount in weights_raw.items():
            try:
                sd_id = int(sd_key)
            except (TypeError, ValueError) as e:
                raise AppConfigError(
                    f"portfolios[{name!r}].weights key", "MUST_BE_INT", sd_key
                ) from e
            if not isinstance(amount, (int, float)) or amount <= 0:
                raise AppConfigError(
                    f"portfolios[{name!r}].weights[{sd_id}]",
                    "MUST_BE_POSITIVE_NUMBER",
                    amount,
                )
            weights[sd_id] = float(amount)

        start_raw = body.get("start_date")
        start_date: date_t | None
        if start_raw is None:
            start_date = None
        elif isinstance(start_raw, date_t):
            start_date = start_raw
        elif isinstance(start_raw, str):
            start_date = date_t.fromisoformat(start_raw)
        else:
            raise AppConfigError(
                f"portfolios[{name!r}].start_date",
                "MUST_BE_DATE_OR_ISO_STRING",
                start_raw,
            )

        fund_house_id_raw = body.get("fund_house_id")
        if fund_house_id_raw is not None and not isinstance(fund_house_id_raw, int):
            raise AppConfigError(
                f"portfolios[{name!r}].fund_house_id",
                "MUST_BE_INT",
                fund_house_id_raw,
            )

        out.append(
            PortfolioConfig(
                name=name,
                index=idx,
                weights=weights,
                fund_house_id=fund_house_id_raw,
                fund_house=body.get("fund_house"),
                category=body.get("category"),
                subcategory=body.get("subcategory"),
                start_date=start_date,
            )
        )
    LOGGER.info("PORTFOLIO_LOAD_SUCCESS. path=%s count=%d", path, len(out))
    return out
