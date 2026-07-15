"""
代理收集器配置
"""

import os
import json
from typing import List, Dict, Any

# 默认代理源配置
DEFAULT_PROXY_SOURCES = [
    # HTTP代理
    {
        "name": "TheSpeedX HTTP",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True
    },
    {
        "name": "Monosans HTTP",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True
    },
    {
        "name": "clarketm HTTP",
        "url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True
    },
    {
        "name": "ShiftyTR HTTP",
        "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "protocol": "http",
        "format": "ip:port",
        "enabled": True
    },
    # HTTPS代理
    {
        "name": "roosterkid HTTPS",
        "url": "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "protocol": "https",
        "format": "ip:port",
        "enabled": True
    },
    # SOCKS5代理
    {
        "name": "TheSpeedX SOCKS5",
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "protocol": "socks5",
        "format": "ip:port",
        "enabled": True
    },
    {
        "name": "Monosans SOCKS5",
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "protocol": "socks5",
        "format": "ip:port",
        "enabled": True
    },
    {
        "name": "Hookzof SOCKS5",
        "url": "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
        "protocol": "socks5",
        "format": "ip:port",
        "enabled": True
    }
]

# 默认配置
DEFAULT_CONFIG = {
    "timeout": 30,
    "max_workers": 20,
    "verify_timeout": 5.0,
    "max_verify": 200,
    "output_dir": "output",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def load_config(config_file: str = None) -> Dict[str, Any]:
    """加载配置文件"""
    config = DEFAULT_CONFIG.copy()
    
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    return config

def load_proxy_sources(config_file: str = None) -> List[Dict]:
    """加载代理源配置"""
    if config_file and os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                if 'sources' in user_config:
                    return user_config['sources']
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    return DEFAULT_PROXY_SOURCES

# 保持向后兼容
PROXY_SOURCES = DEFAULT_PROXY_SOURCES