from path_analysis.analyzer import analyze_path

def test_bottleneck_and_loss():
    hops = [
        {"hop": 1, "ip": "192.168.1.1", "rtts": [2.0, 2.1, 1.9]},
        {"hop": 2, "ip": "10.0.0.1",    "rtts": [12.0, 11.5, 12.5]},
        {"hop": 3, "ip": None,          "rtts": [None, None, None]},
        {"hop": 4, "ip": "8.8.8.8",     "rtts": [90.0, 95.0, None]},
    ]
    stats, bottlenecks = analyze_path(hops)

    assert stats[0].loss_pct == 0
    assert stats[2].loss_pct == 100
    assert stats[3].loss_pct > 30
    assert 4 in [b.hop for b in bottlenecks]
