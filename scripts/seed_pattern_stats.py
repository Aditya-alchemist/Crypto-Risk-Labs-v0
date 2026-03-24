from __future__ import annotations

from bot.historical_scanner import seed_pattern_stats_from_historical


def main() -> None:
    result = seed_pattern_stats_from_historical()
    print(
        f"Pattern scanner complete: inserted={result['inserted']}, "
        f"updated={result['updated']}, scanned={result['patterns']}"
    )


if __name__ == "__main__":
    main()
