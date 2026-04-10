# Grafana Dashboard Hub Test Platform

一个围绕 **Grafana 后端场景** 构建的自动化测试与性能验证项目。  
项目不仅覆盖 Grafana 原生 HTTP API，还扩展了一层自研 **Dashboard Hub** 服务，用来补充 **订阅、分享链接、Dashboard 摘要** 等业务能力，并把 **接口测试、数据库校验、缓存校验、性能压测、监控观测、CI 报告** 串成一条完整链路。

---

## 项目定位

这个仓库不是单纯的“接口能不能调通”的练习项目，而是一套更接近真实测开场景的集成测试工程：

- **Grafana API 自动化测试**：用户、组织、文件夹、Dashboard 等核心接口
- **Dashboard Hub 业务测试**：订阅、分享链接、摘要能力
- **多层校验**：不仅校验 HTTP 返回，还补充 **Grafana SQLite / MySQL / Redis** 校验
- **性能与监控闭环**：通过 **Locust + Prometheus** 验证吞吐、时延、缓存命中和摘要来源
- **CI 报告输出**：通过 **GitHub Actions + Allure** 自动产出测试报告
- **AI 辅助分析**：测试执行后可基于 Allure 结果生成 AI 分析报告

---

## 核心能力

### 1. Grafana 原生 API 自动化测试
覆盖以下对象的正向与负向场景：

- 用户创建、删除、改密
- 组织创建、加人、改角色、查询
- 文件夹创建
- Dashboard 创建、查询、删除
- 鉴权错误与资源不存在等异常场景

### 2. 自研 Dashboard Hub 服务
在 Grafana 之上扩了一层 FastAPI 服务，补充测试项目里更有“业务味道”的能力：

- **订阅管理**：创建订阅、查询订阅、删除订阅
- **分享链接**：创建分享链接、读取链接、删除链接、过期校验
- **Dashboard 摘要**：读取 Dashboard 元信息与 panel 配置，生成中文摘要

### 3. 多层数据校验
项目不是只看接口返回，而是把校验做到了不同数据层：

- **Grafana SQLite**：验证通过 API 创建的用户是否真实落到 Grafana 内部库
- **MySQL**：验证 Dashboard Hub 的订阅、分享链接是否真实持久化
- **Redis**：验证订阅列表、分享链接、摘要缓存是否命中、是否失效

### 4. AI 摘要与回退机制
Dashboard 摘要能力支持两种输出方式：

- 配置了 `AI_API_KEY` 时，调用 AI 生成摘要
- 未配置或 AI 调用失败时，自动回退到本地 fallback 摘要

这样既能体现 AI 集成能力，也不会因为外部依赖不可用导致接口整体失效。

### 5. 性能测试与观测闭环
通过 Locust 对 Dashboard Hub 做并发压测，当前重点覆盖：

- 查询订阅列表
- 读取分享链接
- 正常创建订阅
- 重复创建订阅冲突场景
- 不存在 key / 不存在 dashboard 读取（缓存穿透）
- 单热点 key 高频读取并反复失效（缓存击穿）
- 多组热点 key 批量失效 / 同时过期（缓存雪崩）

配合 Prometheus 暴露的指标，可观察：

- 请求量
- 请求时延
- 缓存命中 / 未命中
- 上游 Grafana 请求与失败
- 写后缓存失效是否生效
- 摘要来自 AI 还是 fallback

---

## 技术栈

### 测试与服务
- Python 3.11
- Pytest
- Requests
- FastAPI
- SQLAlchemy
- Allure

### 数据与中间件
- Grafana
- MySQL
- Redis
- SQLite（Grafana 内部库只读校验）

### 编排与观测
- Docker
- Docker Compose
- Prometheus
- Locust

### CI / 工程化
- GitHub Actions
- GitHub Pages（发布 Allure 报告）

---

## 项目架构

```text
Pytest / Locust
    │
    ├─ 调用 Grafana HTTP API
    │      ├─ 用户 / 组织 / Folder / Dashboard
    │      └─ Grafana SQLite 只读校验
    │
    └─ 调用 Dashboard Hub（FastAPI）
           ├─ 订阅管理
           ├─ 分享链接
           ├─ Dashboard 摘要
           ├─ MySQL 持久化
           ├─ Redis 缓存
           └─ Prometheus 指标暴露
```

---

## Dashboard Hub API

