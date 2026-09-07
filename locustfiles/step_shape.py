"""自定义负载曲线：10→50→100→150→200，每级 2 分钟，线性爬升 10s。
运行：locust -f locustfiles/mixed_user.py,locustfiles/step_shape.py --headless ...
"""
from locust import LoadTestShape

class StepLoad(LoadTestShape):
    step_users = [10, 50, 100, 150, 200]
    step_duration = 120      # 每级持续秒数
    spawn_rate = 10          # 每秒拉起用户数

    def tick(self):
        run_time = self.get_run_time()
        step_index = int(run_time // self.step_duration)
        if step_index >= len(self.step_users):
            return None      # 结束
        return self.step_users[step_index], self.spawn_rate