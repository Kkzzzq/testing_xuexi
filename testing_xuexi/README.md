# testing_xuexi

基于你当前的 **Grafana API 自动化项目** 扩展而来，保留原有主线，并新增一个围绕 dashboard 资源的 **Dashboard Hub（仪表盘分享/订阅服务）**。

## 改造后的能力

- Grafana API 自动化测试（dashboard / org / user）
- SQLite 数据校验（Grafana 自身）
- Dashboard Hub 业务服务
  - 订阅创建 / 查询 / 删除
  - 分享链接创建 / 查询
  - dashboard 摘要查询
- MySQL 业务落库校验
- Redis 缓存校验
- Docker Compose 一键拉起完整环境
- Pytest + Requests + Allure 自动化测试
- GitHub Actions CI
- Locust 压测
- Prometheus + Grafana 指标可视化

## 目录说明

```text
testing_xuexi/
├─ apps/dashboard_hub/          # 新增业务服务
├─ config/                      # 全局配置
├─ data/                        # 测试数据工厂
├─ helpers/                     # 装饰器、schema、清理工具
├─ monitoring/                  # Prometheus 配置
├─ perf/                        # Locust 压测脚本
├─ services/                    # Grafana / Dashboard Hub / DB / Cache 服务封装
├─ src/                         # CLI 入口
├─ tests/                       # 自动化测试
├─ .github/workflows/ci.yml     # GitHub Actions
├─ docker-compose.yml           # 一键启动完整环境
└─ requirements.txt
```

## 启动方式

```bash
docker compose down -v --remove-orphans
docker compose up --build --exit-code-from test-runner
```

## 单独查看 Dashboard Hub

- Dashboard Hub: `http://localhost:8000/docs`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

## 压测

```bash
docker compose up --build grafana mysql redis dashboard-hub prometheus
locust -f perf/locustfile.py --host http://localhost:8000
```