### 订阅
- `POST /api/v1/subscriptions`：创建订阅
- `GET /api/v1/dashboards/{dashboard_uid}/subscriptions`：查询某个 Dashboard 的订阅列表
- `DELETE /api/v1/subscriptions/{subscription_id}`：删除订阅

### 分享链接
- `POST /api/v1/share-links`：创建分享链接
- `GET /api/v1/share-links/{token}`：读取分享链接
- `DELETE /api/v1/share-links/{token}`：删除分享链接

### 摘要
- `GET /api/v1/dashboards/{dashboard_uid}/summary`：读取 Dashboard 摘要

### 健康检查与指标
- `GET /health`
- `GET /metrics`

---

## 当前测试覆盖

### Grafana API
- 创建 Folder 并校验响应结构
- 创建 Dashboard 并校验响应结构
- 错误鉴权访问 Dashboard
- 查询不存在的 Dashboard
- 创建用户 / 删除用户 / 修改密码
- 创建已存在用户 / 非法请求
- 创建组织 / 加用户到组织 / 修改组织内角色 / 查询组织

### Dashboard Hub API
- 成功创建订阅
- 成功创建分享链接
- 成功查询订阅列表
- 成功读取分享链接
- 成功读取 Dashboard 摘要
- 未知 Dashboard 创建订阅返回 404
- 重复订阅返回 409
- 非法 channel 返回 422
- 未知分享 token 返回 404
- 过期分享链接返回 410

### 数据层校验
- 订阅写入 MySQL 后可查到
- 分享链接写入 MySQL 后 view_count 会随读取递增
- 通过 API 创建的 Grafana 用户能在 SQLite 中查到

### 缓存层校验
- 订阅列表缓存命中与删除失效
- 分享链接缓存命中与删除失效
- Dashboard 摘要缓存命中

### 性能测试
- 热点读：订阅列表、分享链接
- 写场景：正常创建订阅
- 并发冲突：重复订阅创建
- 缓存穿透：不存在 token / 不存在 dashboard 持续读取
- 缓存击穿：单热点订阅列表 key 反复失效后回源
- 缓存雪崩：多组热点 subscriptions / share / dashboard_exists 批量失效

---

## 目录结构

```text
grafana-dashboard-hub-test-platform/
├─ apps/dashboard_hub/             # Dashboard Hub 服务
│  └─ app/
│     ├─ main.py                   # FastAPI 入口
│     ├─ crud.py                   # 业务逻辑：订阅 / 分享 / 摘要
│     ├─ models.py                 # MySQL 表模型
│     ├─ schemas.py                # 请求 / 响应模型
│     ├─ metrics.py                # Prometheus 指标
│     ├─ cache.py                  # Redis 缓存操作
│     ├─ ai_client.py              # AI 摘要客户端
│     └─ init_db.py                # 服务启动时建表
│
├─ config/                         # 全局配置
├─ data/                           # 测试数据工厂
├─ helpers/                        # 装饰器、schema、清理工具
├─ monitoring/                     # Prometheus 配置
├─ perf/                           # Locust 压测脚本
├─ services/                       # Grafana / Dashboard Hub / DB / Redis 访问封装
├─ src/                            # CLI 入口（prepare / cleanup / run）
├─ tests/                          # fixture、上下文、资源管理、测试用例
├─ tools/                          # AI 测试分析工具
├─ docker-compose.yml              # 一键拉起完整环境
└─ .github/workflows/              # CI 与性能测试工作流
```

---

## 快速开始

### 环境要求
- Docker
- Docker Compose
- Python 3.11（本地直跑时）
- 可选：`AI_API_KEY`，用于开启 AI 摘要与 AI 测试分析

### 1. 清理旧环境

```bash
docker compose down -v --remove-orphans
```

### 2. 启动完整环境并执行测试

```bash
docker compose up --build --exit-code-from test-runner
```

这个命令会自动完成：

- 启动 Grafana / MySQL / Redis / Dashboard Hub / Prometheus
- 等待依赖服务健康检查通过
- 执行 Pytest
- 输出 Allure 原始结果

### 3. 本地直接执行测试

```bash
python -m src.main run --marker smoke --alluredir=allure-results
```

### 4. 仅准备共享测试资源

```bash
python -m src.main prepare
```

### 5. 清理共享测试资源

```bash
python -m src.main cleanup
```

### 6. 本地运行性能测试场景

