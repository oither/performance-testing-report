"""登录接口专项压测。bcrypt 校验是 CPU 密集操作，预期这里最先出瓶颈 —— 
单独压它可以把'认证开销'和'数据库读写开销'分开定位。"""
from locust import HttpUser, task, between

from common import next_user
from config.settings import settings

class LoginUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.cred = next_user()

    @task
    def login(self):
        with self.client.post(
            "/auth/login",
            json={"username": self.cred["username"],
                  "password": settings.SEED_PASSWORD},
            name="POST /auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200 or "access_token" not in resp.json():
                resp.failure(f"login failed: {resp.status_code}")