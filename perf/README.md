# Performance Scenarios

这个目录只放性能测试相关内容，默认围绕 Dashboard Hub 的读写链路、缓存行为和 Prometheus 指标做验证。

## 现有场景

### hot_read
热点读场景。目标是验证：

- 热点订阅列表是否稳定命中缓存
- 热点分享链接是否稳定命中缓存
- 高比例读流量下 p95 / p99 是否可控

脚本：`perf/locust_hot_read.py`

### write_conflict
写入冲突场景。目标是验证：

- 正常写流量能否持续返回 `201`
- 固定业务键冲突是否稳定返回 `409`
- 写后删缓存链路是否真的发生

脚本：`perf/locust_write_conflict.py`

### cache_penetration
缓存穿透场景。目标是验证：

- 不存在 share token 是否持续打到后端
- 不存在 dashboard UID 是否持续触发 Grafana 回源判断
- `404` 流量会不会拖慢整体响应

脚本：`perf/locust_cache_penetration.py`

### cache_breakdown
缓存击穿场景。目标是验证：

- 单热点订阅列表 key 失效后是否会被并发读打穿
- 回源之后是否能重新形成热点缓存
- 订阅列表接口在击穿周期里是否还能稳住

脚本：`perf/locust_cache_breakdown.py`

### cache_avalanche
缓存雪崩场景。目标是验证：

- 多组热点 `subscriptions / share / dashboard_exists` 是否在同一波次集中失效
- 上游 Grafana 回源是否明显上升
- 多类缓存同时 miss 时核心接口还能不能稳住

脚本：`perf/locust_cache_avalanche.py`

## 常用入口

### 本地直接跑单场景

```bash
python perf/run_local_scenario.py --scenario hot_read
python perf/run_local_scenario.py --scenario cache_penetration
python perf/run_local_scenario.py --scenario cache_breakdown
python perf/run_local_scenario.py --scenario cache_avalanche
```

### 只想看种子数据生成结果

```bash
python perf/bootstrap_perf_data.py
```

### 只想校验 Locust 阈值

```bash
python perf/assert_locust_thresholds.py --csv perf-results/locust_stats.csv --profile cache_breakdown
```

### 只想校验业务信号

```bash
python perf/assert_business_signals.py \
  --before perf-results/metrics-before.json \
  --after perf-results/metrics-after.json \
  --profile cache_avalanche \
  --summary-output perf-results/business-signals-summary.json
```

## 结果怎么读

至少看四类输出：

- `locust_stats.csv`：吞吐、时延、失败数
- `locust-report.html`：整体压测报告
- `metrics-before.json / metrics-after.json`：Prometheus 指标前后快照
- `business-signals-summary.json`：业务层断言结果

不要只看 Locust 的平均响应时间。这个项目里更关键的是：

- 缓存命中 / 未命中有没有按预期变化
- 上游 Grafana 请求量是不是被放大
- 冲突写入是不是稳定形成 `201 + 409` 对照
- 缓存失效后，接口还能不能保持稳定 `200`
