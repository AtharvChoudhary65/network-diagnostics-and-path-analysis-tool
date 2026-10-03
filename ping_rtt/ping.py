import platform
import subprocess
import re


def ping(target, count=4):
    """
    Ping a target and calculate basic RTT statistics.

    Returns:
        dict containing:
        target, sent, received, packet_loss,
        min_rtt, avg_rtt, max_rtt
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
            "min_rtt": None,
            "avg_rtt": None,
            "max_rtt": None,
            "error": str(e)
        }

    output = result.stdout + result.stderr

    # Extract RTT values from ping output.
    rtt_values = []

    pattern = r"(?:time[=<]\s*|time[=<])(\d+(?:\.\d+)?)\s*ms"

    matches = re.findall(pattern, output, re.IGNORECASE)

    for match in matches:
        rtt_values.append(float(match))

    received = len(rtt_values)
    packet_loss = ((count - received) / count) * 100

    if rtt_values:
        min_rtt = min(rtt_values)
        avg_rtt = sum(rtt_values) / len(rtt_values)
        max_rtt = max(rtt_values)
    else:
        min_rtt = None
        avg_rtt = None
        max_rtt = None

    return {
        "target": target,
        "sent": count,
        "received": received,
        "packet_loss": round(packet_loss, 2),
        "min_rtt": round(min_rtt, 2) if min_rtt is not None else None,
        "avg_rtt": round(avg_rtt, 2) if avg_rtt is not None else None,
        "max_rtt": round(max_rtt, 2) if max_rtt is not None else None
    }

if __name__ == "__main__":
    target = input("Enter hostname or IP address: ")

    result = ping(target)

    print("\nPing Results")
    print("-" * 30)

    for key, value in result.items():
        print(f"{key}: {value}")