# 代理池服务（Proxy Pool Service）

持久化的代理池服务：自动抓取各类代理、异步验证（匿名度 / 地理位置 / 健康度 / 过期）、SQLite 存储，并通过 HTTP API 对外提供。

## 快速开始

```bash
# 安装
uv venv .venv --python 3.11
uv pip install -r requirements.txt

# 运行前请先激活虚拟环境，否则会用到缺少依赖的系统 Python
#   source .venv/bin/activate
#   或者直接用 .venv/bin/python main.py ... / uv run python main.py ...

# 运行
python main.py serve              # 启动 HTTP API + 自动刷新守护进程
python main.py collect            # 仅抓取代理
python main.py validate           # 仅验证已存储的代理
python main.py all                # 抓取 + 验证
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `serve` | 启动 HTTP API 服务，并开启周期自动刷新 |
| `collect` | 从所有已配置的源抓取代理 |
| `validate` | 验证库中尚未验证的代理（完成后自动导出可用代理） |
| `all` | 依次执行抓取与验证（完成后自动导出可用代理） |
| `export` | 把库中已验证可用的代理导出到 `data/` 为 JSON / TXT |

### 选项

| 选项 | 说明 | 默认值 |
|------|------|--------|
| `--config, -c` | 配置文件路径 | — |
| `--host, -h` | 绑定地址（serve） | `0.0.0.0` |
| `--port, -p` | 绑定端口（serve） | `8000` |

```bash
python main.py serve --host 0.0.0.0 --port 9000
python main.py collect -c config.json
```

### 验证后导出可用代理

`validate` / `all` 跑完会自动把**可用代理**导出到 `data/` 目录（`--dir` 可改路径），方便手动复制或喂给其他工具。也可单独执行 `python main.py export`。

导出文件（按**协议 × 匿名度**分类）：

| 文件 | 内容 |
|------|------|
| `valid_proxies.json` | 结构化：总数、按协议/匿名度计数、每条含 `address`/`country`/`response_time` |
| `valid_proxies.txt` | 分段文本：`## 协议 / 匿名度 (数量)` 标题下每行一个 `protocol://ip:port` |
| `valid_<协议>.txt` | 每个协议一个扁平文件（如 `valid_socks5.txt`），直接给只认单协议的工具用 |

> 地址均带协议前缀（`http://` / `https://` / `socks5://`），可直接粘进浏览器或代理客户端。

## API 接口

### `GET /health`

健康检查。

```json
{"status": "ok", "total": 1234, "valid": 56}
```

### `GET /metrics`

汇总统计。

```json
{
  "total": 1234,
  "valid": 56,
  "by_protocol": {"http": 30, "socks5": 26}
}
```

### `GET /proxies`

获取有效代理列表。

查询参数：`protocol`、`anon`、`country`、`limit`

```bash
curl "http://localhost:8000/proxies?protocol=socks5&limit=10"
```

### `GET /proxy/random`

随机返回一个有效代理（可用于「每次取一个」的负载场景）。

查询参数：`protocol`、`anon`、`country`

```bash
curl "http://localhost:8000/proxy/random?protocol=http"
```

> 当没有匹配的有效代理时返回 `404`。

### `POST /refresh`

手动触发一次后台代理刷新（抓取 → 验证 → 入库 → 清理过期）。

```bash
curl -X POST http://localhost:8000/refresh
```

## 配置

将 `config.example.json` 复制为 `config.json`：

