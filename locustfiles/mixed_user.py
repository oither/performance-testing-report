"""混合读写场景：模拟真实流量分布 —— 列表浏览为主、详情次之，两类用户默认权重 1:2。
运行示例见 README；用 --tags list / detail / anon 可单独压某一类接口。

基准测试需要"单用户单接口"的确定性采数，用环境变量把另一类用户权重设为 0：
    READER_WEIGHT=1 ANON_WEIGHT=0 locust -f locustfiles/mixed_user.py --tags list ...
（PowerShell：$env:READER_WEIGHT="1"; $env:ANON_WEIGHT="0"）
"""
import os
import random
from locust import HttpUser, task, between, tag

from common import ARTICLE_IDS, next_user
from config.settings import settings

READER_WEIGHT = int(os.getenv("READER_WEIGHT", "1"))
ANON_WEIGHT = int(os.getenv("ANON_WEIGHT", "2"))

class BlogReader(HttpUser):
    """已登录读者：列表 7 : 详情 3，wait_time 模拟用户思考时间。"""
    weight = READER_WEIGHT
    wait_time = between(0.5, 1.5)

    def on_start(self):
        u = next_user()
        r = self.client.post(
            "/auth/login",
            json={"username": u["username"], "password": settings.SEED_PASSWORD},
            name="[setup] POST /auth/login",
        )
        token = r.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @tag("read", "list")
    @task(7)
    def list_articles(self):
        skip = random.choice([0, 0, 0, 10, 20])   # 少量翻页流量
        with self.client.get(
            f"/articles?skip={skip}&limit=10",
            name="GET /articles (list)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200 and not resp.json():
                resp.failure("empty article list")   # 业务级校验，不只 200 就算过

    @tag("read", "detail")
    @task(3)
    def article_detail(self):
        aid = random.choice(ARTICLE_IDS)
        self.client.get(f"/articles/{aid}", name="GET /articles/{id} (detail)")

class AnonymousReader(HttpUser):
    """匿名访客：不登录直接访问公开接口，占比可用 weight 调整。
    tag 用独立的 "anon"，方便用 --tags 与登录用户分开采数。"""
    weight = ANON_WEIGHT
    wait_time = between(0.5, 1.5)

    @tag("anon")
    @task
    def list_articles_anonymous(self):
        self.client.get("/articles?limit=10", name="GET /articles (anon)")