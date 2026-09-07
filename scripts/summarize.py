"""从 Locust stats_history.csv 提取每一级并发的"稳定段"指标，输出 markdown 表格。

阶梯负载（Shape）运行时，每级用户数有一个持续 plateau，爬坡期的中间用户数行
和每级前半段（尚未稳定）都应剔除。本脚本：
  1. 只取 Aggregated 汇总行，按 User Count 分组；
  2. 丢弃持续时间 < --min-plateau 秒的组（即爬坡过渡）；
  3. 每组只取时间上最后 --window 比例的行（稳定段）求指标；
  4. 可选 --monitor 把 monitor.py 的资源 CSV 按时间窗对齐，附上 CPU/内存均值。

用法：
  python scripts/summarize.py results/load_20260907/mixed_stats_history.csv \
      --monitor docs/monitor-data/load_20260907_mixed_p1_resources.csv
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


def load_history(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    df = df[df["Name"] == "Aggregated"].copy()
    for col in ["Timestamp", "User Count", "Requests/s", "Failures/s", "50%", "95%", "99%"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["User Count"].fillna(0) > 0]
    df["fail_pct"] = np.where(df["Requests/s"] > 0,
                              df["Failures/s"] / df["Requests/s"] * 100, 0)
    return df.sort_values("Timestamp")


def plateau_windows(df: pd.DataFrame, min_plateau: float, window: float):
    """返回 [(users, t_start, t_end, rows), ...]，rows 为稳定段数据。"""
    windows = []
    for users, g in df.groupby("User Count"):
        t0, t1 = g["Timestamp"].min(), g["Timestamp"].max()
        if t1 - t0 < min_plateau:
            continue    # 爬坡过渡，丢弃
        cut = t0 + (t1 - t0) * (1 - window)
        stable = g[g["Timestamp"] >= cut]
        if not stable.empty:
            windows.append((int(users), t0, t1, stable))
    return sorted(windows, key=lambda w: w[1])


def load_monitor(csv_path: Path) -> pd.DataFrame:
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                ts = datetime.fromisoformat(r["timestamp"]).timestamp()
            except ValueError:
                continue
            def num(key):
                try:
                    return float(r[key])
                except (ValueError, TypeError, KeyError):
                    return np.nan
            rows.append((ts, num("sys_cpu_percent"), num("sys_mem_percent"),
                         num("proc_cpu_percent"), num("proc_mem_mb")))
    return pd.DataFrame(rows, columns=["ts", "sys_cpu", "sys_mem", "proc_cpu", "proc_mem"])


def monitor_stats(mon: pd.DataFrame, t0: float, t1: float):
    if mon is None or mon.empty:
        return None
    seg = mon[(mon["ts"] >= t0) & (mon["ts"] <= t1)]
    if seg.empty:
        return None
    return {c: seg[c].mean() for c in ["sys_cpu", "sys_mem", "proc_cpu", "proc_mem"]}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv", help="locust 的 *_stats_history.csv")
    p.add_argument("--monitor", default=None, help="monitor.py 输出的资源 CSV（可选）")
    p.add_argument("--min-plateau", type=float, default=30.0,
                   help="用户数 plateau 至少持续多少秒才算一级（默认 30）")
    p.add_argument("--window", type=float, default=0.5,
                   help="每级取时间上最后多少比例作为稳定段（默认 0.5）")
    args = p.parse_args()

    df = load_history(Path(args.csv))
    mon = load_monitor(Path(args.monitor)) if args.monitor else None

    print("| 并发 | TPS | P50 avg (ms) | P95 avg (ms) | P99 max (ms) | 错误率% |"
          " 系统CPU% | 进程CPU% | 进程内存MB |")
    print("|------|-----|--------------|--------------|--------------|---------|"
          "----------|----------|-----------|")
    for users, _t0, _t1, stable in plateau_windows(df, args.min_plateau, args.window):
        m = monitor_stats(mon, stable["Timestamp"].min(), stable["Timestamp"].max())
        cells = [
            str(users),
            f"{stable['Requests/s'].mean():.1f}",
            f"{stable['50%'].mean():.0f}",
            f"{stable['95%'].mean():.0f}",
            f"{stable['99%'].max():.0f}",
            f"{stable['fail_pct'].mean():.2f}",
        ]
        if m:
            cells += [f"{m['sys_cpu']:.0f}", f"{m['proc_cpu']:.0f}", f"{m['proc_mem']:.0f}"]
        else:
            cells += ["-", "-", "-"] if mon is not None else []
        print("| " + " | ".join(cells) + " |")

    # 整场汇总（含爬坡与收尾），给峰值场景看恢复趋势用
    print()
    print(f"整场汇总: 总时长≈{df['Timestamp'].max()-df['Timestamp'].min():.0f}s, "
          f"平均TPS={df['Requests/s'].mean():.1f}, "
          f"P95峰值={df['95%'].max():.0f}ms, "
          f"P99峰值={df['99%'].max():.0f}ms, "
          f"失败率峰值={df['fail_pct'].max():.2f}%")


if __name__ == "__main__":
    main()
