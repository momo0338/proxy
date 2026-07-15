# Proxy Pool Service

Persistent proxy pool service with auto-fetch, validation, SQLite storage, and HTTP API.

## Quick Start

```bash
# Install
uv venv .venv --python 3.11
uv pip install -r requirements.txt

# Run
python main.py serve              # Start HTTP API + auto-refresh daemon
python main.py collect            # Collect proxies only
python main.py validate           # Validate stored proxies
python main.py all                # Collect + validate
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `serve` | Start HTTP API service with auto-refresh |
| `collect` | Fetch proxies from all configured sources |
| `validate` | Validate unvalidated proxies in the store |
| `all` | Collect and validate in sequence |

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--config, -c` | Config file path | — |
| `--host, -h` | Bind host (serve) | `0.0.0.0` |
| `--port, -p` | Bind port (serve) | `8000` |

```bash
python main.py serve --host 0.0.0.0 --port 9000
python main.py collect -c config.json
```

## API Endpoints

### `GET /health`

```json
{"status": "ok", "total": 1234, "valid": 56}
```

### `GET /metrics`

```json
{
  "total": 1234,
  "valid": 56,
  "by_protocol": {"http": 30, "socks5": 26}
}
```

### `GET /proxies`

Query params: `protocol`, `anon`, `country`, `limit`

```bash
curl "http://localhost:8000/proxies?protocol=socks5&limit=10"
```

### `GET /proxy/random`

Query params: `protocol`, `anon`, `country`

```bash
curl "http://localhost:8000/proxy/random?protocol=http"
```

### `POST /refresh`

Triggers background proxy refresh.

```bash
curl -X POST http://localhost:8000/refresh
```

## Configuration

Copy `config.example.json` to `config.json`:

```json
{
  "db_path": "data/proxies.db",
  "refresh_interval_minutes": 30,
  "proxy_expiry_hours": 6,
  "max_concurrency": 50,
  "timeout": 30,
  "max_workers": 20,
  "verify_timeout": 8.0,
  "max_verify": 200,
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

## Project Structure

```
proxy/
├── main.py              # CLI entry point (typer)
├── pyproject.toml       # Project config + ruff/basedpyright
├── requirements.txt     # Dependencies
├── config.example.json  # Example configuration
├── Dockerfile           # Container build
├── src/
│   ├── __init__.py
│   ├── models.py        # ProxyRecord, ProxyProtocol, Anonymity
│   ├── config.py        # Configuration loading
│   ├── store.py         # SQLite storage (ProxyStore)
│   ├── sources.py       # Remote source fetching (TextSource)
│   ├── collector.py     # Proxy collection orchestration
│   ├── validator.py     # Proxy validation with httpx
│   ├── api.py           # FastAPI HTTP routes
│   └── scheduler.py     # APScheduler periodic refresh
├── tests/
│   ├── test_models.py
│   ├── test_store.py
│   ├── test_sources.py
│   ├── test_api.py
│   └── test_config.py
└── output/              # Legacy output files
```

## Docker

```bash
docker build -t proxy-pool .
docker run -p 8000:8000 proxy-pool
```

## Development

```bash
uv pip install -r requirements.txt
ruff check .             # Lint
basedpyright .           # Type check
pytest -q                # Test
```

## Proxy Sources

8 pre-configured GitHub sources:

| Protocol | Sources |
|----------|---------|
| HTTP | TheSpeedX, Monosans, clarketm, ShiftyTR |
| HTTPS | roosterkid |
| SOCKS5 | TheSpeedX, Monosans, Hookzof |
