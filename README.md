# performance-testing-report — 博客系统全链路性能压测与瓶颈分析

基于 **Locust** 对博客系统（FastAPI + SQLite）核心链路进行基准 / 阶梯负载 / 并发峰值
三类场景压测，最高模拟 200 并发用户。定位出**双重瓶颈**：登录接口在 async 事件循环里
跑 bcrypt（10 并发即打满单核、TPS 封顶 ~4/s），并连锁触发 SQLAlchemy 连接池耗尽
（拐点 50→100 并发，P95 从 16ms 恶化到 30s，246 次 HTTP 500）；纯读链路则可扛住
200 并发瞬发（198 TPS、P99 160ms、零错误）。优化验证进行中，见
[docs/performance-report.md](docs/performance-report.md)。

> 被测系统：[blog-system-under-test](../blog-system-under-test) ｜ 功能正确性保障：[api-test-framework](../api-test-framework)

## 技术栈

| 层面 | 技术 |
|------|------|
| 压测引擎 | Locust（Python，HttpUser + 自定义 LoadTestShape 阶梯负载）|
| 数据准备 | requests 批量造数脚本（账号池 + 文章 + 评论）|
| 资源监控 | psutil（进程级 CPU/内存 → CSV，跨平台）|
| 结果分析 | pandas + matplotlib（并发-RT 曲线、RPS/失败率曲线）|
| 版本管理 | Git + GitHub |

## 目录结构

```
performance-testing-report/
├── config/
│   ├── settings.py          # 读取 .env：被测地址、压测账号池、种子数据规模
│   └── .env                 # BASE_URL / SEED_USER_COUNT / SEED_ARTICLE_COUNT / SEED_PASSWORD
├── scripts/
│   ├── seed_data.py         # 压测前造数：批量注册用户 + 文章 + 评论，落 ids 到 JSON
│   ├── reset_db.py          # 一键恢复现场（默认只清压测数据；--rebuild 重建 blog.db）
│   ├── monitor.py           # psutil 采集被测进程 CPU/内存 → CSV
│   ├── plot_results.py      # 解析 Locust *_stats_history.csv → matplotlib 出图
│   └── summarize.py         # 提取每级并发的稳定段指标（TPS/P95/P99/错误率/CPU）→ markdown 表
├── locustfiles/
│   ├── common.py            # 公共逻辑：读种子数据、账号池轮询
│   ├── mixed_user.py        # 混合场景用户（列表 70% / 详情 30%），主压测文件
│   ├── login_user.py        # 登录接口专项压测（bcrypt 是 CPU 密集，单独建模）
│   └── step_shape.py        # 自定义阶梯负载 Shape（10→50→100→150→200，每级 2min）
├── results/                 # 每轮压测的 CSV 输出（按 场景_日期 命名）
├── charts/                  # plot_results.py 输出的 png
├── docs/
│   ├── performance-report.md   # 正式压测报告
│   ├── monitor-data/           # 资源监控 CSV + 截图
│   └── interview-notes.md      # 面试问答要点
├── requirements.txt
└── README.md
```

## 快速开始

### 0. 安装依赖

```bash
pip install -r requirements.txt
```

### 1. 启动被测系统（生产姿势）

```bash
cd ../blog-system-under-test
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

> **不要加 `--reload`**：热重载的 watcher 进程会污染 CPU 数据。
> **单 worker 是刻意的**：先测出裸服务的真实上限，"要不要加 worker/换连接池"本身就是优化结论素材。

### 2. 造数

```bash
python scripts/seed_data.py     # 注册 20 个账号 + 200 篇文章 + 50 条评论（数量在 .env 里调）
```

### 3. 三场景压测

```bash
# ── 场景一：基准测试（1 用户 × 2min，按链路隔离）────────────
# 用权重环境变量 + --tags 保证"单用户单接口"的确定性采数
# Git Bash / Linux：
READER_WEIGHT=1 ANON_WEIGHT=0 locust -f locustfiles/mixed_user.py --headless \
  --host http://127.0.0.1:8000 -u 1 -r 1 -t 2m --tags list \
  --csv results/baseline_YYYYMMDD/baseline_list --csv-full-history
# 同理：--tags detail 压详情；READER_WEIGHT=0 ANON_WEIGHT=1 --tags anon 压匿名列表
# PowerShell：$env:READER_WEIGHT="1"; $env:ANON_WEIGHT="0"（压完记得 Remove-Item env:READER_WEIGHT）

# ── 场景二：阶梯负载（10→50→100→150→200，每级 2min）───────
# 终端 A：资源监控（PID 用 netstat -ano | findstr :8000 查 uvicorn 的）
python scripts/monitor.py --name load_YYYYMMDD --pid <PID>
# 终端 B：混合读写场景阶梯加压（并发数由 step_shape.py 控制，-u/-t 不生效）
locust -f locustfiles/mixed_user.py,locustfiles/step_shape.py --headless \
  --host http://127.0.0.1:8000 \
  --csv results/load_YYYYMMDD/mixed_p1 --csv-full-history
# 登录接口单独跑一轮同样的阶梯
locust -f locustfiles/login_user.py,locustfiles/step_shape.py --headless \
  --host http://127.0.0.1:8000 \
  --csv results/load_YYYYMMDD/login_p1 --csv-full-history
# 整场复测第二遍（验证可复现性）：重启服务后把 mixed_p1 换成 mixed_p2 再跑

