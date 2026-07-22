"""Đồng bộ tương tác thật (enrollments + lesson_progress) từ gold.itlr_fact_interaction (DataLake)
về interactions_real.csv cho CF training (itlr/pipelines/build_cf.py). Chạy job Dagster
`sync_itlr_interactions` trước. Đọc qua Trino localhost:8082, không cần chung Docker network.

Cold-start: dưới --min-users thì KHÔNG ghi đè file cũ.

Cách chạy:
    python scripts/data/sync_interactions_from_datalake.py
    python scripts/data/sync_interactions_from_datalake.py --rebuild-cf
    python scripts/data/sync_interactions_from_datalake.py --min-users 10  # test cục bộ
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd  # noqa: E402

from itlr import config  # noqa: E402

QUERY = """
SELECT DISTINCT user_id, item_id
FROM gold.itlr_fact_interaction
WHERE user_id IS NOT NULL AND item_id IS NOT NULL
"""


def fetch_interactions(host: str, port: int) -> pd.DataFrame:
    from trino.dbapi import connect

    conn = connect(host=host, port=port, user="itlr_sync", catalog="lakehouse", schema="gold")
    cur = conn.cursor()
    cur.execute(QUERY)
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=["user_id", "item_id"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trino-host", default=os.environ.get("TRINO_HOST", "localhost"))
    ap.add_argument("--trino-port", type=int, default=int(os.environ.get("TRINO_PORT", 8082)))
    ap.add_argument("--out", default=str(config.DATA_DIR / "interactions_real.csv"))
    ap.add_argument("--min-users", type=int, default=50,
                     help="Ngưỡng cold-start: dưới ngưỡng này KHÔNG ghi đè file --out.")
    ap.add_argument("--rebuild-cf", action="store_true",
                     help="Chạy build_cf.py ngay sau khi ghi CSV (ITLR_INTERACTIONS_CSV trỏ vào --out).")
    args = ap.parse_args()

    print(f"Truy vấn gold.itlr_fact_interaction qua Trino ({args.trino_host}:{args.trino_port})...", flush=True)
    df = fetch_interactions(args.trino_host, args.trino_port)
    n_users = df["user_id"].nunique()
    n_items = df["item_id"].nunique()
    print(f"Lấy được {len(df)} tương tác thật từ {n_users} user, {n_items} khóa học.", flush=True)

    if n_users < args.min_users:
        print(f"Chỉ {n_users} user thật (< --min-users {args.min_users}) — GIỮ NGUYÊN {args.out}, "
              f"không ghi đè.", flush=True)
        return

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Đã ghi {args.out} ({len(df)} dòng).", flush=True)

    if args.rebuild_cf:
        print("Rebuild CF model từ interactions thật...", flush=True)
        env = {**os.environ, "ITLR_INTERACTIONS_CSV": args.out}
        subprocess.run([sys.executable, "-m", "itlr.pipelines.build_cf"], check=True, env=env)


if __name__ == "__main__":
    main()
