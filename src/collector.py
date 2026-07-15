"""
代理收集器
"""

import requests
import re
from typing import List, Set, Dict
from datetime import datetime

from .config import PROXY_SOURCES, DEFAULT_CONFIG, load_config, load_proxy_sources
from .proxy import Proxy
from .utils import (
    ensure_dir,
    get_timestamp,
    save_json,
    save_text,
    print_separator,
    print_header,
    print_stats
)

class ProxyCollector:
    """代理收集器"""
    
    def __init__(self, output_dir: str = None, config_file: str = None):
        self.config = load_config(config_file)
        self.output_dir = output_dir or self.config["output_dir"]
        self.proxies: List[Proxy] = []
        self.unique_proxies: Set[str] = set()
        self.sources = [s for s in load_proxy_sources(config_file) if s.get("enabled", True)]
        
        ensure_dir(self.output_dir)
    
    def fetch_file(self, url: str) -> str:
        """从URL获取文件内容"""
        try:
            headers = {
                'User-Agent': self.config["user_agent"]
            }
            response = requests.get(url, headers=headers, timeout=self.config["timeout"])
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"  获取失败: {e}")
            return ""
    
    def collect_from_source(self, source: Dict) -> List[Proxy]:
        """从单个源收集代理"""
        print(f"正在获取: {source['name']}...")
        
        content = self.fetch_file(source['url'])
        if not content:
            return []
        
        proxies = []
        for line in content.strip().split('\n'):
            proxy = Proxy.from_line(line, source['protocol'], source['name'])
            if proxy:
                proxy_key = f"{proxy.ip}:{proxy.port}"
                if proxy_key not in self.unique_proxies:
                    self.unique_proxies.add(proxy_key)
                    proxies.append(proxy)
        
        print(f"  找到 {len(proxies)} 个代理")
        return proxies
    
    def collect_all(self) -> List[Proxy]:
        """从所有源收集代理"""
        print_header("GitHub免费代理收集器")
        print(f"开始时间: {get_timestamp()}")
        print(f"代理源数量: {len(self.sources)}")
        print()
        
        for source in self.sources:
            proxies = self.collect_from_source(source)
            self.proxies.extend(proxies)
        
        return self.proxies
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        stats = {
            "total_collected": len(self.proxies),
            "unique_proxies": len(self.unique_proxies),
            "protocols": {},
            "sources": {}
        }
        
        for proxy in self.proxies:
            # 统计协议
            if proxy.protocol not in stats["protocols"]:
                stats["protocols"][proxy.protocol] = 0
            stats["protocols"][proxy.protocol] += 1
            
            # 统计来源
            if proxy.source not in stats["sources"]:
                stats["sources"][proxy.source] = 0
            stats["sources"][proxy.source] += 1
        
        return stats
    
    def save_results(self) -> None:
        """保存结果"""
        # 保存所有代理到文本文件
        all_proxies_file = f"{self.output_dir}/all_proxies.txt"
        save_text([str(p) for p in self.proxies], all_proxies_file)
        
        # 按协议分类保存
        for protocol in ['http', 'https', 'socks5']:
            protocol_proxies = [p for p in self.proxies if p.protocol == protocol]
            if protocol_proxies:
                filepath = f"{self.output_dir}/{protocol}_proxies.txt"
                save_text([f"{p.ip}:{p.port}" for p in protocol_proxies], filepath)
        
        # 保存JSON报告
        stats = self.get_statistics()
        report = {
            "timestamp": get_timestamp(),
            "summary": stats,
            "proxies": [p.to_dict() for p in self.proxies[:200]]
        }
        save_json(report, f"{self.output_dir}/proxy_report.json")
        
        # 打印统计
        print_stats(stats["protocols"], "协议分布")
        print_stats(stats["sources"], "来源统计")
        
        print(f"\n结果已保存到 {self.output_dir} 目录")
        print(f"  - all_proxies.txt: {stats['unique_proxies']} 个代理")
        print(f"  - http_proxies.txt: HTTP代理")
        print(f"  - https_proxies.txt: HTTPS代理")
        print(f"  - socks5_proxies.txt: SOCKS5代理")
        print(f"  - proxy_report.json: 详细报告")
    
    def run(self) -> None:
        """运行收集器"""
        self.collect_all()
        print()
        print_separator()
        print("收集完成")
        print_separator()
        print(f"总计代理: {len(self.proxies)}")
        self.save_results()