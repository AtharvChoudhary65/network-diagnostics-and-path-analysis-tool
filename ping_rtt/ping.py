import platform
import subprocess
import re


def ping(target, count=4):
    """
    Ping a target and calculate latency/RTT statistics.

    Returns:
        dict containing:
        target, sent, received, packet_loss,
        latency_ms, min_rtt, avg_rtt, max_rtt
    """

    system = platform.system().lower()

    if system == "windows":
        command = ["ping", "-n", str(count), target]
    else:
        command = ["ping", "-c", str(count), target]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )

    except subprocess.TimeoutExpired:
        return {
            "target": target,
            "sent": count,
            "received": 0,
            "packet_loss": 100.0,
            "latency_ms": [],
            "min_rtt": None,
            "avg_rtt": None,
            "max_rtt": None,
            "error": "Ping timed out"
        }

    except Exception as e:
        return {
            "target": target,
            "sent": count,
            "received": 0,
            "packet_loss": 100.0,
            "latency_ms": [],
            "min_rtt": None,
            "avg_rtt": None,
            "max_rtt": None,
            "error": str(e)
        }

    output = result.stdout + result.stderr

    # Find individual RTT/latency values.
    # Example:
    # Windows: time=24ms
    # Linux:   time=24.5 ms
    pattern = r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms"

    matches = re.findall(pattern, output, re.IGNORECASE)

    latency_values = [float(value) for value in matches]

    received = len(latency_values)

    packet_loss = ((count - received) / count) * 100

    if latency_values:
        min_rtt = min(latency_values)
        avg_rtt = sum(latency_values) / len(latency_values)
        max_rtt = max(latency_values)
    else:
        min_rtt = None
        avg_rtt = None
        max_rtt = None

    return {
        "target": target,
        "sent": count,
        "received": received,
        "packet_loss": round(packet_loss, 2),
        "latency_ms": [round(value, 2) for value in latency_values],
        "min_rtt": round(min_rtt, 2) if min_rtt is not None else None,
        "avg_rtt": round(avg_rtt, 2) if avg_rtt is not None else None,
        "max_rtt": round(max_rtt, 2) if max_rtt is not None else None
    }


if __name__ == "__main__":
    target = input("Enter hostname or IP address: ")

    result = ping(target)

    print("\nPing / Latency Results")
    print("-" * 35)

    print(f"Target       : {result['target']}")
    print(f"Packets Sent : {result['sent']}")
    print(f"Packets Recv : {result['received']}")
    print(f"Packet Loss  : {result['packet_loss']}%")

    print("\nLatency per request:")
    
    if result["latency_ms"]:
        for i, latency in enumerate(result["latency_ms"], start=1):
            print(f"Request {i}: {latency} ms")
    else:
        print("No response received.")

    print("\nRTT Statistics")
    print("-" * 35)
    print(f"Minimum RTT  : {result['min_rtt']} ms")
    print(f"Average RTT  : {result['avg_rtt']} ms")
    print(f"Maximum RTT  : {result['max_rtt']} ms")