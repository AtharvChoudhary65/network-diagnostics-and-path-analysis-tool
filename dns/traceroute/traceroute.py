"""
Traceroute module for the Network Diagnostics and Path Analysis Tool.

Owner: Member 3 (Traceroute)

This module runs the operating system's traceroute utility
(``tracert`` on Windows, ``traceroute`` on Linux/macOS), parses the output
into structured hop data, and formats that data for display.

Public API
----------
run_traceroute(target, max_hops=30, timeout=2, queries=3) -> TracerouteResult
    Run a traceroute and return structured results. Never raises for
    runtime/network problems; failures are reported via ``result.success``
    and ``result.error``.

format_result(result) -> str
    Return a printable hop table.

parse_traceroute_output(output) -> list[Hop]
    Parse raw traceroute/tracert text (exposed for testing and reuse).

``TracerouteResult.hops`` (or ``TracerouteResult.to_dict()["hops"]``) is the
input expected by the ``path_analysis`` module.

Standalone usage
----------------
    python -m traceroute example.com
    python -m traceroute 8.8.8.8 --max-hops 15 --json
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

DEFAULT_MAX_HOPS = 30
DEFAULT_TIMEOUT_SECONDS = 2.0  # per-probe wait time
DEFAULT_QUERIES = 3  # probes per hop (fixed at 3 on Windows)

MAX_ALLOWED_HOPS = 64
MAX_ALLOWED_QUERIES = 10
MAX_TARGET_LENGTH = 253  # maximum length of a DNS name

# Windows reports very fast replies as "<1 ms". We record them as 1.0 ms,
# i.e. the upper bound of what the tool tells us.
LESS_THAN_ONE_MS_VALUE = 1.0

# Extra seconds allowed on top of the worst-case probe time before the
# subprocess is forcibly stopped.
SUBPROCESS_GRACE_SECONDS = 10

# --------------------------------------------------------------------------- #
# Regular expressions used for parsing
# --------------------------------------------------------------------------- #

# A hop line starts with the hop number, e.g. " 3  10.0.0.1  5.1 ms ..."
_HOP_LINE_RE = re.compile(r"^\s*(\d+)\s+(.*)$")

# Tokens of interest inside a hop line, in priority order:
#   *            -> probe timed out
#   12.3 ms      -> RTT (also "<1 ms" on Windows)
#   IPv4 / IPv6  -> responding router address
_TOKEN_RE = re.compile(
    r"(?P<star>\*)"
    r"|(?P<rtt><?\d+(?:\.\d+)?)\s*ms\b"
    r"|(?P<ipv4>\b(?:\d{1,3}\.){3}\d{1,3}\b)"
    r"|(?P<ipv6>(?<![\w:])[0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7}(?![\w:]))"
)

# Destination IP in the header line:
#   Linux/macOS: "traceroute to example.com (93.184.216.34), 30 hops max"
#   Windows:     "Tracing route to example.com [93.184.216.34]"
_HEADER_DEST_RE = re.compile(
    r"(?:traceroute(?:6)? to|Tracing route to)\s+\S+\s+[\[(]([0-9a-fA-F.:]+)[\])]",
    re.IGNORECASE,
)

# Allowed characters for a hostname or IP address.
_TARGET_RE = re.compile(r"^[A-Za-z0-9.:\-]+$")


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass
class Hop:
    """A single hop (router) along the network path.

    Attributes:
        hop_number: TTL value of this hop (1 = first router).
        addresses:  IP addresses that answered for this hop. Usually one;
                    more than one when load-balanced paths are seen.
        rtts_ms:    RTT of each probe in milliseconds; ``None`` for a probe
                    that timed out (shown as ``*`` by traceroute).
    """

    hop_number: int
    addresses: List[str] = field(default_factory=list)
    rtts_ms: List[Optional[float]] = field(default_factory=list)

    @property
    def ip_address(self) -> Optional[str]:
        """Primary IP address of the hop, or ``None`` if it did not respond."""
        return self.addresses[0] if self.addresses else None

    @property
    def responded(self) -> bool:
        """True if at least one probe received a reply from this hop."""
        return bool(self.addresses) and any(r is not None for r in self.rtts_ms)

    @property
    def _valid_rtts(self) -> List[float]:
        return [r for r in self.rtts_ms if r is not None]

    @property
    def avg_rtt_ms(self) -> Optional[float]:
        rtts = self._valid_rtts
        return round(mean(rtts), 3) if rtts else None

    @property
    def min_rtt_ms(self) -> Optional[float]:
        rtts = self._valid_rtts
        return min(rtts) if rtts else None

    @property
    def max_rtt_ms(self) -> Optional[float]:
        rtts = self._valid_rtts
        return max(rtts) if rtts else None

    def to_dict(self) -> Dict[str, Any]:
        """Plain-dict form (JSON-serialisable) used by other modules."""
        return {
            "hop": self.hop_number,
            "ip": self.ip_address,
            "addresses": list(self.addresses),
            "rtts_ms": list(self.rtts_ms),
            "avg_rtt_ms": self.avg_rtt_ms,
            "min_rtt_ms": self.min_rtt_ms,
            "max_rtt_ms": self.max_rtt_ms,
            "responded": self.responded,
        }


@dataclass
class TracerouteResult:
    """Outcome of a traceroute run.

    Attributes:
        target:              Hostname/IP that was traced.
        success:             True if at least one hop was parsed.
        hops:                Ordered list of hops.
        destination_ip:      Destination IP reported by the tool (if known).
        reached_destination: True if the destination itself replied.
        error:               Human-readable error message, if any.
        command:             The exact command that was executed.
        raw_output:          Unmodified tool output (useful for debugging).
    """

    target: str
    success: bool
    hops: List[Hop] = field(default_factory=list)
    destination_ip: Optional[str] = None
    reached_destination: bool = False
    error: Optional[str] = None
    command: List[str] = field(default_factory=list)
    raw_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Plain-dict form (JSON-serialisable). Excludes raw output."""
        return {
            "target": self.target,
            "success": self.success,
            "destination_ip": self.destination_ip,
            "reached_destination": self.reached_destination,
            "error": self.error,
            "command": list(self.command),
            "hops": [hop.to_dict() for hop in self.hops],
        }


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


