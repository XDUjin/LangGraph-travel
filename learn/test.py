from typing import Any
import httpx
from fastmcp import FastMCP
import sys
import subprocess
import logging
# Initialize FastMCP server

def capture_packets(interface, output_file, packet_count=100, filter_expr=None):
    """
    使用 tshark 抓包并保存为 pcap 文件。

    :param interface: 网卡名称（例如 'eth0', 'Wi-Fi'）
    :param output_file: 输出 pcap 文件的路径
    :param packet_count: 要捕获的数据包数量（None 表示无限捕获，需手动终止）
    :param filter_expr: 捕获过滤器表达式（例如 'tcp port 80'）
    """
    # 构建 tshark 命令
    cmd = ['tshark', '-i', interface, '-w', output_file]
    if packet_count:
        cmd.extend(['-c', str(packet_count)])
    if filter_expr:
        cmd.extend(['-f', filter_expr])

    print(f"执行命令: {' '.join(cmd)}")
    try:
        # 启动 tshark 进程
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,encoding='utf-8' )
        print("正在抓包...")

        # 等待抓包完成（如果指定了 -c，tshark 会在捕获足够包后自动退出）
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            print(f"抓包失败，错误信息:\n{stderr}")
        else:
            print(f"抓包成功，已保存到 {output_file}")

    except FileNotFoundError:
        print("未找到 tshark，请确保已安装 Wireshark 并将 tshark 添加到系统 PATH 中。")
        sys.exit(1)
    except Exception as e:
        print(f"发生异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    capture_packets('8','test.pcap')