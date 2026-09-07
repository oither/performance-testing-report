import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "config" / ".env")

class Settings:
    BASE_URL: str = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    SEED_PASSWORD: str = os.getenv("SEED_PASSWORD", "LoadTest#123")
    SEED_USER_COUNT: int = int(os.getenv("SEED_USER_COUNT", "20"))
    SEED_ARTICLE_COUNT: int = int(os.getenv("SEED_ARTICLE_COUNT", "200"))
    SEED_FILE: Path = ROOT / "results" / "seed_ids.json"
    # 压测时 Locust 用户从账号池里轮流取用，避免 200 并发全挤一个账号
    RESULTS_DIR: Path = ROOT / "results"
    # 被测系统的 SQLite 文件。注意：blog.db 的实际位置取决于启动 uvicorn 时的
    # 工作目录（连接串是相对路径 sqlite:///./blog.db），默认按"两个仓库并排放在
    # 桌面、从 blog-system-under-test 目录启动服务"来解析，不同布局时改 .env
    BLOG_DB_PATH: Path = Path(os.getenv(
        "BLOG_DB_PATH",
        str(ROOT.parent / "blog-system-under-test" / "blog.db"),
    ))

settings = Settings()