# 代理收集器

从多个GitHub免费代理列表项目收集代理，支持HTTP、HTTPS和SOCKS5协议。

## 快速开始

```bash
pip install requests
python main.py collect      # 收集代理
python main.py validate     # 验证代理
python main.py all          # 收集并验证
```

## 命令行参数

| 命令 | 说明 |
|------|------|
| `collect` | 收集代理 |
| `validate` | 验证代理 |
| `all` | 收集并验证 |

| 参数 | 说明 |
|------|------|
| `-o, --output` | 输出目录 |
| `-c, --config` | 配置文件路径 |
| `-f, --proxy-file` | 代理文件路径 |
| `-m, --max-verify` | 最大验证数量 |

```bash
python main.py collect -o my_output          # 指定输出目录
python main.py collect -c config.json        # 使用配置文件
python main.py validate -m 500               # 验证500个代理
```

## 项目结构

```
proxy/
├── main.py                 # 主入口
├── config.example.json     # 配置示例
├── src/                    # 源代码
│   ├── config.py          # 配置
│   ├── proxy.py           # 代理模型
│   ├── utils.py           # 工具函数
│   ├── collector.py       # 收集器
│   └── validator.py       # 验证器
└── output/                 # 输出文件
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `all_proxies.txt` | 所有代理（带协议前缀） |
| `http_proxies.txt` | HTTP代理 |
| `socks5_proxies.txt` | SOCKS5代理 |
| `verified_proxies_all.txt` | 验证后的有效代理 |
| `verified_report_all.json` | 验证详细报告 |

## Python 使用

### 加载代理

```python
with open('output/http_proxies.txt', 'r') as f:
    proxies = [line.strip() for line in f if line.strip()]
```

### 使用代理请求

```python
import requests

proxy = f"http://{proxies[0]}"
response = requests.get(
    'http://httpbin.org/ip',
    proxies={'http': proxy, 'https': proxy},
    timeout=10
)
print(response.json())
```

### 验证代理

```python
from src.validator import ProxyValidator

validator = ProxyValidator(output_dir='output')
result = validator.validate_proxy('http://95.211.174.135:3128')
print(f"有效: {result['is_valid']}, 耗时: {result['response_time']}s")
```

### 代理轮换

```python
import random

def fetch_with_rotation(urls, proxies):
    for url in urls:
        proxy = random.choice(proxies)
        response = requests.get(url, proxies={'http': proxy, 'https': proxy}, timeout=10)
        yield response.text
```

### 异步请求

```python
import asyncio
import aiohttp

async def fetch_async(url, proxy):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, proxy=proxy) as resp:
            return await resp.text()
```

## 配置文件

复制 `config.example.json` 为 `config.json`：

```json
{
  "output_dir": "output",
  "timeout": 30,
  "max_workers": 20,
  "sources": [
    {
      "name": "源名称",
      "url": "https://raw.githubusercontent.com/user/repo/branch/file.txt",
      "protocol": "http",
      "enabled": true
    }
  ]
}
```

使用配置文件：
```bash
python main.py collect -c config.json
```

## 代理源

| 协议 | 来源 |
|------|------|
| HTTP | TheSpeedX, Monosans |
| SOCKS5 | TheSpeedX, Monosans, Hookzof |

## 注意事项

1. 免费代理不稳定，建议定期重新收集
2. 使用前建议验证代理可用性
3. 避免通过免费代理传输敏感信息

## 许可证

MIT License
