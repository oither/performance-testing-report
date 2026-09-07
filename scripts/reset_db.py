"""一键恢复压测现场。

两种模式：
  python scripts/reset_db.py            # 只清理压测造的数据（loaduser_* 账号及其文章/评论）
  python scripts/reset_db.py --rebuild  # 整个删除 blog.db，服务重启后自动重建空表（慎用）

blog.db 的路径由 config/.env 的 BLOG_DB_PATH 控制。
SQLite 是文件库，脚本直接操作文件，不需要被测服务在运行；
但如果服务正在跑，建议先停掉再清理，避免写锁冲突。
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings

# 与 seed_data.py 的命名保持一致
SEED_USER_PREFIX = "loaduser_"


def clean_seed_data(db_path: Path):
    if not db_path.exists():
        print(f"[reset] 数据库不存在，无需清理：{db_path}")
        return
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # 没有外键级联（SQLite 默认不启用），按 依赖顺序 手动删：评论 → 文章 → 用户
        cur.execute(
            """DELETE FROM comments WHERE user_id IN (
                   SELECT id FROM users WHERE username LIKE ?)
               OR article_id IN (
                   SELECT id FROM articles WHERE author_id IN (
                       SELECT id FROM users WHERE username LIKE ?))""",
            (f"{SEED_USER_PREFIX}%", f"{SEED_USER_PREFIX}%"),
        )
        comments = cur.rowcount
        cur.execute(
            """DELETE FROM articles WHERE author_id IN (
                   SELECT id FROM users WHERE username LIKE ?)""",
            (f"{SEED_USER_PREFIX}%",),
        )
        articles = cur.rowcount
        cur.execute("DELETE FROM users WHERE username LIKE ?", (f"{SEED_USER_PREFIX}%",))
        users = cur.rowcount
        conn.commit()
        print(f"[reset] 已清理压测数据：用户 {users} 个、文章 {articles} 篇、评论 {comments} 条")
    finally:
        conn.close()


def rebuild_db(db_path: Path):
    if db_path.exists():
        print(f"[reset] 即将删除整个数据库文件：{db_path}")
        db_path.unlink()
        print("[reset] 已删除。重启被测服务后 SQLAlchemy 会自动建出空表。")
    else:
        print(f"[reset] 数据库不存在：{db_path}（服务首次启动时会自动创建）")


def main():
    p = argparse.ArgumentParser(description="清理压测数据或重建 blog.db")
    p.add_argument("--rebuild", action="store_true",
                   help="删除整个 blog.db（会丢掉所有数据，包括项目一的测试数据）")
    args = p.parse_args()

    db_path = Path(settings.BLOG_DB_PATH)
    print(f"[reset] 目标数据库：{db_path}")
    if args.rebuild:
        rebuild_db(db_path)
    else:
        clean_seed_data(db_path)


if __name__ == "__main__":
    main()
