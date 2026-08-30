# -*- coding: utf-8 -*-
"""启动脚本辅助：在 127.0.0.1 上找一个空闲端口（优先 8000），打印端口号供 .bat 读取。

被启动.bat / scripts/启动.bat 调用：for /f 读取 stdout 第一行作为服务端口。
找不到空闲端口时退出码为 1，信息写 stderr。
"""
import socket
import sys

# 扫描范围：优先 8000（保持默认入口不变），被占时顺移
PORT_START = 8000
PORT_END = 8020  # 不含

for port in range(PORT_START, PORT_END):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        continue
    sock.close()
    print(port)
    sys.exit(0)

print(f"no free port in {PORT_START}-{PORT_END - 1} on 127.0.0.1", file=sys.stderr)
sys.exit(1)
