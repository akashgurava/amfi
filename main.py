import argparse
import asyncio
import logging

from amfi import (
    AmfiClient,
    App,
    Database,
    configure_logging,
)


async def main() -> None:
    configure_logging()

    parser = argparse.ArgumentParser(description="AMFI NAV loader")
    parser.add_argument(
        "--db",
        default="amfi.duckdb",
        help="Path to database file (default: amfi.duckdb)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: fetch
    parser_fetch = subparsers.add_parser("fetch", help="Fetch data")
    fetch_subparsers = parser_fetch.add_subparsers(dest="fetch_command", required=True)

    # Subcommand: fetch plans
    fetch_subparsers.add_parser("plans", help="Fetch scheme details")

    # Subcommand: fetch all
    fetch_subparsers.add_parser("all", help="Fetch both plans and NAV data")

    # Subcommand: fetch nav
    parser_nav = fetch_subparsers.add_parser("nav", help="Fetch NAV data")
    parser_nav.add_argument(
        "--dates",
        default="new",
        help=(
            "Date selector: 'new' (fetch only missing), 'all' (fetch complete "
            "history), or specific dates/ranges (e.g. YYYY, YYYY-MM)"
        ),
    )

    args = parser.parse_args()

    client = AmfiClient(
        parallel_requests=4,
        max_retries=3,
    )
    db = Database(db_path=args.db)
    app = App(client, db)
    app.init_db()

    try:
        if args.command == "fetch":
            if args.fetch_command == "plans":
                await app.save_fund_details()

            elif args.fetch_command == "all":
                await app.save_fund_details()
                await app.save_nav()

            elif args.fetch_command == "nav":
                fetch_all = False
                force = None

                if args.dates == "all":
                    fetch_all = True
                elif args.dates == "new":
                    fetch_all = False
                else:
                    force = args.dates

                await app.save_nav(fetch_all=fetch_all, force=force)

    except KeyboardInterrupt:
        logging.getLogger("amfi").warning("Interrupted by user")


if __name__ == "__main__":
    asyncio.run(main())
