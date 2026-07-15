"""
代理数据模型
"""

from dataclasses import dataclass, asdict
from typing import Optional
import re

@dataclass
class Proxy:
    """代理数据类"""
    ip: str
    port: int
    protocol: str  # http, https, socks5, socks4
    country: str = ""
    source: str = ""
    response_time: float = 0.0
    last_checked: str = ""
    is_valid: bool = False
    
    def __str__(self):
        return f"{self.protocol}://{self.ip}:{self.port}"
    
    def __eq__(self, other):
        if isinstance(other, Proxy):
            return self.ip == other.ip and self.port == other.port
        return False
    
    def __hash__(self):
        return hash((self.ip, self.port))
    
    @property
    def address(self) -> str:
        return f"{self.protocol}://{self.ip}:{self.port}"
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_line(cls, line: str, protocol: str, source: str = "") -> Optional['Proxy']:
        """从文本行解析代理"""
        line = line.strip()
        if not line or line.startswith('#'):
            return None
        
        # 尝试匹配 ip:port 格式
        match = re.match(r'^(\d+\.\d+\.\d+\.\d+):(\d+)$', line)
        if match:
            ip = match.group(1)
            port = int(match.group(2))
            
            # 验证IP地址格式
            if all(0 <= int(octet) <= 255 for octet in ip.split('.')):
                # 验证端口范围
                if 1 <= port <= 65535:
                    return cls(ip=ip, port=port, protocol=protocol, source=source)
        
        return None