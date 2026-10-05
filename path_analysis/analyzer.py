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
    delta_ms: float | None = None   # added latency vs previous responding hop

def analyze_hop(hop_num, ip, rtts):
    """rtts: list of floats in ms, with None for timeouts."""
    got = [r for r in rtts if r is not None]
    return HopStats(
        hop=hop_num, ip=ip, sent=len(rtts), received=len(got),
        min_rtt=min(got) if got else None,
        avg_rtt=mean(got) if got else None,
        max_rtt=max(got) if got else None,
        jitter=pstdev(got) if len(got) > 1 else 0.0 if got else None,
        loss_pct=100 * (len(rtts) - len(got)) / len(rtts),
    )

def analyze_path(hops, jump_ms=50, loss_thresh=20):
    stats = [analyze_hop(h["hop"], h["ip"], h["rtts"]) for h in hops]
    prev = None
    for s in stats:
        if s.avg_rtt is not None:
            if prev is not None:
                s.delta_ms = s.avg_rtt - prev
            prev = s.avg_rtt
    bottlenecks = [
        s for s in stats
        if (s.delta_ms and s.delta_ms > jump_ms) or s.loss_pct >= loss_thresh
    ]
    return stats, bottlenecks
