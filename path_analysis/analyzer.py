from dataclasses import dataclass
from statistics import mean, pstdev


@dataclass
class HopStats:
    hop: int
    ip: str | None
    sent: int
    received: int
    min_rtt: float | None
    avg_rtt: float | None
    max_rtt: float | None
    jitter: float | None
    loss_pct: float
    delta_ms: float | None = None  # latency added vs previous responding hop


def _unpack(h):
    """Accept a traceroute Hop object or a plain dict."""
    if isinstance(h, dict):
        return h["hop"], h["ip"], h["rtts"]
    return h.hop_number, h.ip_address, h.rtts_ms


def analyze_hop(hop_num, ip, rtts):
    """rtts: list of floats in ms, with None for timeouts."""
    got = [r for r in rtts if r is not None]
    return HopStats(
        hop=hop_num,
        ip=ip,
        sent=len(rtts),
        received=len(got),
        min_rtt=min(got) if got else None,
        avg_rtt=mean(got) if got else None,
        max_rtt=max(got) if got else None,
        jitter=pstdev(got) if len(got) > 1 else 0.0 if got else None,
        loss_pct=100 * (len(rtts) - len(got)) / len(rtts) if rtts else 100.0,
    )


def analyze_path(hops, jump_ms=50, loss_thresh=20):
    """hops: a TracerouteResult, a list of Hop objects, or a list of dicts."""
    if hasattr(hops, "hops"):
        hops = hops.hops
    stats = [analyze_hop(*_unpack(h)) for h in hops]

    prev = None
    for s in stats:
        if s.avg_rtt is not None:
            if prev is not None:
                s.delta_ms = s.avg_rtt - prev
            prev = s.avg_rtt

    # Fully silent hops (100% loss) are usually routers ignoring probes,
    # so only partial loss or a big latency jump counts as a bottleneck.
    bottlenecks = [
        s for s in stats
        if (s.delta_ms is not None and s.delta_ms > jump_ms)
        or (0 < s.loss_pct < 100 and s.loss_pct >= loss_thresh)
    ]
    return stats, bottlenecks


def summary(stats, bottlenecks, target=None, reached=None):
    lines = []
    if target:
        lines.append(f"Path analysis for {target}")
    lines.append(f"{'Hop':>3}  {'IP':<18}{'Avg ms':>9}{'Jitter':>9}{'Loss %':>8}{'Delta':>9}")
    for s in stats:
        ip = s.ip or "*"
        if s.avg_rtt is None:
            lines.append(f"{s.hop:>3}  {ip:<18}{'-':>9}{'-':>9}{s.loss_pct:>8.0f}{'-':>9}")
        else:
            delta = f"{s.delta_ms:+.1f}" if s.delta_ms is not None else "-"
            lines.append(
                f"{s.hop:>3}  {ip:<18}{s.avg_rtt:>9.1f}{s.jitter:>9.1f}"
                f"{s.loss_pct:>8.0f}{delta:>9}"
            )

    responding = [s for s in stats if s.avg_rtt is not None]
    lines.append("")
    lines.append(f"Total hops: {len(stats)} "
                 f"({sum(1 for s in stats if s.avg_rtt is None)} silent)")
    if responding:
        lines.append(f"End-to-end RTT (last responding hop): {responding[-1].avg_rtt:.1f} ms")
        with_delta = [s for s in responding if s.delta_ms is not None]
        if with_delta:
            worst = max(with_delta, key=lambda s: s.delta_ms)
            lines.append(f"Biggest latency jump: hop {worst.hop} ({worst.ip}) "
                         f"+{worst.delta_ms:.1f} ms")
    if reached is not None:
        lines.append(f"Destination reached: {'yes' if reached else 'no'}")
    if bottlenecks:
        lines.append("Possible bottlenecks: " + ", ".join(f"hop {b.hop}" for b in bottlenecks))
    else:
        lines.append("No bottlenecks detected.")
    return "\n".join(lines)
