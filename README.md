# 代理池服务（Proxy Pool Service）

持久化的代理池服务：多源自动抓取、全链路 HTTPS 加密隧道验证、国内高可用 CDN 探测与省份分组、SQLite 持久化存储，提供 RESTful API 以及开箱即用的 Clash Verge / Mihomo 配置文件与动态订阅。

## 核心特性

- **多协议多源采集**：内置抓取 HTTP、HTTPS、SOCKS4、SOCKS5 公开代理源。
- **严格 HTTPS 隧道验证**：100% 采用 HTTPS 加密隧道（`CONNECT`）测试，彻底剔除仅支持明文 HTTP 转发、无法访问加密网站的残废节点。
- **国内 IP 专用 CDN 链路**：智能识别中国大陆节点，采用国内高可用 CDN（小米 MIUI 204、华为 204、IPIP、百度）进行境内连通性与低延迟探测，杜绝境内节点因连外网超时被误杀。
- **Clash Verge 开箱即用**：自动生成带 Fake-IP DNS、分流规则、省份分组（江苏/北京/上海/广东/浙江等）与国内自动测速优选（`url-test`）的完整配置文件。
- **动态订阅 API**：内置 `/clash` 与 `/subscription` 接口，可直接作为 Clash Verge 的远程订阅链接使用。
- **CI 自动化驱动**：GitHub Actions 每日定时刷新并回写最新检测产物，免运维、零服务器即可直接食用。

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
| `serve` | 启动 HTTP API 服务，并开启后台周期自动刷新 |
| `all` | 依次执行抓取与验证（完成后自动导出可用代理） |
| `collect` | 从所有已配置的公开源抓取代理入库 |
| `validate` | 验证库中尚未验证的代理（完成后自动导出可用代理） |
| `export` | 把库中已验证可用的代理导出到 `data/` 为 JSON / TXT |
| `diagnose` | 探测测试端点连通性，并抽取样本代理打印详细诊断日志 |

### 选项

```bash
# 指定端口启动服务
python main.py serve --host 0.0.0.0 --port 9000

# 验证选项: 默认开启快速探测(--quick-probe), 可加 --include-failed 重试历史失效节点
python main.py validate --include-failed

# 导出选项: 默认导出所有 is_valid=1 的代理; 加 --fresh 仅导出新鲜窗口内验证的代理
python main.py export --fresh
```

### 验证后导出可用代理

`validate` / `all` 跑完会自动把**可用代理**导出到 `data/` 目录（`--dir` 可改路径），方便手动复制或喂给其他工具。也可单独执行 `python main.py export`。

默认导出全部 `is_valid=1` 的代理；加 `--fresh` 只导最近验证过的（按配置的 `proxy_expiry_hours` 过滤）。

导出文件：

| 文件 | 内容 |
|------|------|
| `valid_<协议>.txt` | 每个协议一个扁平文件（`valid_http.txt` / `valid_socks5.txt`），每行一个 `protocol://ip:port`，给只认单协议的工具直接用 |
| `valid_proxies.json` | 结构化：总数、按协议计数、每条含 `address`/`country`/`response_time` |
| `clash_config.yaml` | 完整 Clash Verge / Mihomo 配置文件（含按省份/地区分组与国内自动测速优选） |

## API 接口

服务启动后（默认 `http://localhost:8000`），对外提供以下 RESTful 接口与动态订阅：

### `GET /clash` 或 `GET /subscription`（动态 Clash 订阅）

返回开箱即用的完整 Clash Verge / Mihomo YAML 配置文件，可直接在 Clash Verge 的「订阅」中填入此 URL 自动更新节点。

- 查询参数：`country`（可选，过滤特定国家代码，如 `CN`）

```bash
curl "http://localhost:8000/clash?country=CN"
```

### `GET /proxies`

获取有效代理列表。

查询参数：
- `protocol`：协议过滤（`http` / `https` / `socks4` / `socks5`）
- `anon`：匿名度过滤（`transparent` / `anonymous` / `elite`）
- `country`：国家代码过滤（如 `CN`、`US`）
- `fresh`：是否仅返回新鲜窗口内的代理（布尔值，默认 `false`）
- `limit`：返回条数上限

```bash
curl "http://localhost:8000/proxies?protocol=socks5&country=CN&limit=10"
```

### `GET /proxy/random`

随机返回一个有效代理（可用于「每次取一个」的爬虫场景）。

