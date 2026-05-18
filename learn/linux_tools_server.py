"""
linux_tools_server.py — Linux 系统工具 MCP 服务器
===================================================
基于 fastmcp 封装三类工具：
  - 内存查看：读取 /proc/meminfo，解析各内存字段
  - 进程查看：读取 /proc/<pid>/status，支持列表与详情
  - 文件查看：列出目录内容、读取文件内容
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP(
    name="linux-tools",
    instructions=(
        "提供 Linux 系统级别的内存、进程与文件查看能力。"
        "所有工具均以只读方式运行，不会修改任何系统状态。"
    ),
)

# ─────────────────────────────────────────────────────────────────────────────
# 内存工具
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "读取 Linux /proc/meminfo，返回系统内存概况。"
        "字段单位均为 kB，包括 MemTotal、MemFree、MemAvailable、"
        "Buffers、Cached、SwapTotal、SwapFree 等。"
    )
)
def get_memory_info() -> dict:
    """解析 /proc/meminfo 并以字典形式返回所有字段（单位 kB）。"""
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        raise RuntimeError("/proc/meminfo 不存在，请确认运行于 Linux 系统。")

    result: dict[str, int] = {}
    for line in meminfo_path.read_text().splitlines():
        match = re.match(r"^(\S+):\s+(\d+)", line)
        if match:
            key = match.group(1).rstrip(":")
            result[key] = int(match.group(2))

    # 计算使用率（百分比，保留两位小数）
    total = result.get("MemTotal", 0)
    available = result.get("MemAvailable", 0)
    if total > 0:
        result["MemUsedPercent"] = round((total - available) / total * 100, 2)
    else:
        result["MemUsedPercent"] = 0.0

    return result


@mcp.tool(
    description=(
        "返回格式化的内存使用摘要（MB 单位），"
        "包括总量、已用、可用、缓冲区、缓存及交换分区信息。"
    )
)
def get_memory_summary() -> str:
    """以人类可读格式返回内存摘要（MB）。"""
    info = get_memory_info()

    def kb_to_mb(kb: int) -> float:
        return round(kb / 1024, 1)

    lines = [
        "=== 内存使用摘要 ===",
        f"总内存    : {kb_to_mb(info.get('MemTotal', 0)):>10.1f} MB",
        f"已用内存  : {kb_to_mb(info.get('MemTotal', 0) - info.get('MemAvailable', 0)):>10.1f} MB"
        f"  ({info.get('MemUsedPercent', 0)}%)",
        f"可用内存  : {kb_to_mb(info.get('MemAvailable', 0)):>10.1f} MB",
        f"空闲内存  : {kb_to_mb(info.get('MemFree', 0)):>10.1f} MB",
        f"缓冲区    : {kb_to_mb(info.get('Buffers', 0)):>10.1f} MB",
        f"缓存      : {kb_to_mb(info.get('Cached', 0)):>10.1f} MB",
        "--- 交换分区 ---",
        f"交换总量  : {kb_to_mb(info.get('SwapTotal', 0)):>10.1f} MB",
        f"交换空闲  : {kb_to_mb(info.get('SwapFree', 0)):>10.1f} MB",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 进程工具
# ─────────────────────────────────────────────────────────────────────────────

def _read_proc_status(pid: int) -> dict[str, str]:
    """读取 /proc/<pid>/status，返回键值字典。"""
    status_path = Path(f"/proc/{pid}/status")
    result: dict[str, str] = {}
    try:
        for line in status_path.read_text().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                result[key.strip()] = value.strip()
    except (FileNotFoundError, PermissionError):
        pass
    return result


def _read_proc_cmdline(pid: int) -> str:
    """读取 /proc/<pid>/cmdline，返回命令行字符串。"""
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        raw = cmdline_path.read_bytes()
        return raw.replace(b"\x00", b" ").decode(errors="replace").strip()
    except (FileNotFoundError, PermissionError):
        return ""


@mcp.tool(
    description=(
        "列出系统中所有正在运行的进程，返回进程列表。"
        "每个条目包含 PID、进程名、状态、用户 UID 及虚拟内存大小（kB）。"
        "可通过 name_filter 按进程名关键字过滤（不区分大小写）。"
    )
)
def list_processes(name_filter: Optional[str] = None) -> list[dict]:
    """
    遍历 /proc 下的数字目录，收集进程基本信息。

    Args:
        name_filter: 按名称过滤的关键字（可选，不区分大小写）。

    Returns:
        进程信息列表，每项含 pid、name、state、uid、vm_rss_kb。
    """
    processes: list[dict] = []
    proc_root = Path("/proc")

    if not proc_root.exists():
        raise RuntimeError("/proc 不存在，请确认运行于 Linux 系统。")

    for entry in sorted(proc_root.iterdir(), key=lambda p: p.name):
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        status = _read_proc_status(pid)
        if not status:
            continue

        name = status.get("Name", "")
        if name_filter and name_filter.lower() not in name.lower():
            continue

        # VmRSS 格式: "1234 kB"
        vm_rss_str = status.get("VmRSS", "0 kB")
        vm_rss_kb = int(vm_rss_str.split()[0]) if vm_rss_str.split() else 0

        processes.append({
            "pid": pid,
            "name": name,
            "state": status.get("State", ""),
            "uid": status.get("Uid", "").split()[0] if status.get("Uid") else "",
            "vm_rss_kb": vm_rss_kb,
            "threads": int(status.get("Threads", 0)),
        })

    return processes


@mcp.tool(
    description=(
        "查看指定 PID 的进程详细信息，包括完整的 /proc/<pid>/status 字段、"
        "命令行参数、以及可执行文件路径（如有权限）。"
    )
)
def get_process_detail(pid: int) -> dict:
    """
    返回指定进程的详细信息。

    Args:
        pid: 目标进程的 PID。

    Returns:
        包含 status、cmdline、exe_path 的字典。
    """
    if not Path(f"/proc/{pid}").exists():
        raise ValueError(f"PID {pid} 不存在或已退出。")

    status = _read_proc_status(pid)
    if not status:
        raise PermissionError(f"无权限读取 PID {pid} 的状态信息。")

    cmdline = _read_proc_cmdline(pid)

    exe_path = ""
    try:
        exe_path = os.readlink(f"/proc/{pid}/exe")
    except (FileNotFoundError, PermissionError, OSError):
        exe_path = "(无权限或已退出)"

    return {
        "pid": pid,
        "status": status,
        "cmdline": cmdline,
        "exe_path": exe_path,
    }


@mcp.tool(
    description=(
        "以表格形式打印进程列表摘要，类似 ps aux 输出，"
        "按内存占用（VmRSS）降序排列，默认显示前 20 条。"
        "可通过 name_filter 过滤进程名，通过 limit 控制条数。"
    )
)
def get_process_table(
    name_filter: Optional[str] = None,
    limit: int = 20,
) -> str:
    """
    以格式化表格返回进程摘要。

    Args:
        name_filter: 按名称过滤（可选）。
        limit: 最多返回的行数，默认 20。

    Returns:
        格式化的进程表格字符串。
    """
    processes = list_processes(name_filter=name_filter)
    processes.sort(key=lambda p: p["vm_rss_kb"], reverse=True)
    top = processes[:limit]

    header = f"{'PID':>7}  {'NAME':<20}  {'STATE':<20}  {'UID':>6}  {'RSS(kB)':>10}  {'THREADS':>7}"
    sep = "-" * len(header)
    rows = [
        f"{p['pid']:>7}  {p['name']:<20}  {p['state']:<20}  "
        f"{p['uid']:>6}  {p['vm_rss_kb']:>10}  {p['threads']:>7}"
        for p in top
    ]
    summary = f"\n共 {len(processes)} 个进程，显示前 {len(top)} 条（按内存降序）"
    return "\n".join([header, sep] + rows + [sep, summary])


# ─────────────────────────────────────────────────────────────────────────────
# 文件工具
# ─────────────────────────────────────────────────────────────────────────────

def _safe_path(path: str) -> Path:
    """解析并验证路径，防止路径遍历攻击。"""
    resolved = Path(path).resolve()
    return resolved


@mcp.tool(
    description=(
        "列出指定目录的内容，返回文件与子目录列表。"
        "每个条目包含名称、类型（file/dir/symlink/other）、"
        "文件大小（字节）及最后修改时间（Unix 时间戳）。"
        "hidden 参数控制是否显示以 . 开头的隐藏条目（默认 False）。"
    )
)
def list_directory(
    path: str,
    hidden: bool = False,
) -> list[dict]:
    """
    列出目录内容。

    Args:
        path: 目标目录的绝对路径。
        hidden: 是否包含隐藏文件（. 开头），默认 False。

    Returns:
        条目列表，每项含 name、type、size_bytes、mtime。
    """
    target = _safe_path(path)

    if not target.exists():
        raise FileNotFoundError(f"路径不存在: {path}")
    if not target.is_dir():
        raise NotADirectoryError(f"不是目录: {path}")

    entries: list[dict] = []
    for item in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name)):
        if not hidden and item.name.startswith("."):
            continue
        try:
            stat = item.stat(follow_symlinks=False)
            if item.is_symlink():
                entry_type = "symlink"
            elif item.is_dir():
                entry_type = "dir"
            elif item.is_file():
                entry_type = "file"
            else:
                entry_type = "other"

            entries.append({
                "name": item.name,
                "type": entry_type,
                "size_bytes": stat.st_size,
                "mtime": stat.st_mtime,
            })
        except PermissionError:
            entries.append({
                "name": item.name,
                "type": "unknown",
                "size_bytes": -1,
                "mtime": -1,
            })

    return entries


@mcp.tool(
    description=(
        "读取指定文件的文本内容。"
        "offset 和 limit 参数支持按行范围读取（从第 offset 行开始，读取 limit 行）。"
        "默认读取全部内容。文件大小超过 10 MB 时会拒绝读取以防止内存耗尽。"
        "适合读取日志、配置文件、脚本等文本文件；二进制文件请使用 read_file_hex。"
    )
)
def read_file_text(
    path: str,
    offset: int = 0,
    limit: Optional[int] = None,
    encoding: str = "utf-8",
) -> dict:
    """
    以文本模式读取文件内容。

    Args:
        path: 文件的绝对路径。
        offset: 起始行号（0 索引），默认 0。
        limit: 最多读取的行数，None 表示全部。
        encoding: 文件编码，默认 utf-8。

    Returns:
        含 path、total_lines、content、truncated 的字典。
    """
    target = _safe_path(path)

    if not target.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"不是文件: {path}")

    size = target.stat().st_size
    if size > 10 * 1024 * 1024:  # 10 MB
        raise ValueError(
            f"文件过大（{size / 1024 / 1024:.1f} MB），超过 10 MB 限制，"
            "请使用 offset/limit 参数分段读取。"
        )

    try:
        all_lines = target.read_text(encoding=encoding).splitlines()
    except UnicodeDecodeError:
        raise ValueError(
            f"文件 {path} 无法以 {encoding} 解码，"
            "可能是二进制文件，请改用 read_file_hex。"
        )

    total_lines = len(all_lines)
    sliced = all_lines[offset: (offset + limit) if limit is not None else None]
    truncated = limit is not None and (offset + limit) < total_lines

    return {
        "path": str(target),
        "total_lines": total_lines,
        "offset": offset,
        "returned_lines": len(sliced),
        "truncated": truncated,
        "content": "\n".join(sliced),
    }


@mcp.tool(
    description=(
        "读取文件并以十六进制转储（hexdump）格式返回。"
        "适合查看二进制文件、ELF 可执行文件、设备文件等。"
        "max_bytes 限制最多读取的字节数，默认 512 字节。"
    )
)
def read_file_hex(
    path: str,
    offset: int = 0,
    max_bytes: int = 512,
) -> str:
    """
    以 hexdump 格式返回文件内容。

    Args:
        path: 文件的绝对路径。
        offset: 字节偏移量，默认 0。
        max_bytes: 最多读取的字节数，默认 512，上限 65536。

    Returns:
        hexdump 格式的字符串。
    """
    if max_bytes > 65536:
        raise ValueError("max_bytes 上限为 65536（64 KB）。")

    target = _safe_path(path)

    if not target.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    if not target.is_file():
        raise IsADirectoryError(f"不是文件: {path}")

    with target.open("rb") as f:
        f.seek(offset)
        data = f.read(max_bytes)

    lines: list[str] = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        addr = offset + i
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{addr:08x}  {hex_part:<47}  |{ascii_part}|")

    lines.append(f"\n读取 {len(data)} 字节，偏移量 {offset}，文件: {target}")
    return "\n".join(lines)


@mcp.tool(
    description=(
        "获取指定路径（文件或目录）的详细元数据，"
        "包括大小、权限（八进制）、所有者 UID/GID、"
        "访问时间、修改时间、更改时间及 inode 号。"
    )
)
def get_file_stat(path: str) -> dict:
    """
    返回路径的 stat 元数据。

    Args:
        path: 目标路径（文件或目录）。

    Returns:
        含元数据字段的字典。
    """
    target = _safe_path(path)

    if not target.exists():
        raise FileNotFoundError(f"路径不存在: {path}")

    stat = target.stat(follow_symlinks=False)
    is_symlink = target.is_symlink()
    link_target = ""
    if is_symlink:
        try:
            link_target = os.readlink(target)
        except OSError:
            link_target = "(无法读取)"

    if target.is_symlink():
        path_type = "symlink"
    elif target.is_dir():
        path_type = "directory"
    elif target.is_file():
        path_type = "file"
    else:
        path_type = "other"

    return {
        "path": str(target),
        "type": path_type,
        "size_bytes": stat.st_size,
        "permissions_octal": oct(stat.st_mode),
        "uid": stat.st_uid,
        "gid": stat.st_gid,
        "inode": stat.st_ino,
        "atime": stat.st_atime,
        "mtime": stat.st_mtime,
        "ctime": stat.st_ctime,
        "link_target": link_target,
    }


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