def validate_target(target: str) -> str:
    """Validate and normalise a hostname or IP address.

    The target is passed to an external program, so it is checked strictly
    to prevent option injection (e.g. a target starting with ``-``).

    Returns:
        The stripped target string.

    Raises:
        ValueError: If the target is empty or contains invalid characters.
    """
    if not isinstance(target, str):
        raise ValueError("Target must be a string.")

    target = target.strip()
    if not target:
        raise ValueError("Target must not be empty.")
    if len(target) > MAX_TARGET_LENGTH:
        raise ValueError(f"Target is longer than {MAX_TARGET_LENGTH} characters.")
    if target.startswith("-"):
        raise ValueError("Target must not start with '-'.")
    if not _TARGET_RE.match(target):
        raise ValueError(
            "Target may only contain letters, digits, '.', ':' and '-'."
        )
    return target


def _validate_options(max_hops: int, timeout: float, queries: int) -> None:
    """Raise ValueError for out-of-range numeric options."""
    if not isinstance(max_hops, int) or not 1 <= max_hops <= MAX_ALLOWED_HOPS:
        raise ValueError(f"max_hops must be an integer between 1 and {MAX_ALLOWED_HOPS}.")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be a positive number of seconds.")
    if not isinstance(queries, int) or not 1 <= queries <= MAX_ALLOWED_QUERIES:
        raise ValueError(f"queries must be an integer between 1 and {MAX_ALLOWED_QUERIES}.")


# --------------------------------------------------------------------------- #
# Command construction (handles OS differences)
# --------------------------------------------------------------------------- #


def _is_windows(system_name: Optional[str] = None) -> bool:
    return (system_name or platform.system()).lower().startswith("win")


