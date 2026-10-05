# Network Diagnostics and Path Analysis Tool

## Path Analysis

The `path_analysis` module turns raw traceroute hop data into per-hop statistics and flags likely trouble spots along the route.

### Usage

Run a traceroute and analyze it in one step:

```bash
python -m path_analysis <target>
python -m path_analysis 8.8.8.8
```

Or use it from Python with the output of the `traceroute` module:

```python
from traceroute import run_traceroute
from path_analysis.analyzer import analyze_path, summary

result = run_traceroute("example.com")
stats, bottlenecks = analyze_path(result)
print(summary(stats, bottlenecks, result.target, result.reached_destination))
```

`analyze_path` accepts a `TracerouteResult`, a list of `Hop` objects, or plain dicts shaped like `{"hop": 1, "ip": "10.0.0.1", "rtts": [2.1, 2.0, None]}` (`None` means a timed-out probe).

### Output

For each hop the report shows:

| Column | Meaning |
|--------|---------|
| Avg ms | Mean RTT of the probes that got a reply |
| Jitter | Standard deviation of those RTTs |
| Loss % | Share of probes that timed out |
| Delta | Latency added compared to the previous responding hop |

Below the table, a summary lists total hops (and how many were silent), the end-to-end RTT, the biggest latency jump, whether the destination was reached, and any bottlenecks.

### Bottleneck detection

A hop is flagged when either condition holds:

- its latency delta is greater than **50 ms** (`jump_ms`), or
- it shows **partial** packet loss of at least **20%** (`loss_thresh`).

Both thresholds can be changed with the `jump_ms` and `loss_thresh` arguments of `analyze_path`.

### Notes

- Hops with 100% loss (`*`) are reported as silent but not flagged. Many routers ignore traceroute probes, so total silence on its own is not a fault.
- A negative delta can appear when a farther router replies faster than a nearer one. This is normal (ICMP rate limiting or asymmetric routes) and is not treated as an error.
- On networks with several layers of NAT or strict firewalls, only the first few hops may answer and the destination may show as not reached.

### Tests

```bash
python -m pytest
```
