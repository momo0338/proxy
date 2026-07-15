#!/usr/bin/env python3
"""
代理收集器 - 主入口
从多个GitHub免费代理列表项目收集代理，验证可用性并整理
"""

import sys
import argparse
from src.collector import ProxyCollector
from src.validator import ProxyValidator
from src.config import DEFAULT_CONFIG
from src.utils import print_header, print_separator

def main():
    parser = argparse.ArgumentParser(description='代理收集器 - 从GitHub收集免费代理')
    parser.add_argument('command', choices=['collect', 'validate', 'all'], 
                       help='执行命令: collect(收集), validate(验证), all(全部)')
    parser.add_argument('--output', '-o', 
                       help='输出目录')
    parser.add_argument('--config', '-c',
                       help='配置文件路径')
    parser.add_argument('--proxy-file', '-f',
                       help='代理文件路径 (验证时使用)')
    parser.add_argument('--max-verify', '-m', type=int,
                       help='最大验证数量')
    
    args = parser.parse_args()
    
    print_header("代理收集器")
    print(f"命令: {args.command}")
    if args.config:
        print(f"配置文件: {args.config}")
    print()
    
    if args.command == 'collect':
        # 只收集代理
        collector = ProxyCollector(output_dir=args.output, config_file=args.config)
        collector.run()
        
    elif args.command == 'validate':
        # 只验证代理
        validator = ProxyValidator(output_dir=args.output)
        if args.proxy_file:
            validator.run(proxy_file=args.proxy_file, max_verify=args.max_verify)
        else:
            validator.run(max_verify=args.max_verify)
            
    elif args.command == 'all':
        # 收集并验证
        print("第一步: 收集代理...")
        collector = ProxyCollector(output_dir=args.output, config_file=args.config)
        collector.collect_all()
        collector.save_results()
        
        print()
        print("第二步: 验证代理...")
        validator = ProxyValidator(output_dir=args.output)
        validator.run()
    
    print()
    print_separator()
    print("完成!")
    print_separator()

if __name__ == "__main__":
    main()