先保证服务已经起来：

```bash
docker compose up -d --build grafana mysql redis dashboard-hub prometheus
```

然后可以直接用本地脚本跑单个场景，它会自动：

- 生成压测种子数据
- 执行 Locust
- 抓取前后指标快照
- 校验时延阈值
- 校验业务信号

示例：

```bash
python perf/run_local_scenario.py --scenario hot_read
python perf/run_local_scenario.py --scenario write_conflict
python perf/run_local_scenario.py --scenario cache_penetration
python perf/run_local_scenario.py --scenario cache_breakdown
python perf/run_local_scenario.py --scenario cache_avalanche
```

如果想覆盖默认并发参数，也可以直接改：

```bash
python perf/run_local_scenario.py --scenario cache_avalanche --users 180 --rate 30 --duration 6m
```

执行结果会落到 `perf-results/local-<scenario>-<timestamp>/`，重点看这些文件：

- `locust_stats.csv`：吞吐、p95、p99、失败数
- `metrics-before.json` / `metrics-after.json`：压测前后指标快照
- `business-signals-summary.json`：业务信号断言汇总
- `locust-report.html`：Locust HTML 报告

### 7. 三类缓存场景怎么理解

#### 缓存穿透
这里不是简单重复读同一个不存在 key，而是持续生成新的非法 token 和新的非法 dashboard UID，避免请求被同一个 key“误当成热点”。
重点观察：

- `share_link` 缓存 miss
- `dashboard_exists` 缓存 miss
- `dashboard_by_uid|404` 的上游回源
- 业务接口 `404` 是否稳定增长

#### 缓存击穿
这里聚焦单个热点订阅列表 key。先预热，再按固定间隔反复删 `dashhub:subscriptions:{dashboard_uid}`，制造“热点 key 刚失效就被大量并发读打穿”的效果。
重点观察：

- `subscriptions` 缓存 miss 是否增长
- miss 之后 hit 是否也继续增长
- 订阅列表 `200` 是否稳定

#### 缓存雪崩
这里不是只删一个 key，而是对多组热点 key 分波次一起删：

- `dashhub:subscriptions:*`
- `dashhub:share:*`
- `dashhub:dashboard_exists:*`

再配合较短 TTL，让它更接近“同一批缓存集中失效”。
重点观察：

- 多类缓存 miss 是否同时抬升
- `dashboard_by_uid|200` 是否明显上升
- 订阅和分享接口 `200` 是否还能稳住

---

## 性能测试

当前仓库提供了基于 Locust 的 Dashboard Hub 压测脚本，并按场景拆成独立文件。

### 已提供的压测脚本
- `perf/locust_hot_read.py`：热点读场景，重点覆盖订阅列表与分享链接读取
- `perf/locust_write_conflict.py`：并发写冲突场景，重点覆盖重复订阅创建
- `perf/locust_cache_penetration.py`：缓存穿透场景，重点覆盖不存在资源读取
- `perf/locust_cache_breakdown.py`：缓存击穿场景，重点覆盖热点 key 高频读取

### 本地执行前置条件

先保证以下服务已经启动：
- Grafana
- Dashboard Hub
- MySQL
- Redis

然后执行种子脚本，为压测准备 dashboard、subscription 和 share link 数据：

```bash
python perf/bootstrap_perf_data.py
```

脚本会输出一组 `LOCUST_*` 变量，至少需要把下面这些变量导出到当前 shell：
- `LOCUST_DASHBOARD_UIDS`
- `LOCUST_SHARE_TOKENS`
- `LOCUST_HOT_DASHBOARD_UID`
- `LOCUST_HOT_SHARE_TOKEN`
- `LOCUST_CONFLICT_DASHBOARD_UID`
- `LOCUST_CONFLICT_USER_LOGIN`

### 本地执行示例

Web UI 模式：

```bash
locust -f perf/locust_hot_read.py --host http://localhost:8000
```

无头模式示例：

```bash
locust -f perf/locust_hot_read.py \
  --host http://localhost:8000 \
  --headless \
  -u 20 -r 5 -t 3m
```

并发写冲突示例：

```bash
locust -f perf/locust_write_conflict.py \
  --host http://localhost:8000 \
  --headless \
  -u 40 -r 10 -t 3m
```