def build_command(
    target: str,
    max_hops: int = DEFAULT_MAX_HOPS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    queries: int = DEFAULT_QUERIES,
    system_name: Optional[str] = None,
) -> List[str]:
    """Build the traceroute command for the current (or given) OS.

    Name resolution of each hop is disabled (``-d`` / ``-n``) so the trace is
    faster and the output contains plain IP addresses.

    Args:
        target:      Validated hostname or IP address.
        max_hops:    Maximum TTL to probe.
        timeout:     Seconds to wait for each probe.
        queries:     Probes per hop (ignored on Windows, which always sends 3).
        system_name: Override for ``platform.system()`` (used in tests).

    Returns:
        Argument list suitable for ``subprocess.run`` (no shell involved).
    """
    if _is_windows(system_name):
        timeout_ms = max(1, int(timeout * 1000))
        return ["tracert", "-d", "-h", str(max_hops), "-w", str(timeout_ms), target]

    # Linux and macOS share the same core options.
    timeout_str = str(int(timeout)) if float(timeout).is_integer() else str(timeout)
    return [
        "traceroute",
        "-n",
        "-m", str(max_hops),
        "-q", str(queries),
        "-w", timeout_str,
        target,
    ]


# --------------------------------------------------------------------------- #
# Output parsing
# --------------------------------------------------------------------------- #


def _parse_rtt(token: str) -> float:
    """Convert an RTT token such as '12.4' or '<1' into milliseconds."""
    if token.startswith("<"):
        return LESS_THAN_ONE_MS_VALUE
    return float(token)


def _is_valid_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def parse_traceroute_output(output: str) -> List[Hop]:
    """Parse traceroute (Linux/macOS) or tracert (Windows) output.

    Lines that do not start with a hop number (headers, "Trace complete.",
    blank lines) are ignored. Annotations such as ``!H`` or
    ``Request timed out.`` are skipped; only IPs, RTTs and ``*`` are kept.

    Args:
        output: Raw text produced by the traceroute tool.

    Returns:
        Hops in the order they appear.
    """
    hops: List[Hop] = []

    for line in output.splitlines():
        match = _HOP_LINE_RE.match(line)
        if not match:
            continue

        hop = Hop(hop_number=int(match.group(1)))

        for token in _TOKEN_RE.finditer(match.group(2)):
            if token.group("star"):
                hop.rtts_ms.append(None)
            elif token.group("rtt"):
                hop.rtts_ms.append(_parse_rtt(token.group("rtt")))
            else:
                address = token.group("ipv4") or token.group("ipv6")
                if _is_valid_ip(address) and address not in hop.addresses:
                    hop.addresses.append(address)

        hops.append(hop)

    return hops


def _parse_destination_ip(output: str, target: str) -> Optional[str]:
    """Find the destination IP from the header, or use the target if it is an IP."""
    match = _HEADER_DEST_RE.search(output)
    if match and _is_valid_ip(match.group(1)):
        return match.group(1)
    return target if _is_valid_ip(target) else None


def _same_ip(a: str, b: str) -> bool:
    try:
        return ipaddress.ip_address(a) == ipaddress.ip_address(b)
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #


