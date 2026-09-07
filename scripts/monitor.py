"""采集被测 uvicorn 进程与整机资源 → CSV。
用法（压测开始前另开终端运行）：
    python scripts/monitor.py --name load_20260907 --pid <uvicorn的PID>
不传 --pid 则只采整机。Ctrl+C 停止。
"""
import argparse, csv, time
from datetime import datetime
from pathlib import Path
import psutil

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "monitor-data"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--name", required=True)
    p.add_argument("--pid", type=int, default=None)
    p.add_argument("--interval", type=float, default=2.0)
    args = p.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.name}_resources.csv"
    proc = psutil.Process(args.pid) if args.pid else None

    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "sys_cpu_percent", "sys_mem_percent",
                    "proc_cpu_percent", "proc_mem_mb"])
        print(f"[monitor] writing to {out}, Ctrl+C to stop")
        try:
            while True:
                row = [datetime.now().isoformat(timespec="seconds"),
                       psutil.cpu_percent(interval=None),
                       psutil.virtual_memory().percent,
                       proc.cpu_percent(interval=None) if proc else "",
                       round(proc.memory_info().rss / 1048576, 1) if proc else ""]
                w.writerow(row)
                f.flush()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("[monitor] stopped")

if __name__ == "__main__":
    main()