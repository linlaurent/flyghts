"""CLI for flight traffic audit."""

import argparse
import sys
from datetime import date

from flyghts.audit.models import DateFilter, RouteFilter
from flyghts.audit.service import AuditService


def parse_args():
    parser = argparse.ArgumentParser(
        description="Audit flight traffic data (e.g. HK-Taipei)"
    )
    parser.add_argument(
        "--route",
        "-r",
        required=True,
        help="Route as ORIGIN-DEST (e.g. HKG-TPE)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--date",
        "-d",
        help="Single date (YYYY-MM-DD)",
    )
    group.add_argument(
        "--days",
        "-n",
        type=int,
        help="Past N days (inclusive)",
    )
    parser.add_argument(
        "--stats",
        "-s",
        action="store_true",
        help="Include statistics summary",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write results to CSV file",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        route = RouteFilter.from_route_string(args.route)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.date:
        try:
            d = date.fromisoformat(args.date)
        except ValueError:
            print(f"Error: Invalid date format: {args.date}", file=sys.stderr)
            sys.exit(1)
        date_filter = DateFilter.single(d)
    else:
        date_filter = DateFilter.past_days(args.days)

    service = AuditService()
    result = service.query(route, date_filter)

    if args.stats:
        stats = service.statistics(result.flights)
        print(f"\nTotal flights: {stats.total_flights}")
        if stats.by_airline:
            print("\nBy airline:")
            for airline, count in sorted(stats.by_airline.items(), key=lambda x: -x[1]):
                print(f"  {airline}: {count}")
        if stats.by_route:
            print("\nBy route:")
            for route_key, count in sorted(stats.by_route.items()):
                print(f"  {route_key}: {count}")
        if stats.by_date:
            print("\nBy date:")
            for d, count in sorted(stats.by_date.items()):
                print(f"  {d}: {count}")
        if stats.status_summary:
            print("\nStatus summary:")
            for status, count in sorted(stats.status_summary.items(), key=lambda x: -x[1]):
                print(f"  {status}: {count}")
        print()

    df = result.to_dataframe()
    if df.empty:
        print("No flights found.", file=sys.stderr)
    else:
        print(df.to_string(index=False))

    if args.output and not df.empty:
        df.to_csv(args.output, index=False)
        print(f"\nWrote {len(df)} rows to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