查询参数：`protocol`、`anon`、`country`、`fresh`（默认 `true`，优先提取新鲜活跃节点）

```bash
curl "http://localhost:8000/proxy/random?protocol=http"
```

> 当没有匹配的有效代理时返回 `404`。

### `GET /health`

健康检查。

```json
{"status": "ok", "total": 17607, "valid": 138}
```

### `GET /metrics`

汇总统计。

```json
{
  "total": 17607,
  "valid": 138,
  "by_protocol": {"http": 18, "socks5": 120}
}
```

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
  "verify_endpoints": [
    "https://api.ipify.org?format=json",
    "https://ipinfo.io/json",
    "https://ip.my-ip.io/json"
  ],
  "china_verify_endpoints": [
    "https://connect.rom.miui.com/generate_204",
    "https://connectivitycheck.platform.hicloud.com/generate_204",
    "https://myip.ipip.net/json",
    "https://www.baidu.com"
  ],
  "anon_check_url": "https://ipinfo.io/json",
  "country_url": "https://ip-api.com/json",
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
| `max_concurrency` | 验证并发数（默认 100 兼容 macOS fd 上限；服务器可调高） |
| `timeout` | 单源抓取超时（秒） |
| `max_workers` | 验证线程数 |
| `verify_timeout` | 完整验证时连接超时（秒） |
| `quick_probe_timeout` | 首轮快筛超时（秒）；死代理只磨这么久 |
| `verify_hard_timeout` | 单代理硬性总超时（秒）；兜底黑洞 DNS/半开连接，0 = `verify_timeout`×2 |
| `max_verify` | 单次最多验证的代理数 |
| `verify_endpoints` | 通用 HTTPS 验证端点列表（严格走 HTTPS CONNECT 加密隧道） |
| `china_verify_endpoints` | 国内节点专用测试端点列表（包含国内高可用 CDN 204 与 IPIP/百度） |
| `anon_check_url` | 匿名度检测端点 |
| `country_url` | 地理位置查询端点 |
| `sources` | 代理源列表，每项含 `name` / `url` / `protocol` / `format` / `enabled` |

> **性能与验证安全说明**：
> 1. **全链路 HTTPS 隧道**：所有测试端点强制使用 HTTPS。不支持 `CONNECT` 加密隧道的明文 HTTP 代理会在握手阶段直接报错淘汰，避免导出不能走 HTTPS 流量的残废节点。
> 2. **国内 IP 专用路由**：境内 IP 会自动路由至国内高可用 CDN（小米 MIUI 204、华为 204、IPIP）进行测试，避免因访问境外端点丢包或超时被误杀。
> 3. **快筛机制**：先用单个端点 + `quick_probe_timeout`(3s) 快筛，通了才走完整验证。每代理另有 `verify_hard_timeout` 硬性超时（`asyncio.wait_for`），杜绝黑洞 DNS 拖垮批次。
> 4. **并发与文件描述符**：`max_concurrency` 默认 100 留有安全余量（macOS 默认 `ulimit -n=256`）。如在服务器大并发运行，建议先执行 `ulimit -n 4096`。

## 项目结构

```
proxy/
├── main.py              # CLI 入口（typer）
├── pyproject.toml       # 项目配置 + ruff/basedpyright
├── requirements.txt     # 依赖
├── config.example.json  # 配置示例
├── Dockerfile           # 容器构建
├── data/                # 运行产物: proxies.db + 导出的文本/JSON/Clash 配置
│   ├── proxies.db       # SQLite 本地持久化数据库
│   ├── valid_http.txt   # 可用 HTTP 代理列表
│   ├── valid_socks5.txt # 可用 SOCKS5 代理列表
│   ├── valid_proxies.json # 结构化代理清单
│   └── clash_config.yaml # 开箱即用的 Clash Verge / Mihomo 配置文件
├── scripts/
│   └── gen_clash.py     # Clash Verge 完整配置生成脚本（含省份分组）
├── src/
│   ├── models.py        # ProxyRecord、ProxyProtocol、Anonymity
│   ├── config.py        # 配置加载
│   ├── store.py         # SQLite 存储（ProxyStore）
│   ├── sources.py       # 远程源抓取（TextSource）
│   ├── collector.py     # 代理抓取编排
│   ├── validator.py     # 基于 httpx 的全 HTTPS 隧道与国内 CDN 校验器
│   ├── exporter.py      # 文本与 JSON 文件导出
│   ├── diagnostics.py   # 端点连通性与样本代理诊断
│   ├── scheduler.py     # APScheduler 周期自动刷新守护
│   └── api.py           # FastAPI RESTful 接口与动态 /clash 订阅
├── tests/
│   ├── test_api.py
│   ├── test_config.py
│   ├── test_diagnostics.py
│   ├── test_exporter.py
│   ├── test_gen_clash.py
│   ├── test_models.py
│   ├── test_sources.py
│   ├── test_store.py
│   └── test_validator.py
```