# ── 场景三：并发峰值（200 用户瞬间拉起，1 分钟，纯读）────────
# 在重启后的干净服务上单独跑，避免与阶梯场景互相污染
READER_WEIGHT=0 ANON_WEIGHT=1 locust -f locustfiles/mixed_user.py --headless \
  --host http://127.0.0.1:8000 -u 200 -r 200 -t 1m --tags anon \
  --csv results/spike_YYYYMMDD/spike --csv-full-history
```

说明：

- `--csv-full-history` 才会输出带时间序列的 `*_stats_history.csv`，画图靠它。
- 调试期不加 `--headless`，用 Web UI（http://localhost:8089）观察；正式采数据必须 headless，UI 本身耗资源。
- 每个场景**至少跑两遍取稳定值**，第一遍当热身。
- Windows 下多行命令直接连成一行执行，或用 PowerShell 的反引号续行。

### 4. 出图与分析

```bash
python scripts/plot_results.py results/load_YYYYMMDD/mixed_p1_stats_history.csv
# 生成 charts/ 下两张图：并发-响应时间曲线（找拐点，对数轴）、RPS/失败率曲线

python scripts/summarize.py results/load_YYYYMMDD/mixed_p1_stats_history.csv \
  --monitor docs/monitor-data/load_YYYYMMDD_mixed_p1_resources.csv
# 输出每级并发的稳定段指标表（TPS/P50/P95/P99/错误率/CPU/内存），可直接贴进报告
```

### 5. 恢复现场

```bash
python scripts/reset_db.py            # 只清理压测造的数据（loaduser_* 账号及其文章/评论）
python scripts/reset_db.py --rebuild  # 删掉整个 blog.db 重建空库（慎用，会丢所有数据）
```

## 核心数据速览（2026-09-07 首轮采数）

| 场景 | 并发 | TPS | P50 | P95 | P99 | 错误率 |
|------|------|-----|-----|-----|-----|--------|
| 基准·登录态列表 | 1 | 0.99 | 6ms | — | 10ms | 0% |
| 基准·详情 | 1 | 0.98 | 7ms | — | 12ms | 0% |
| 阶梯·混合场景 | 50 | 49.7 | 7ms | 16ms | 26ms | 0% |
| **阶梯·混合场景（拐点）** | **100** | **≈0（悬死）** | **37.6s** | **37.6s** | **91s** | 悬死后成批 500 |
| 登录专项 | 10 | 3.7 | 764ms | 1.5s | 2s | 0%（CPU 88% 打满单核）|
| 并发峰值·纯读 | 200（瞬发）| 198.3 | 7ms | 44ms | 160ms | **0%** |

瓶颈定位：登录接口在 async 事件循环里跑 bcrypt（单核 ~4 TPS 上限），爬坡期登录风暴阻塞事件循环 → 线程池占满 → SQLAlchemy 连接池（5+10）checkout 30s 超时 → 246 次 HTTP 500 成批爆发。完整证据链见 [docs/performance-report.md](docs/performance-report.md)，图表见 [charts/](charts/)。

## 遇到的问题与解决

1. **造数接口全部 422**：种子邮箱用 `@loadtest.local`，而 `.local` 是保留域名，被 email-validator 拒绝，注册静默失败导致后续登录 401。**解决**：改用规范放行的 `@example.com`，并给注册响应加状态码检查。教训：造数脚本的每一步都要 assert，不能 fire-and-forget。
2. **基准测试压出 0 个请求**：`-u 1` 时 Locust 按 1:2 权重随机挑用户类，随机到匿名类后 `--tags list` 过滤掉了它的全部任务。**解决**：给用户类权重加环境变量开关（`READER_WEIGHT/ANON_WEIGHT`），基准采数时把另一类设为 0，实现确定性单类压测。
3. **压测后服务"假死"**：含大量登录的场景跑完后，服务进程活着、端口在监听，但不 accept 任何连接（进程 CPU≈0，持续数分钟）。**定位**：`async def login` 在事件循环里直接跑 bcrypt，结合连接断开的取消风暴把循环卡死；纯读场景压完 3 秒即恢复，对比锁定登录链路。**临时处置**：每个重场景前重启服务保证起点一致；根治方案（login 移出事件循环）列入第 2 周优化验证。这个"假死"本身就是报告里最有价值的发现之一。

## 设计取舍

- **为什么 Locust 而不是 JMeter？** Python 生态统一（和被测系统、API 自动化同一套栈）、脚本即代码可版本管理、自定义 Shape 实现阶梯负载比 JMeter 线程组直观。
- **为什么单 worker 压测？** 先测裸服务真实上限；worker 数量对比本身是优化素材。
- **为什么登录单独建模？** bcrypt 是 CPU 密集操作，混在读写场景会污染数据；分开压才能把"认证开销"和"读写开销"分开定位。
- **为什么造数与压测分离？** 注册走 bcrypt 很贵，放进压测任务等于自己制造瓶颈；造数脚本保证每轮压测数据规模一致，优化前后才可比。
- **为什么用 psutil 而不是 top/free 截图？** 跨平台（项目在 Windows 上跑）、精确盯住 uvicorn 进程、输出 CSV 可与压测时间序列对齐画图，比截图更工程化。

## 面试要点

见 [docs/interview-notes.md](docs/interview-notes.md)（TPS vs QPS、P95/P99 vs 平均值、瓶颈定位交叉验证、WAL 原理等）。
