"""
通用工具函数
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any

def ensure_dir(directory: str) -> None:
    """确保目录存在"""
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_timestamp() -> str:
    """获取当前时间戳"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def save_json(data: Any, filepath: str, indent: int = 2) -> None:
    """保存JSON文件"""
    ensure_dir(os.path.dirname(filepath))
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)

def load_json(filepath: str) -> Any:
    """加载JSON文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_text(lines: List[str], filepath: str) -> None:
    """保存文本文件"""
    ensure_dir(os.path.dirname(filepath))
    with open(filepath, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(f"{line}\n")

def load_text(filepath: str) -> List[str]:
    """加载文本文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def format_number(num: int) -> str:
    """格式化数字"""
    return f"{num:,}"

def print_separator(char: str = "=", length: int = 60) -> None:
    """打印分隔符"""
    print(char * length)

def print_header(title: str) -> None:
    """打印标题"""
    print_separator()
    print(title)
    print_separator()

def print_stats(stats: Dict[str, int], title: str = "统计") -> None:
    """打印统计信息"""
    print(f"\n{title}:")
    for key, value in stats.items():
        print(f"  {key}: {format_number(value)}")