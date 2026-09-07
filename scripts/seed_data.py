"""压测前造数：批量注册账号池 + 文章 + 评论，账号与文章 ID 落到 seed_ids.json。
用法：python scripts/seed_data.py
前提：被测系统已启动，且数据库是干净的（或先跑 reset_db.py）。
"""
import json, random, string, sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings

session = requests.Session()

def rand_suffix(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def register_and_login(username):
    session.post(f"{settings.BASE_URL}/auth/register", json={
        "username": username,
        # .local/.test 等保留域名会被 email-validator 拒绝（422），example.com 是规范放行的示例域
        "email": f"{username}@example.com",
        "password": settings.SEED_PASSWORD,
    }, timeout=10)
    r = session.post(f"{settings.BASE_URL}/auth/login", json={
        "username": username, "password": settings.SEED_PASSWORD,
    }, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

def main():
    users = []
    for i in range(settings.SEED_USER_COUNT):
        name = f"loaduser_{i}_{rand_suffix(4)}"
        token = register_and_login(name)
        users.append({"username": name, "token": token})
        print(f"[seed] user {i+1}/{settings.SEED_USER_COUNT} ready")

    article_ids = []
    for i in range(settings.SEED_ARTICLE_COUNT):
        owner = random.choice(users)
        content = "压测文章内容。" * random.randint(20, 200)  # 模拟真实体积
        r = session.post(
            f"{settings.BASE_URL}/articles",
            headers={"Authorization": f"Bearer {owner['token']}"},
            json={"title": f"性能测试文章 {i} {rand_suffix(6)}", "content": content},
            timeout=10,
        )
        r.raise_for_status()
        article_ids.append(r.json()["id"])
        if (i + 1) % 50 == 0:
            print(f"[seed] articles {i+1}/{settings.SEED_ARTICLE_COUNT}")

    # 给部分文章造评论，让详情/评论链路有数据
    for aid in random.sample(article_ids, k=min(50, len(article_ids))):
        owner = random.choice(users)
        session.post(
            f"{settings.BASE_URL}/articles/{aid}/comments",
            headers={"Authorization": f"Bearer {owner['token']}"},
            json={"content": f"压测评论 {rand_suffix(10)}"},
            timeout=10,
        )

    settings.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    settings.SEED_FILE.write_text(json.dumps({
        "users": users, "article_ids": article_ids,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[seed] done -> {settings.SEED_FILE}")

if __name__ == "__main__":
    main()