"""优化前后对比图：输入两份 stats_history.csv（优化前 / 优化后），
按每级并发的稳定段指标画两张柱状图：
  ① TPS per concurrency level（线性轴）
  ② P95 per concurrency level（对数轴，优化前后差几个数量级）
用法：
  python scripts/plot_compare.py results/load_20260907/mixed_p1_stats_history.csv \
      results/load_20260907/mixed_opt_stats_history.csv --labels "before" "after"
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from summarize import load_history, plateau_windows

ROOT = Path(__file__).resolve().parent.parent
CHARTS = ROOT / "charts"

# 退场时用户逐个退出会产生非标准并发档位（如 145/197），只保留阶梯配置的档位
sys.path.insert(0, str(ROOT / "locustfiles"))
try:
    from step_shape import StepLoad
    CANONICAL_STEPS = set(StepLoad.step_users)
except ImportError:
    CANONICAL_STEPS = None


def per_level(csv_path: Path):
    """返回 {users: {"tps": .., "p95": .., "fail": ..}}，只保留阶梯级别（≥30s plateau）。"""
    df = load_history(csv_path)
    out = {}
    for users, _t0, _t1, stable in plateau_windows(df, 30.0, 0.5):
        if CANONICAL_STEPS is not None and users not in CANONICAL_STEPS:
            continue
        out[users] = {
            "tps": float(stable["Requests/s"].mean()),
            "p95": float(stable["95%"].mean()),
            "fail": float(stable["fail_pct"].mean()),
        }
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("before_csv")
    p.add_argument("after_csv")
    p.add_argument("--labels", nargs=2, default=["before", "after"])
    args = p.parse_args()

    CHARTS.mkdir(exist_ok=True)
    b = per_level(Path(args.before_csv))
    a = per_level(Path(args.after_csv))
    # 阶梯级别取两份数据的并集（按目标并发归类，爬坡中间态已由 plateau 过滤）
    levels = sorted(set(b) | set(a))
    x = np.arange(len(levels))
    width = 0.35

    for metric, fname, log, title in [
        ("tps", "opt_compare_tps.png", False, "TPS per concurrency level"),
        ("p95", "opt_compare_p95.png", True, "P95 RT per concurrency level (log)"),
    ]:
        fig, ax = plt.subplots(figsize=(10, 5))
        bv = [b.get(l, {}).get(metric, np.nan) for l in levels]
        av = [a.get(l, {}).get(metric, np.nan) for l in levels]
        ax.bar(x - width / 2, bv, width, label=args.labels[0], color="tab:gray")
        ax.bar(x + width / 2, av, width, label=args.labels[1], color="tab:green")
        ax.set_xticks(x); ax.set_xticklabels(levels)
        ax.set_xlabel("Concurrency level"); ax.set_title(title)
        if log:
            ax.set_yscale("log")
        ax.legend()
        out = CHARTS / fname
        fig.tight_layout(); fig.savefig(out, dpi=150)
        print(f"[compare] saved: {out}")


if __name__ == "__main__":
    main()