## 代理源

已预配置 8 个 GitHub 文本源：

| 协议 | 源 |
|------|----|
| HTTP | TheSpeedX、Monosans、clarketm、ShiftyTR |
| HTTPS | roosterkid |
| SOCKS5 | TheSpeedX、Monosans、Hookzof |

## 导出为 Clash / mihomo 配置

把已验证可用的代理转成 Clash Verge / mihomo 可直接导入使用的完整配置文件，纯生成文件、**不修改任何系统代理设置**：

```bash
python scripts/gen_clash.py                 # 生成 data/clash_config.yaml
python scripts/gen_clash.py --data-dir data --out /tmp/clash.yaml
```

产物 `data/clash_config.yaml` 包含完整 Profile：

- `mixed-port`, `dns` (Fake-IP 模式与国内优质 DNS), `rules` 基础配置
- `proxies:` 全部可用节点（根据 IP 与归属地标注国家/省份/运营商/协议，如 `🇨🇳 江苏电信 ...`）
- `proxy-groups:`
  - `🚀 节点选择`：总控策略组
  - `⚡ 自动优选(国内)`：基于国内测速端点的 `url-test` 延迟最低优选
  - `🇨🇳 全部国内` / 各省份组（江苏、北京、上海、浙江、广东、四川等）
  - `🌍 海外节点`

**使用方式**：可直接在 Clash Verge 的「配置 / 订阅」中点击「导入」，选择该 YAML 文件直接使用，无需手动合并配置。

## 自动部署（GitHub Actions）

仓库已配置 `.github/workflows/daily.yml`：每天 **UTC 0 点（北京时间 8:00）** 自动执行一次完整链路 `collect → validate → export → gen_clash`，并把产物用 `GITHUB_TOKEN` 提交回本仓库的 `main` 分支。无需后端进程，纯 CI 驱动。

- 手动触发：GitHub → Actions → Daily Proxy Check → Run workflow
- 产物：每次 run 后 `data/valid_http.txt`、`data/valid_socks5.txt`、`data/valid_proxies.json`、`data/clash_config.yaml` 自动更新并回写

### 直接食用（Raw 直链）

仓库为公开仓库，其他应用/脚本可直接拉取最新清单，无需克隆：

```bash
# 可用 HTTP 代理（每行 protocol://host:port）
curl -fsSL https://raw.githubusercontent.com/momo0338/proxy/main/data/valid_http.txt

# 可用 SOCKS5 代理
curl -fsSL https://raw.githubusercontent.com/momo0338/proxy/main/data/valid_socks5.txt

# Clash Verge / mihomo 完整配置（可直接导入订阅/配置）
curl -fsSL https://raw.githubusercontent.com/momo0338/proxy/main/data/clash_config.yaml
```

Clash Verge 用户可直接将 Raw 链接填入「新建订阅」或下载本地 YAML 文件导入配置，开箱即用。

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

## 验证与匿名度说明

### 1. 严格 HTTPS 加密隧道
测试端点全面淘汰纯明文 HTTP，100% 走 HTTPS 握手。普通代理若仅支持明文转发、无法进行 `CONNECT` 隧道加密，会直接在验证阶段被剔除，保证留下的代理在现代 HTTPS 网站上均能正常建立连接。

### 2. 国内节点 CDN 智能路由
国内 IP 会自动优先使用小米 MIUI CDN（`connect.rom.miui.com/generate_204`）、华为 CDN、IPIP 等国内高可用链路进行验证，确保境内代理快速响应，避免因向境外发送请求导致的握手超时。

### 3. 匿名度级别

- `transparent`（透明）：目标服务器能看见你的真实 IP。
- `anonymous`（匿名）：目标服务器看不见真实 IP，但知道你在使用代理。
- `elite`（高匿）：目标服务器既看不见真实 IP，也察觉不到代理的存在。

返回的每条代理记录包含 `protocol`、`country`、`anonymity`、`response_time`、`last_verified` 等字段，便于调用方按需求筛选。