说明：
- `write_conflict` 场景会先对固定 dashboard + 固定 user_login + channel=email 预种一条订阅，再持续并发打同一业务键，冲突结果更稳定。
- `cache_breakdown` 场景会按固定时间间隔反复删除单个热点 subscriptions key，持续制造“删 key → 回源 → 回填 → 再删 key”。
- `cache_penetration` 场景持续请求不存在 token 和不存在 dashboard，重点看 404、cache miss 和 Grafana 404 回源。
- `cache_avalanche` 场景会先预热多组热点 key，再批量删掉 dashboard_exists / subscriptions / share_link 热点缓存，模拟同批热点同时过期。
- 当前 README 不再使用 `perf/locustfile.py`，因为仓库里实际已经拆成多个场景文件
- 当前热点读压测主要覆盖订阅列表与分享链接，不再把摘要读取写成已覆盖场景

---

## 监控指标

Dashboard Hub 通过 `/metrics` 暴露 Prometheus 指标，重点包括：

- `dashboard_hub_requests_total`
- `dashboard_hub_request_latency_seconds`
- `dashboard_hub_cache_hit_total`
- `dashboard_hub_cache_miss_total`
- `dashboard_hub_grafana_requests_total`
- `dashboard_hub_grafana_request_failures_total`
- `dashboard_hub_cache_invalidations_total`
- `dashboard_hub_subscription_conflicts_total`
- `dashboard_hub_summary_source_total`

这些指标可以帮助判断：

- 哪类接口最热
- 哪类接口最慢
- Redis 缓存是否真正起作用
- 上游 Grafana 是否拖慢或打断业务链路
- 写操作后缓存是否按预期失效
- 冲突写场景是否被正确识别
- 摘要主要来自 AI 还是 fallback

---

## 服务地址

本地通过 Docker Compose 启动后，可访问：

- Grafana：`http://localhost:3000`
- Dashboard Hub Docs：`http://localhost:8000/docs`
- Dashboard Hub Health：`http://localhost:8000/health`
- Prometheus：`http://localhost:9090`

---

## CI / 报告

仓库已经配置 GitHub Actions：

### `ci.yml`
在 push 到 `main` 或手动触发时执行：

- 拉起 Docker Compose 环境
- 运行测试
- 生成 Allure 报告
- 上传 Allure artifact
- 调用 AI 测试分析脚本
- 将 Allure 报告发布到 GitHub Pages

### `perf.yml`
手动触发性能测试：

- 拉起 Grafana / MySQL / Redis / Dashboard Hub
- 自动创建压测所需 Dashboard 与分享链接
- 执行 Locust headless 压测
- 上传性能结果 artifact

---

## 项目亮点

### 1. 不只测接口返回，而是补多层校验
很多测试项目只断言状态码和响应体，这个项目额外补了：

- Grafana SQLite 校验
- MySQL 落库校验
- Redis 缓存命中 / 失效校验

### 2. 不是纯 Grafana API 测试，而是扩展了真实业务层
自建 Dashboard Hub 后，项目从“接口调用”升级成了“带业务语义的服务测试”：

- 订阅冲突
- 分享链接过期
- 摘要生成
- 缓存失效

### 3. 性能测试和监控闭环完整
项目不是“压了就结束”，而是能结合 Prometheus 指标一起分析服务在并发下的真实表现。

### 4. CI 结果可沉淀
测试结果不仅有 Allure 报告，还能基于 Allure 结果继续做 AI 分析，便于快速定位失败方向。

---

## 注意事项

1. `AI_API_KEY` 为空时，Dashboard 摘要会自动走 fallback 逻辑，这属于预期行为。  
2. Grafana 用户的 SQLite 校验依赖本地 / Docker 环境共享同一份 Grafana 数据目录。  
3. Locust 压测前需要先准备好有效的 `dashboard_uid` 和 `share_token`。  
4. Dashboard Hub 的缓存默认 TTL 为 `120` 秒，可通过环境变量调整。  

---

## 后续可扩展方向

- 增加 Dashboard Hub 的鉴权与权限测试
- 增加更细的异常注入场景，如 MySQL / Redis 不可用
- 为性能测试补充阈值断言与基线对比
- 增加 Grafana Dashboard 面板展示 Prometheus 指标
- 将 AI 测试分析结果进一步结构化，形成失败归因模板

---

## License

MIT


## 性能测试增强

已补充种子数据准备、阈值校验、指标快照与 HTML 报告生成。
