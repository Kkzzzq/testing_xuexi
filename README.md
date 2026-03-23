# testing_xuexi

## 唯一运行方式

本项目只支持 **Docker Compose** 运行。

### 本地运行

```bash
docker compose down -v
docker compose up --build --abort-on-container-exit --exit-code-from test-runner
