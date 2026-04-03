"""Show operator timing breakdown from the llm_client observability DB.

Usage:
    python scripts/timing_report.py [--days N] [--trace TRACE_ID]
"""

from __future__ import annotations

import argparse
import os
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser(description="Operator timing breakdown")
    parser.add_argument("--days", type=int, default=1, help="Lookback window in days")
    parser.add_argument("--trace", default="", help="Filter to specific trace_id prefix")
    args = parser.parse_args()

    db_path = os.path.expanduser("~/projects/data/llm_observability.db")
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)

    # Per-operator summary
    where_trace = "AND trace_id LIKE ?" if args.trace else ""
    params: list[object] = [f"digimon.benchmark", args.days]
    if args.trace:
        params.append(f"{args.trace}%")

    rows = conn.execute(
        f"""
        SELECT tool_name, operation,
               COUNT(*) AS calls,
               ROUND(AVG(duration_ms)) AS avg_ms,
               ROUND(MIN(duration_ms)) AS min_ms,
               ROUND(MAX(duration_ms)) AS max_ms,
               ROUND(SUM(duration_ms)/1000.0, 1) AS total_s
        FROM tool_calls
        WHERE task = ?
          AND started_at >= datetime('now', '-' || ? || ' day')
          AND status = 'succeeded'
          {where_trace}
        GROUP BY tool_name, operation
        ORDER BY total_s DESC
        """,
        params,
    ).fetchall()

    if not rows:
        print(f"No Digimon operator timing records in last {args.days}d.")
        print("Run a benchmark with the updated tool_consolidation.py to populate data.")
        return

    header = f"{'Tool':<25} {'Method':<18} {'Calls':>6} {'Avg ms':>8} {'Min ms':>8} {'Max ms':>8} {'Total s':>9}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r[0]:<25} {r[1]:<18} {r[2]:>6} {r[3]:>8} {r[4]:>8} {r[5]:>8} {r[6]:>9}")

    total_s = sum(r[6] for r in rows)
    total_calls = sum(r[2] for r in rows)
    print(f"\nTotal operator time: {total_s:.1f}s across {total_calls} calls")

    # Per-trace summary (shows total operator time vs LLM time per question)
    trace_rows = conn.execute(
        """
        SELECT trace_id,
               COUNT(*) AS tool_calls,
               ROUND(SUM(duration_ms)/1000.0, 1) AS operator_s
        FROM tool_calls
        WHERE task = 'digimon.benchmark'
          AND started_at >= datetime('now', '-' || ? || ' day')
          AND status = 'succeeded'
        GROUP BY trace_id
        ORDER BY operator_s DESC
        LIMIT 20
        """,
        [args.days],
    ).fetchall()

    if trace_rows:
        print(f"\n{'Trace (question)':<55} {'Tool calls':>11} {'Operator s':>11}")
        print("-" * 79)
        for r in trace_rows:
            trace = str(r[0])
            # Extract question ID from trace like "digimon.benchmark.MuSiQue.12345.abcd"
            parts = trace.split(".")
            label = ".".join(parts[-2:]) if len(parts) >= 2 else trace
            print(f"{label:<55} {r[1]:>11} {r[2]:>11}")


if __name__ == "__main__":
    main()
