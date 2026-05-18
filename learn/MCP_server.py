from typing import Any
import httpx
from fastmcp import FastMCP
import subprocess
import logging
# Initialize FastMCP server
mcp = FastMCP("MTR")

@mcp.tool()
def ping(ip:str) -> str:
    """
    一个ping命令，可以检查 ip 的可达性。
    :param ip:
    :return:
    """
    logging.info("开始执行ping命令")
    args = ["ping", "-n", "4", ip]
    try:
        result = subprocess.run(
            args,
            capture_output=True,  # 捕获 stdout 和 stderr
            text=True,  # 以文本形式返回（默认为 bytes）
            timeout=10)

        return result.stdout
    except Exception as e:
        return f"ping时发生错误"

@mcp.tool()
def traceRoute(ip:str) -> str:
    """
    一个traceroute命令，可以追踪宿主机到 目标地址 之间的路由路径。
    :param ip: 可以为网址或ip地址
    :return:
    """
    logging.info("开始执行tracert命令")
    args = ["tracert", ip]
    try:
        result = subprocess.run(
            args,
            capture_output=True,  # 捕获 stdout 和 stderr
            text=True,  # 以文本形式返回（默认为 bytes）
            timeout=50)

        return result.stdout
    except Exception as e:
        return "traceroute时，发生错误"

if __name__ == "__main__":
    mcp.run(transport="stdio")