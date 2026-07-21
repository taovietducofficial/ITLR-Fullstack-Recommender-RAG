"""Tái lập TOÀN BỘ thực nghiệm bằng MỘT lệnh (reproducibility).

Chạy lần lượt: sinh nhãn -> ablation sạch -> ablation nhiễu -> CF eval -> off-policy ->
(tùy chọn) LTR -> latency -> Cohen's Kappa. Mọi con số trong reports/ tái lập được từ đây.

    python scripts/eval/run_all.py            # bộ đầy đủ (chậm; có rerank + LTR)
    python scripts/eval/run_all.py --quick    # bộ rút gọn (cho CI / kiểm tra nhanh)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(cmd, env):
    print(f"\n{'='*70}\n$ {' '.join(cmd)}\n{'='*70}")
    t = time.time()
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, env=env)
    print(f"[{'OK' if r.returncode == 0 else 'LỖI'}] {time.time()-t:.1f}s")
    return r.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--with-ltr", action="store_true", help="Bao gồm train LTR (chậm)")
    args = ap.parse_args()

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    steps = [
        (["scripts/eval/make_judgments.py", "--natural", "--queries-per-cat", "4", "--simulate-human"], True),
        (["scripts/eval/make_judgments.py", "--out", "eval/relevance_keyword.csv", "--no-human"], True),
        (["scripts/eval/run_evaluation.py", "--no-rerank"] + (["--quick"] if args.quick else []), True),
        (["scripts/eval/run_evaluation.py", "--judgments", "eval/relevance_keyword.csv", "--tag", "_kw",
          "--noisy", "--no-rerank"] + (["--max-queries", "20"] if args.quick else []), True),
        (["scripts/eval/eval_cf.py", "--max-users", "300" if args.quick else "800"], True),
        (["scripts/eval/eval_off_policy.py", "--rounds", "3000" if args.quick else "6000"], True),
        (["scripts/eval/evaluate_human.py"], True),
        (["scripts/eval/bench_latency.py", "--repeats", "10" if args.quick else "30"], True),
    ]
    if args.with_ltr:
        steps.insert(3, (["scripts/eval/build_ltr.py", "--no-cross"], True))

    failed = []
    for cmd, _ in steps:
        if run(cmd, env) != 0:
            failed.append(cmd[0])

    print(f"\n{'='*70}\nTỔNG KẾT: {len(steps)-len(failed)}/{len(steps)} bước OK")
    if failed:
        print("Bước lỗi:", ", ".join(failed))
    print("Báo cáo ở: reports/  (tables.md, tables_noisy.md, cf_eval.md, off_policy.md, "
          "latency.md, human_eval.md, ltr.md)")


if __name__ == "__main__":
    main()
