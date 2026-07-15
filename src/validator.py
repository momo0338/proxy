"""
代理验证器
"""

import requests
import time
import concurrent.futures
from typing import List, Dict, Optional
from datetime import datetime

from .config import DEFAULT_CONFIG
from .proxy import Proxy
from .utils import (
    ensure_dir,
    get_timestamp,
    save_json,
    save_text,
    load_text,
    print_separator,
    print_header,
    format_number
)

class ProxyValidator:
    """代理验证器"""
    
    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or DEFAULT_CONFIG["output_dir"]
        self.valid_proxies: List[Dict] = []
        
        ensure_dir(self.output_dir)
    
    def validate_proxy(self, proxy: str, timeout: float = None) -> Dict:
        """验证单个代理"""
        timeout = timeout or DEFAULT_CONFIG["verify_timeout"]
        
        result = {
            "address": proxy,
            "is_valid": False,
            "response_time": 0,
            "origin_ip": None,
            "error": None
        }
        
        try:
            # 解析代理地址
            if "://" not in proxy:
                proxy = f"http://{proxy}"
            
            proxies = {
                "http": proxy,
                "https": proxy
            }
            
            start_time = time.time()
            response = requests.get(
                "http://httpbin.org/ip",
                proxies=proxies,
                timeout=timeout,
                headers={"User-Agent": DEFAULT_CONFIG["user_agent"]}
            )
            
            result["response_time"] = round(time.time() - start_time, 3)
            result["is_valid"] = response.status_code == 200
            result["origin_ip"] = response.json().get("origin", "")
            
        except requests.exceptions.Timeout:
            result["error"] = "连接超时"
        except requests.exceptions.ConnectionError:
            result["error"] = "连接失败"
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def validate_batch(self, proxies: List[str], max_workers: int = None) -> List[Dict]:
        """批量验证代理"""
        max_workers = max_workers or DEFAULT_CONFIG["max_workers"]
        
        print_header("代理验证器")
        print(f"待验证代理数: {len(proxies)}")
        print(f"并发数: {max_workers}")
        print()
        
        valid_proxies = []
        invalid_count = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_proxy = {
                executor.submit(self.validate_proxy, proxy): proxy 
                for proxy in proxies
            }
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_proxy):
                completed += 1
                proxy_addr = future_to_proxy[future]
                
                try:
                    result = future.result()
                    if result["is_valid"]:
                        valid_proxies.append(result)
                        print(f"  ✓ {proxy_addr} ({result['response_time']}s)")
                    else:
                        invalid_count += 1
                except Exception as e:
                    invalid_count += 1
                
                # 进度显示
                if completed % 20 == 0:
                    print(f"  进度: {completed}/{len(proxies)}")
        
        print()
        print_separator()
        print("验证完成")
        print_separator()
        print(f"有效代理: {len(valid_proxies)}")
        print(f"无效代理: {invalid_count}")
        
        # 按响应时间排序
        valid_proxies.sort(key=lambda x: x["response_time"])
        
        self.valid_proxies = valid_proxies
        return valid_proxies
    
    def load_proxies_from_file(self, filepath: str) -> List[str]:
        """从文件加载代理列表"""
        try:
            proxies = load_text(filepath)
            print(f"从 {filepath} 加载了 {len(proxies)} 个代理")
            return proxies
        except FileNotFoundError:
            print(f"文件不存在: {filepath}")
            return []
    
    def save_results(self) -> None:
        """保存验证结果"""
        if not self.valid_proxies:
            print("没有有效代理可保存")
            return
        
        # 保存有效代理
        valid_proxies_file = f"{self.output_dir}/verified_proxies.txt"
        save_text([p["address"] for p in self.valid_proxies], valid_proxies_file)
        
        # 保存详细报告
        report = {
            "timestamp": get_timestamp(),
            "total_tested": len(self.valid_proxies),
            "valid_count": len(self.valid_proxies),
            "proxies": self.valid_proxies
        }
        save_json(report, f"{self.output_dir}/verified_report.json")
        
        print(f"\n验证结果已保存到 {self.output_dir} 目录")
        print(f"  - verified_proxies.txt: {len(self.valid_proxies)} 个有效代理")
        print(f"  - verified_report.json: 详细报告")
    
    def run(self, proxy_file: str = None, max_verify: int = None) -> None:
        """运行验证器"""
        # 加载代理列表
        if proxy_file:
            proxies = self.load_proxies_from_file(proxy_file)
        else:
            proxies = self.load_proxies_from_file(f"{self.output_dir}/all_proxies.txt")
        
        if not proxies:
            print("没有找到代理文件")
            return
        
        # 限制验证数量
        if max_verify is None:
            max_verify = DEFAULT_CONFIG["max_verify"]
        
        if max_verify > 0 and len(proxies) > max_verify:
            print(f"代理数量过多，只验证前 {max_verify} 个")
            proxies = proxies[:max_verify]
        elif max_verify == 0:
            print(f"验证所有代理: {len(proxies)} 个")
        
        # 验证代理
        self.validate_batch(proxies)
        
        # 保存结果
        self.save_results()
        
        # 显示最快的10个代理
        if self.valid_proxies:
            print()
            print("最快的10个代理:")
            for i, proxy in enumerate(self.valid_proxies[:10]):
                print(f"  {i+1}. {proxy['address']} ({proxy['response_time']}s)")