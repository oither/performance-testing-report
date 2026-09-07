"""公共逻辑：加载种子数据、登录、从账号池取号。"""
import itertools, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings

# 注意：这个 import 必须在 config.settings 之前执行才能把仓库根加进 sys.path，
# mixed_user.py / login_user.py 里 `from common import ...` 都写在最前面，别调换顺序
try:
    _seed = json.loads(settings.SEED_FILE.read_text(encoding="utf-8"))
except FileNotFoundError:
    raise SystemExit(
        f"[common] 找不到种子数据 {settings.SEED_FILE}。\n"
        "请先启动被测系统并运行：python scripts/seed_data.py"
    )
ARTICLE_IDS = _seed["article_ids"]
_user_cycle = itertools.cycle(_seed["users"])   # 账号池轮询

def next_user():
    return next(_user_cycle)