import asyncio
import json
from datetime import datetime

import duckdb
import httpx
import polars as pl

url = "https://www.nseindia.com/api/historicalOR/indicesHistory"
FROM_DATE = "01-01-2000"
TO_DATE = datetime.now().strftime("%d-%m-%Y")
# ?indexType={index}&from={from_date}&to={to_date}&csv=true"


def create_indices_table() -> duckdb.DuckDBPyConnection:
    """
    Create the indices table in DuckDB.
    """
    conn = duckdb.connect("indices.duckdb")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS indices (
            symbol VARCHAR,
            name VARCHAR,
            open DOUBLE,
            high DOUBLE,
            close DOUBLE,
            low DOUBLE,
            turnover DOUBLE,
            traded_qty BIGINT,
            date DATE,
            timestamp TIMESTAMP WITH TIME ZONE,
            inserted_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    return conn


async def fetch_index_data(index: str, from_date: str, to_date: str) -> pl.DataFrame:
    """
    Raw function to fetch index data from NSE. NSE limits the number of days to 365.
    """
    params = {"indexType": index, "from": from_date, "to": to_date, "csv": "true"}
    response = httpx.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    data = json.loads(response.text)
    if "error" in data:
        raise Exception(f"Error fetching index data: {data['message']}")
    data = data["data"]
    df = pl.DataFrame(data, infer_schema_length=1000)
    if len(df) > 0:
        df = df.with_columns(
            [
                pl.col("EOD_OPEN_INDEX_VAL")
                .cast(pl.Float64, strict=False)
                .alias("EOD_OPEN_INDEX_VAL"),
                pl.col("EOD_HIGH_INDEX_VAL")
                .cast(pl.Float64, strict=False)
                .alias("EOD_HIGH_INDEX_VAL"),
                pl.col("EOD_LOW_INDEX_VAL")
                .cast(pl.Float64, strict=False)
                .alias("EOD_LOW_INDEX_VAL"),
                pl.col("EOD_CLOSE_INDEX_VAL")
                .cast(pl.Float64, strict=False)
                .alias("EOD_CLOSE_INDEX_VAL"),
                pl.col("HIT_TURN_OVER")
                .cast(pl.Float64, strict=False)
                .alias("HIT_TURN_OVER"),
                pl.col("HIT_TRADED_QTY")
                .cast(pl.Int64, strict=False)
                .alias("HIT_TRADED_QTY"),
                pl.col("EOD_TIMESTAMP").str.to_date("%d-%b-%Y").alias("EOD_TIMESTAMP"),
                pl.col("HI_TIMESTAMP")
                .str.to_datetime("%Y-%m-%dT%H:%M:%S%.3f%z")
                .alias("HI_TIMESTAMP"),
            ]
        )
    return df


async def fetch_full_index_data(symbol: str, index: str) -> None:
    """
    Fetch full index data for a given index.

    Args:
        index: The index to fetch data for.

    Returns:
        A DataFrame containing the full index data.
    """
    conn = duckdb.connect("indices.duckdb")

    all_dfs = []
    for year in range(2000, datetime.now().year + 1):
        from_date = f"01-01-{year}"
        to_date = f"31-12-{year}"

        # Check if symbol already has data in db for this date range
        result = conn.execute(
            "SELECT COUNT(*) FROM indices WHERE symbol = ? AND date >= ? AND date <= ?",
            [symbol, f"{year}-01-01", f"{year}-12-31"],
        ).fetchone()

        if result is not None and result[0] > 5:
            continue

        df = await fetch_index_data(index, from_date, to_date)
        if len(df) == 0:
            # print(f"No data found for {index} from {from_date} to {to_date}")
            continue
        all_dfs.append(df)
    if not all_dfs:
        print(f"No data fetched for {index}")
        return
    data = pl.concat(all_dfs)

    # Transform dataframe to match schema
    data = data.with_columns(
        [
            pl.lit(symbol).alias("symbol"),
            pl.col("EOD_INDEX_NAME").alias("name"),
            pl.col("EOD_OPEN_INDEX_VAL").alias("open"),
            pl.col("EOD_HIGH_INDEX_VAL").alias("high"),
            pl.col("EOD_CLOSE_INDEX_VAL").alias("close"),
            pl.col("EOD_LOW_INDEX_VAL").alias("low"),
            pl.col("HIT_TURN_OVER").alias("turnover"),
            pl.col("HIT_TRADED_QTY").alias("traded_qty"),
            pl.col("EOD_TIMESTAMP").alias("date"),
            pl.col("HI_TIMESTAMP").alias("timestamp"),
        ]
    )

    # Select only the required columns
    data = data.select(
        [
            "symbol",
            "name",
            "open",
            "high",
            "close",
            "low",
            "turnover",
            "traded_qty",
            "date",
            "timestamp",
        ]
    )

    # Insert into DuckDB (exclude inserted_ts, it has a default)
    conn.execute(
        "INSERT INTO indices "
        "(symbol, name, open, high, close, low, turnover, traded_qty, date, timestamp) "
        "SELECT * FROM data"
    )
    conn.close()


async def main() -> None:
    indices = {
        # Cap-weighted
        "n50": "NIFTY 50",
        "nn50": "NIFTY NEXT 50",
        "n100": "NIFTY 100",
        "n200": "NIFTY 200",
        "n500": "NIFTY 500",
        "nfpi150": "NIFTY INDIA FPI 150",
        "nlm250": "NIFTY LARGEMIDCAP 250",
        "nm50": "NIFTY MIDCAP 50",
        "nm100": "NIFTY MIDCAP 100",
        "nm150": "NIFTY MIDCAP 150",
        "ns50": "NIFTY SMALLCAP 50",
        "ns100": "NIFTY SMALLCAP 100",
        "ns250": "NIFTY SMALLCAP 250",
        "nms400": "NIFTY MIDSMALLCAP 400",
        "nmc250": "NIFTY MICROCAP 250",
        "ntm": "NIFTY TOTAL MARKET",
        "nlm500e": "NIFTY500 LARGEMIDSMALL EQUAL-CAP WEIGHTED",
        "n500_50_25_25": "NIFTY500 MULTICAP 50:25:25",
        # Sector
        "auto": "NIFTY AUTO",
        "bank": "NIFTY BANK",
        "chem": "NIFTY CHEMICALS",
        "cons_dur": "NIFTY CONSUMER DURABLES",
        "fin_ser": "NIFTY FINANCIAL SERVICES",
        "fin_ser_ex_bank": "NIFTY FINANCIAL SERVICES EX-BANK",
        "fin_ser_25_50": "NIFTY FINANCIAL SERVICES 25/50",
        "fmcg": "NIFTY FMCG",
        "healthcare": "NIFTY HEALTHCARE INDEX",
        "it": "NIFTY IT",
        "media": "NIFTY MEDIA",
        "metal": "NIFTY METAL",
        "ms_healthcare": "NIFTY MIDSMALL HEALTHCARE",
        "ms_fin_ser": "NIFTY MIDSMALL FINANCIAL SERVICES",
        "ms_it_telecom": "NIFTY MIDSMALL IT & TELECOM",
        "oil_gas": "NIFTY OIL & GAS",
        "pharma": "NIFTY PHARMA",
        "psu_bank": "NIFTY PSU BANK",
        "priv_bank": "NIFTY PRIVATE BANK",
        "realty": "NIFTY REALTY",
        "n500_healthcare": "NIFTY500 HEALTHCARE",
        # Thematic
        "cap_mkt": "NIFTY CAPITAL MARKETS",
        "commodities": "NIFTY COMMODITIES",
        "cons": "NIFTY INDIA CONSUMPTION",
        "core_housing": "NIFTY CORE HOUSING",
        "maatr": "NIFTY INDIA SELECT 5 CORPORATE GROUPS (MAATR)",
        "cpse": "NIFTY CPSE",
        "energy": "NIFTY ENERGY",
        "ev": "NIFTY EV & NEW AGE AUTOMOTIVE",
        "housing": "NIFTY HOUSING",
        "defense": "NIFTY INDIA DEFENCE",
        "digital": "NIFTY INDIA DIGITAL",
        "tourism": "NIFTY INDIA TOURISM",
        "mfg": "NIFTY INDIA MANUFACTURING",
        "infra": "NIFTY INFRASTRUCTURE",
        "infra_logistics": "NIFTY INDIA INFRASTRUCTURE & LOGISTICS",
        "internet": "NIFTY INDIA INTERNET",
        "ipo": "NIFTY IPO",
        "m_liquid15": "NIFTY MIDCAP LIQUID 15",
        "mnc": "NIFTY MNC",
        "mobility": "NIFTY MOBILITY",
        "ms_consumption": "NIFTY MIDSMALL INDIA CONSUMPTION",
        "n500_infra_50_30_20": "NIFTY500 MULTICAP INFRASTRUCTURE 50:30:20",
        "n500_mfg_50_30_20": "NIFTY500 MULTICAP INDIA MANUFACTURING 50:30:20",
        "cons_new_age": "NIFTY INDIA NEW AGE CONSUMPTION",
        "cons_non_cyclical": "NIFTY NON-CYCLICAL CONSUMER",
        "pse": "NIFTY PSE",
        "psu_railways": "NIFTY INDIA RAILWAYS PSU",
        "rural": "NIFTY RURAL",
        "services": "NIFTY SERVICES SECTOR",
        "shariah_25": "NIFTY SHARIAH 25",
        "sme_emerge": "NIFTY SME EMERGE",
        "tata_25": "NIFTY INDIA CORPORATE GROUP INDEX - TATA GROUP 25% CAP",
        "transportation_logistics": "NIFTY TRANSPORTATION & LOGISTICS",
        "waves": "NIFTY WAVES",
        "enhanced_esg": "NIFTY100 ENHANCED ESG",
        "esg": "NIFTY100 ESG",
        "liquid15": "NIFTY100 LIQUID 15",
        "shariah_50": "NIFTY50 SHARIAH",
        "shariah_500": "NIFTY500 SHARIAH",
        "conglomerate_50": "NIFTY CONGLOMERATE 50",
        "ab_25": "NIFTY INDIA CORPORATE GROUP INDEX - ADITYA BIRLA GROUP",
        "mahindra_25": "NIFTY INDIA CORPORATE GROUP INDEX - MAHINDRA GROUP",
        "reits_invits": "NIFTY REITS & INVITS",
        # Strategy
        "a_50": "NIFTY ALPHA 50",
        "alv_30": "NIFTY ALPHA LOW-VOLATILITY 30",
        "aqlv_30": "NIFTY ALPHA QUALITY LOW-VOLATILITY 30",
        "aqvlv_30": "NIFTY ALPHA QUALITY VALUE LOW-VOLATILITY 30",
        "div_50": "NIFTY DIVIDEND OPPORTUNITIES 50",
        "growth_sectors_15": "NIFTY GROWTH SECTORS 15",
        "b_50": "NIFTY HIGH BETA 50",
        "lv_50": "NIFTY LOW VOLATILITY 50",
        "mq_50": "NIFTY MIDCAP150 QUALITY 50",
        "mcmq_50": "NIFTY500 MULTICAP MOMENTUM QUALITY 50",
        "qlv_30": "NIFTY QUALITY LOW-VOLATILITY 30",
        "sq_50": "NIFTY SMALLCAP250 QUALITY 50",
        "tmq_50": "NIFTY TOTAL MARKET MOMENTUM QUALITY 50",
        "t10ew": "NIFTY TOP 10 EQUAL WEIGHT",
        "t15ew": "NIFTY TOP 15 EQUAL WEIGHT",
        "t20ew": "NIFTY TOP 20 EQUAL WEIGHT",
        "n100a30": "NIFTY100 ALPHA 30",
        "n100ew": "NIFTY100 EQUAL WEIGHT",
        "n100lv30": "NIFTY100 LOW VOLATILITY 30",
        "n100q30": "NIFTY100 QUALITY 30",
        "n200a30": "NIFTY200 ALPHA 30",
        "n200q30": "NIFTY200 QUALITY 30",
        "n200v30": "NIFTY200 VALUE 30",
        "n200m30": "NIFTY200 MOMENTUM 30",
        "n50dp": "NIFTY50 DIVIDEND POINTS",
        "n50ew": "NIFTY50 EQUAL WEIGHT",
        "n50pr1x": "NIFTY50 PR 1X INVERSE",
        "n50pr2x": "NIFTY50 PR 2X LEVERAGE",
        "n50tr1x": "NIFTY50 TR 1X INVERSE",
        "n50tr2x": "NIFTY50 TR 2X LEVERAGE",
        "n50v20": "NIFTY50 VALUE 20",
        "n500ew": "NIFTY500 EQUAL WEIGHT",
        "n500fq30": "NIFTY500 FLEXICAP QUALITY 30",
        "n500lv50": "NIFTY500 LOW VOLATILITY 50",
        "n500mmq50": "NIFTY500 MULTIFACTOR MQVLV 50",
        "n500q50": "NIFTY500 QUALITY 50",
        "n500v50": "NIFTY500 VALUE 50",
        "n500m50": "NIFTY500 MOMENTUM 50",
        "nmc150m50": "NIFTY MIDCAP150 MOMENTUM 50",
        "nms400mq100": "NIFTY MIDSMALLCAP400 MOMENTUM QUALITY 100",
        "nsc250mq100": "NIFTY SMALLCAP250 MOMENTUM QUALITY 100",
        "n1drate": "NIFTY 1D RATE INDEX",
        "n50arbitrage": "NIFTY 50 ARBITRAGE",
        "n50futures": "NIFTY 50 FUTURES INDEX",
        "n50futurestr": "NIFTY 50 FUTURES TR INDEX",
        "n50usd": "NIFTY50 USD",
        # Fixed Income Indices
        "nbb2030": "NIFTY BHARAT BOND INDEX - APRIL 2030",
        "nbb2031": "NIFTY BHARAT BOND INDEX - APRIL 2031",
        "nbb2032": "NIFTY BHARAT BOND INDEX - APRIL 2032",
        "nbb2033": "NIFTY BHARAT BOND INDEX - APRIL 2033",
        "n10yrbenchmark": "NIFTY 10 YR BENCHMARK G-SEC",
        "n10yrbenchmarkclean": "NIFTY 10 YR BENCHMARK G-SEC (CLEAN PRICE)",
        "n1115yrgsec": "NIFTY 11-15 YR G-SEC INDEX",
        "n15yrandabovegsec": "NIFTY 15 YR AND ABOVE G-SEC INDEX",
        "n48yrgsec": "NIFTY 4-8 YR G-SEC INDEX",
        "n813yrgsec": "NIFTY 8-13 YR G-SEC",
        "ncompositegsec": "NIFTY COMPOSITE G-SEC INDEX",
    }
    for symbol, index in indices.items():
        await fetch_full_index_data(symbol, index)


asyncio.run(main())
