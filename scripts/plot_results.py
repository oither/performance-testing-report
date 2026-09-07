"""解析 Locust 的 *_stats_history.csv，画两张核心图：
  ① 并发用户数 vs 响应时间（P50 / P95）—— 找拐点
  ② 并发用户数 vs RPS + 失败率 —— 看吞吐饱和点
用法：python scripts/plot_results.py results/load_YYYYMMDD/mixed_stats_history.csv

说明：stats_history 的逐秒窗口里只有分位数列（50%..100%）和累计均值
（Total Average Response Time，跨整个 run 累计，不反映瞬时趋势），
所以瞬时"典型响应时间"用 P50 中位数代替平均数，长尾看 P95。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
CHARTS = ROOT / "charts"


def load_aggregated(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    # 只看 Aggregated 汇总行；开头会有一条 User Count=0 的预启动空记录，丢掉
    df = df[df["Name"] == "Aggregated"]
    df = df[pd.to_numeric(df["User Count"], errors="coerce").fillna(0) > 0].copy()
    num_cols = ["Timestamp", "User Count", "Requests/s", "Failures/s", "50%", "95%"]
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["elapsed"] = df["Timestamp"] - df["Timestamp"].iloc[0]   # unix 秒 → 相对秒
    df["fail_pct"] = np.where(df["Requests/s"] > 0,
                              df["Failures/s"] / df["Requests/s"] * 100, 0)
    return df


def main(csv_path: str):
    CHARTS.mkdir(exist_ok=True)
    df = load_aggregated(Path(csv_path))
    if df.empty:
        sys.exit(f"[plot] {csv_path} 里没有可用的 Aggregated 数据行")

    t = df["elapsed"]

    # 图①：并发用户数（左轴） vs P50/P95 响应时间（右轴）
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(t, df["User Count"], label="Concurrent Users", color="tab:gray", alpha=0.6)
    ax1.set_xlabel("Elapsed (s)"); ax1.set_ylabel("Users")
    ax2 = ax1.twinx()
    ax2.plot(t, df["50%"], label="Median RT (P50, ms)", color="tab:blue")
    ax2.plot(t, df["95%"], label="P95 RT (ms)", color="tab:red", linestyle="--")
    ax2.set_ylabel("Response Time (ms)")
    ax2.set_yscale("log")   # 长尾可达数十万 ms，线性轴会压扁正常段
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [l.get_label() for l in lines], loc="upper left")
    ax1.set_title("Concurrency vs Response Time")
    out1 = CHARTS / f"{Path(csv_path).stem}_rt.png"
    fig.tight_layout(); fig.savefig(out1, dpi=150)

    # 图②：RPS 与失败率随时间变化
    fig2, ax = plt.subplots(figsize=(10, 5))
    ax.plot(t, df["Requests/s"], label="RPS", color="tab:green")
    ax.plot(t, df["fail_pct"], label="Failure %", color="tab:red")
    ax.set_xlabel("Elapsed (s)"); ax.set_ylabel("Requests/s / Failure %")
    ax.set_title("Throughput & Failure Rate")
    ax.legend()
    out2 = CHARTS / f"{Path(csv_path).stem}_rps.png"
    fig2.tight_layout(); fig2.savefig(out2, dpi=150)

    print(f"[plot] saved: {out1}, {out2}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("用法：python scripts/plot_results.py <locust的*_stats_history.csv路径>")
    main(sys.argv[1])