```json
{
  "db_path": "data/proxies.db",
  "refresh_interval_minutes": 30,
  "proxy_expiry_hours": 6,
  "max_concurrency": 100,
  "timeout": 30,
  "max_workers": 20,
  "verify_timeout": 5.0,
  "quick_probe_timeout": 3.0,
  "max_verify": 200,
  "output_dir": "output",
  "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  "verify_endpoints": ["http://httpbin.org/ip"],
  "anon_check_url": "http://httpbin.org/ip",
  "country_url": "http://ip-api.com/json",
  "sources": [
    {
      "name": "TheSpeedX HTTP",
      "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
      "protocol": "http",
      "format": "ip:port",
      "enabled": true
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `db_path` | SQLite 数据库路径 |
| `refresh_interval_minutes` | 自动刷新周期（分钟） |
| `proxy_expiry_hours` | 代理过期时间（小时）；超过则视为失效并清理 |
| `max_concurrency` | 抓取并发数 |
| `timeout` | 单源抓取超时（秒） |
| `max_workers` | 验证线程数 |
| `verify_timeout` | 完整验证时连接超时（秒） |
| `quick_probe_timeout` | 首轮快筛超时（秒）；死代理只磨这么久 |
| `verify_hard_timeout` | 单代理硬性总超时（秒）；兜底黑洞 DNS/半开连接，0 = `verify_timeout`×2 |
| `max_verify` | 单次最多验证的代理数 |

> **性能与时间说明**：验证默认开启「死代理快速跳过」——先用单个端点 + `quick_probe_timeout`(3s) 快筛，通了才走完整多端点验证（超时 `verify_timeout`=5s）。因为库里约 88% 是死代理，这能把整库重测时间从「每代理跑满所有端点超时」砍掉一大截。想关掉用 `python main.py validate --no-quick-probe`。
>
> 每代理另有 `verify_hard_timeout`（默认 `verify_timeout`×2=10s）硬性总超时，套在 `asyncio.wait_for` 上——专门兜底黑洞 DNS / 半开 TCP 连接这类 httpx 自身超时兜不住的 stall，确保整批永远按「并发数 × 硬上限」有界收工（实测 50 代理并发 50、硬超时 8s 仅需 8.6s）。
>
> **并发数与文件描述符**：`max_concurrency` 是同时打开的 socket 数。macOS 默认 `ulimit -n=256`，所以默认值 100 留了余量；若想开到 800，先放开口子：`ulimit -n 4096` 再跑，否则会撞 `Too many open files`。服务器环境通常 fd 上限很高，可直接调高。
| `verify_endpoints` | 验证用端点列表（多端点取健康度评分） |
| `anon_check_url` | 匿名度检测端点 |
| `country_url` | 地理位置查询端点 |
| `sources` | 代理源列表，每项含 `name` / `url` / `protocol` / `format` / `enabled` |

## 项目结构

```
proxy/
├── main.py              # CLI 入口（typer）
├── pyproject.toml       # 项目配置 + ruff/basedpyright
├── requirements.txt     # 依赖
├── config.example.json  # 配置示例
├── Dockerfile           # 容器构建
├── src/
│   ├── __init__.py
│   ├── models.py        # ProxyRecord、ProxyProtocol、Anonymity
│   ├── config.py        # 配置加载
│   ├── store.py         # SQLite 存储（ProxyStore）
│   ├── sources.py       # 远程源抓取（TextSource）
│   ├── collector.py     # 代理抓取编排
│   ├── validator.py     # 基于 httpx 的代理验证
│   ├── api.py           # FastAPI 路由
│   └── scheduler.py     # APScheduler 周期刷新
├── tests/
│   ├── test_models.py
│   ├── test_store.py
│   ├── test_sources.py
│   ├── test_api.py
│   └── test_config.py
└── output/              # 旧版输出文件
```

## 代理源

已预配置 8 个 GitHub 文本源：

| 协议 | 源 |
|------|----|
| HTTP | TheSpeedX、Monosans、clarketm、ShiftyTR |
| HTTPS | roosterkid |
| SOCKS5 | TheSpeedX、Monosans、Hookzof |

## Docker

```bash
docker build -t proxy-pool .
docker run -p 8000:8000 proxy-pool
```

## 开发

```bash
uv pip install -r requirements.txt
ruff check .             # 代码检查
basedpyright .           # 类型检查
pytest -q                # 测试
```

## 验证说明（匿名度）

验证阶段会检测代理的匿名级别：

- `transparent`（透明）：目标服务器能看见你的真实 IP。
- `anonymous`（匿名）：目标服务器看不见真实 IP，但知道你在使用代理。
- `elite`（高匿）：目标服务器既看不见真实 IP，也察觉不到代理的存在。

返回的每条代理记录包含 `protocol`、`country`、`anonymity`、`response_time`、`last_verified` 等字段，便于调用方按需求筛选。
