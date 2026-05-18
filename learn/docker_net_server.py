"""
Docker Network MCP Server
Provides ping, vtysh routing table query, and tcpdump/Wireshark capture tools
for a multi-node Docker network with FRR installed.
All tools require specifying a source Docker node (container name or ID).
"""

import asyncio
import os
import re
import shutil
import tempfile
from typing import Optional

from fastmcp import FastMCP

mcp = FastMCP(
    name="docker-net-tools",
    instructions=(
        "Network diagnostic tools for a Docker-based FRR network. "
        "All tools operate from a specified Docker node (container). "
        "Available tools: list_nodes, ping, vtysh_query, tcpdump_capture, stop_capture."
    ),
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _require(cmd: str) -> str:
    """Return full path of a host command or raise a clear error."""
    path = shutil.which(cmd)
    if path is None:
        raise RuntimeError(f"'{cmd}' not found on host. Is Docker installed?")
    return path


async def _run(
    args: list[str], timeout: int
) -> tuple[int, str, str]:
    """Run a subprocess; return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"Command timed out after {timeout}s: {' '.join(args)}")
    return proc.returncode, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def _docker_exec(
    node: str, cmd_args: list[str], timeout: int
) -> tuple[int, str, str]:
    """Run a command inside a Docker container."""
    docker = _require("docker")
    return await _run([docker, "exec", node] + cmd_args, timeout)


def _parse_ping_summary(output: str) -> dict:
    summary: dict = {}
    loss = re.search(r"(\d+(?:\.\d+)?)% packet loss", output)
    if loss:
        summary["packet_loss_pct"] = float(loss.group(1))
    rtt = re.search(
        r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms", output
    )
    if rtt:
        summary["rtt_min_ms"] = float(rtt.group(1))
        summary["rtt_avg_ms"] = float(rtt.group(2))
        summary["rtt_max_ms"] = float(rtt.group(3))
        summary["rtt_mdev_ms"] = float(rtt.group(4))
    tx = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", output)
    if tx:
        summary["packets_transmitted"] = int(tx.group(1))
        summary["packets_received"] = int(tx.group(2))
    return summary


# ─── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool
async def list_nodes() -> dict:
    """
    List all running Docker containers that can be used as source nodes.
    Returns container names, IDs, status, and image for easy reference.
    """
    docker = _require("docker")
    rc, stdout, stderr = await _run(
        [
            docker, "ps",
            "--format",
            "{{.Names}}\t{{.ID}}\t{{.Status}}\t{{.Image}}",
        ],
        timeout=15,
    )
    nodes = []
    for line in stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            nodes.append(
                {
                    "name": parts[0],
                    "id": parts[1],
                    "status": parts[2],
                    "image": parts[3],
                }
            )
    return {
        "nodes": nodes,
        "count": len(nodes),
        "raw": stdout,
        "stderr": stderr or None,
    }


@mcp.tool
async def ping(
    node: str,
    target: str,
    count: int = 4,
    interval: float = 1.0,
    timeout_per_packet: int = 2,
    packet_size: int = 56,
    ttl: Optional[int] = None,
    ipv6: bool = False,
) -> dict:
    """
    Send ICMP echo requests from a Docker node to a target host.

    Args:
        node: Source Docker container name or ID (e.g. 'router1').
        target: Destination hostname or IP address.
        count: Number of echo requests (1–100). Default 4.
        interval: Seconds between requests (0.2–60). Default 1.0.
        timeout_per_packet: Per-packet reply timeout in seconds (1–30). Default 2.
        packet_size: Payload bytes (8–65507). Default 56.
        ttl: IP Time-To-Live (1–255). Omit for OS default.
        ipv6: Use ping6 instead of ping.
    """
    count = max(1, min(count, 100))
    interval = max(0.2, min(interval, 60.0))
    timeout_per_packet = max(1, min(timeout_per_packet, 30))
    packet_size = max(8, min(packet_size, 65507))

    cmd = "ping6" if ipv6 else "ping"
    args = [
        cmd,
        "-c", str(count),
        "-i", str(interval),
        "-W", str(timeout_per_packet),
        "-s", str(packet_size),
    ]
    if ttl is not None:
        args += ["-t", str(max(1, min(ttl, 255)))]
    args.append(target)

    total_timeout = int(count * (interval + timeout_per_packet) + 15)
    rc, stdout, stderr = await _docker_exec(node, args, total_timeout)

    return {
        "node": node,
        "target": target,
        "command": f"docker exec {node} {' '.join(args)}",
        "returncode": rc,
        "success": rc == 0,
        "output": stdout,
        "stderr": stderr or None,
        "summary": _parse_ping_summary(stdout),
    }


@mcp.tool
async def vtysh_query(
    node: str,
    command: str,
    extra_commands: Optional[list[str]] = None,
) -> dict:
    """
    Run one or more vtysh commands on a Docker node running FRR to query
    routing information (routing tables, BGP neighbors, OSPF state, etc.).

    Common commands:
      - "show ip route"           — IPv4 routing table
      - "show ipv6 route"         — IPv6 routing table
      - "show ip bgp summary"     — BGP peer summary
      - "show ip ospf neighbor"   — OSPF neighbors
      - "show mpls table"         — MPLS forwarding table
      - "show running-config"     — active FRR configuration

    Args:
        node: Source Docker container name or ID (e.g. 'router1').
        command: Primary vtysh command to execute.
        extra_commands: Additional vtysh commands to run in the same session.
    """
    args = ["vtysh", "-c", command]
    if extra_commands:
        for c in extra_commands:
            args += ["-c", c]

    rc, stdout, stderr = await _docker_exec(node, args, timeout=30)

    # vtysh sometimes writes informational lines to stderr; treat them as output
    combined_output = stdout
    if stderr and not stdout:
        combined_output = stderr

    return {
        "node": node,
        "command": command,
        "extra_commands": extra_commands or [],
        "full_command": f"docker exec {node} {' '.join(args)}",
        "returncode": rc,
        "success": rc == 0,
        "output": combined_output,
        "stderr": stderr or None,
    }


# In-memory store for background capture processes: capture_id -> (process, pcap_path)
_captures: dict[str, tuple[asyncio.subprocess.Process, str]] = {}


@mcp.tool
async def tcpdump_capture(
    node: str,
    interface: str = "eth0",
    duration: int = 10,
    capture_filter: str = "",
    output_path: Optional[str] = None,
    packet_count: Optional[int] = None,
    snaplen: int = 65535,
) -> dict:
    """
    Capture packets on a Docker node using tcpdump and save a .pcap file that
    can be opened with Wireshark.  Runs for 'duration' seconds (or until
    'packet_count' packets are captured), then stops automatically.

    Args:
        node: Source Docker container name or ID (e.g. 'router1').
        interface: Network interface inside the container (default 'eth0').
                   Use 'any' to capture on all interfaces.
        duration: Capture duration in seconds (1–300). Default 10.
        capture_filter: BPF filter expression, e.g. 'tcp port 80' or
                        'host 10.0.0.1'. Empty string captures everything.
        output_path: Host path for the .pcap file.
                     Defaults to a temp file printed in the result.
        packet_count: Stop after this many packets instead of using duration.
        snaplen: Bytes to capture per packet (64–65535). Default 65535.
    """
    duration = max(1, min(duration, 300))
    snaplen = max(64, min(snaplen, 65535))

    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            prefix=f"capture_{node}_", suffix=".pcap"
        )
        os.close(fd)

    # tcpdump writes inside the container; we pipe stdout to the host file.
    # Use -U (per-packet flush) so the file is usable even if interrupted.
    inner_args = [
        "tcpdump",
        "-i", interface,
        "-s", str(snaplen),
        "-U",       # per-packet flush
        "-w", "-",  # write raw pcap to stdout
    ]
    if packet_count is not None:
        inner_args += ["-c", str(packet_count)]
    if capture_filter:
        inner_args.append(capture_filter)

    docker = _require("docker")
    full_args = [docker, "exec", node] + inner_args

    # Open the output file and wire docker stdout → file
    with open(output_path, "wb") as pcap_file:
        proc = await asyncio.create_subprocess_exec(
            *full_args,
            stdout=pcap_file,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=duration + 15
            )
        except asyncio.TimeoutError:
            proc.kill()
            _, stderr = await proc.communicate()
            stderr = b"(capture timed out and was killed)"

    stderr_text = stderr.decode(errors="replace") if stderr else ""

    # tcpdump summary is on stderr, e.g. "5 packets captured"
    captured = None
    m = re.search(r"(\d+) packets captured", stderr_text)
    if m:
        captured = int(m.group(1))

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

    return {
        "node": node,
        "interface": interface,
        "filter": capture_filter or "(none)",
        "pcap_file": output_path,
        "file_size_bytes": file_size,
        "packets_captured": captured,
        "command": f"docker exec {node} {' '.join(inner_args)} > {output_path}",
        "tcpdump_output": stderr_text or None,
        "hint": f"Open '{output_path}' with Wireshark to inspect the capture.",
    }


@mcp.tool
async def tcpdump_capture_background(
    node: str,
    capture_id: str,
    interface: str = "eth0",
    capture_filter: str = "",
    output_path: Optional[str] = None,
    snaplen: int = 65535,
) -> dict:
    """
    Start a background packet capture on a Docker node.  Use stop_capture()
    to end it and retrieve the .pcap file path.

    This is useful for captures spanning longer operations (e.g. start before
    a routing protocol converges, then stop after convergence).

    Args:
        node: Source Docker container name or ID.
        capture_id: A unique label for this capture session (used with stop_capture).
        interface: Interface inside the container (default 'eth0', or 'any').
        capture_filter: BPF filter string (empty = capture all).
        output_path: Host path for the .pcap file (auto-generated if omitted).
        snaplen: Bytes per packet (64–65535). Default 65535.
    """
    if capture_id in _captures:
        raise ValueError(
            f"Capture '{capture_id}' is already running. "
            "Call stop_capture() first or use a different capture_id."
        )

    snaplen = max(64, min(snaplen, 65535))

    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            prefix=f"capture_{node}_{capture_id}_", suffix=".pcap"
        )
        os.close(fd)

    inner_args = [
        "tcpdump",
        "-i", interface,
        "-s", str(snaplen),
        "-U",
        "-w", "-",
    ]
    if capture_filter:
        inner_args.append(capture_filter)

    docker = _require("docker")
    full_args = [docker, "exec", node] + inner_args

    pcap_file = open(output_path, "wb")  # stays open until stop_capture()
    proc = await asyncio.create_subprocess_exec(
        *full_args,
        stdout=pcap_file,
        stderr=asyncio.subprocess.PIPE,
    )
    # Store file handle inside tuple wrapped in a list so we can close it later
    _captures[capture_id] = (proc, output_path, pcap_file)  # type: ignore[assignment]

    return {
        "capture_id": capture_id,
        "node": node,
        "interface": interface,
        "filter": capture_filter or "(none)",
        "pcap_file": output_path,
        "status": "running",
        "hint": f"Call stop_capture(capture_id='{capture_id}') to end the capture.",
    }


@mcp.tool
async def stop_capture(capture_id: str) -> dict:
    """
    Stop a background packet capture started with tcpdump_capture_background()
    and return the path to the saved .pcap file.

    Args:
        capture_id: The label used when starting the capture.
    """
    if capture_id not in _captures:
        known = list(_captures.keys())
        raise ValueError(
            f"No running capture with id '{capture_id}'. "
            f"Active captures: {known}"
        )

    proc, output_path, pcap_file = _captures.pop(capture_id)  # type: ignore[misc]

    proc.terminate()
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
    except asyncio.TimeoutError:
        proc.kill()
        _, stderr = await proc.communicate()
        stderr = b"(process killed)"

    pcap_file.close()

    stderr_text = stderr.decode(errors="replace") if stderr else ""
    captured = None
    m = re.search(r"(\d+) packets captured", stderr_text)
    if m:
        captured = int(m.group(1))

    file_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0

    return {
        "capture_id": capture_id,
        "pcap_file": output_path,
        "file_size_bytes": file_size,
        "packets_captured": captured,
        "tcpdump_output": stderr_text or None,
        "status": "stopped",
        "hint": f"Open '{output_path}' with Wireshark to inspect the capture.",
    }


if __name__ == "__main__":
    mcp.run()