def _decode(data: Any) -> str:
    """Normalise subprocess output that may be bytes, str or None."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode(errors="replace")
    return data


def run_traceroute(
    target: str,
    max_hops: int = DEFAULT_MAX_HOPS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    queries: int = DEFAULT_QUERIES,
) -> TracerouteResult:
    """Run a traceroute to ``target`` and return structured results.

    Runtime problems (invalid target, tool not installed, overall timeout,
    unreachable host) are reported in the returned object rather than raised,
    so the caller (``app.py``) can always display something.

    Args:
        target:   Hostname or IP address (ideally the IP resolved by dns.py).
        max_hops: Maximum number of hops to probe (1-64).
        timeout:  Seconds to wait for each probe reply.
        queries:  Probes per hop (1-10; Windows always uses 3).

    Returns:
        TracerouteResult.

    Raises:
        ValueError: Only for invalid ``max_hops``/``timeout``/``queries``,
                    which indicate a programming error in the caller.
    """
    _validate_options(max_hops, timeout, queries)

    try:
        target = validate_target(target)
    except ValueError as exc:
        return TracerouteResult(target=str(target), success=False, error=str(exc))

    command = build_command(target, max_hops, timeout, queries)
    probes_per_hop = 3 if _is_windows() else queries
    overall_timeout = max_hops * probes_per_hop * timeout + SUBPROCESS_GRACE_SECONDS

    result = TracerouteResult(target=target, success=False, command=command)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=overall_timeout,
            check=False,
        )
        output = _decode(completed.stdout)
        stderr = _decode(completed.stderr).strip()
    except FileNotFoundError:
        tool = command[0]
        hint = (
            "Install it with 'sudo apt install traceroute' (Debian/Ubuntu) "
            "or 'sudo dnf install traceroute' (Fedora)."
            if tool == "traceroute" and platform.system() == "Linux"
            else ""
        )
        result.error = f"'{tool}' command not found. {hint}".strip()
        return result
    except subprocess.TimeoutExpired as exc:
        # Keep whatever partial output was produced before the time limit.
        output = _decode(exc.stdout)
        stderr = ""
        result.error = f"Traceroute did not finish within {overall_timeout:.0f} seconds."
    except OSError as exc:
        result.error = f"Could not run '{command[0]}': {exc}"
        return result

    result.raw_output = output
    result.hops = parse_traceroute_output(output)
    result.destination_ip = _parse_destination_ip(output, target)

    if result.destination_ip:
        result.reached_destination = any(
            hop.responded and any(_same_ip(a, result.destination_ip) for a in hop.addresses)
            for hop in result.hops
        )

    if result.hops:
        result.success = True
    elif result.error is None:
        result.error = stderr or "Traceroute produced no hop information."

    return result


# --------------------------------------------------------------------------- #
# Display
# --------------------------------------------------------------------------- #


def _format_ms(value: Optional[float]) -> str:
    if value is None:
        return "*"
    return f"{value:.0f} ms" if value >= 10 else f"{value:.1f} ms"


def format_result(result: TracerouteResult) -> str:
    """Return a printable hop table for the terminal.

    Columns: hop number, responding address, average RTT, individual probes.
    Non-responding hops are shown with ``*``.
    """
    if not result.success:
        return f"Traceroute failed: {result.error}"

    lines = [f"{'Hop':<6}{'Address':<42}{'Avg RTT':<11}Probes"]
    for hop in result.hops:
        address = hop.ip_address or "*"
        if len(hop.addresses) > 1:
            address += f" (+{len(hop.addresses) - 1} more)"
        if hop.responded:
            avg = _format_ms(hop.avg_rtt_ms)
            probes = " / ".join(_format_ms(r) for r in hop.rtts_ms)
        else:
            avg = "*"
            probes = "no response"
        lines.append(f"{hop.hop_number:<6}{address:<42}{avg:<11}{probes}")

    if result.destination_ip:
        status = "reached" if result.reached_destination else "NOT reached"
        lines.append("")
        lines.append(f"Destination {result.destination_ip}: {status}")
    if result.error:
        lines.append(f"Note: {result.error}")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Command-line interface (for testing this module on its own)
# --------------------------------------------------------------------------- #


def _main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run a traceroute and show the hops.")
    parser.add_argument("target", help="Hostname or IP address")
    parser.add_argument("--max-hops", type=int, default=DEFAULT_MAX_HOPS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help="Seconds to wait per probe")
    parser.add_argument("--queries", type=int, default=DEFAULT_QUERIES,
                        help="Probes per hop (ignored on Windows)")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a table")
    args = parser.parse_args(argv)

    try:
        result = run_traceroute(args.target, args.max_hops, args.timeout, args.queries)
    except ValueError as exc:
        parser.error(str(exc))

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_result(result))
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(_main())
