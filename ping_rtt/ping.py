import platform
import subprocess
import re


def ping(target, count=4):
    """
    Ping a target and calculate latency and RTT statistics.

    Returns:
        Dictionary containing ping results.
    """

    system = platform.system().lower()

    # Windows uses -n, Linux/macOS use -c
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

    # Extract individual RTT values.
    #
    # Windows example:
    # time=20ms
    #
    # Linux/macOS example:
    # time=20.5 ms

    pattern = r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms"

    matches = re.findall(
        pattern,
        output,
        re.IGNORECASE
    )

    latency_values = [
        float(value)
        for value in matches
    ]

    received = len(latency_values)

    # Calculate packet loss
    packet_loss = ((count - received) / count) * 100

    # Calculate RTT statistics
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
        "latency_ms": [
            round(value, 2)
            for value in latency_values
        ],
        "min_rtt": (
            round(min_rtt, 2)
            if min_rtt is not None
            else None
        ),
        "avg_rtt": (
            round(avg_rtt, 2)
            if avg_rtt is not None
            else None
        ),
        "max_rtt": (
            round(max_rtt, 2)
            if max_rtt is not None
            else None
        )
    }


def display_results(result):
    """Display ping results in a clean, aligned format."""

    width = 42

    def row(label, value):
        """Create a perfectly aligned box row."""
        content = f" {label:<13}: {value}"
        return "║" + content.ljust(width) + "║"

    print()

    print("╔" + "═" * width + "╗")
    print("║" + "NETWORK PING DIAGNOSTICS".center(width) + "║")
    print("╠" + "═" * width + "╣")

    print(row("Target", result["target"]))
    print(row("Packets Sent", result["sent"]))
    print(row("Packets Recv", result["received"]))
    print(row("Packet Loss", f"{result['packet_loss']}%"))

    print("╠" + "═" * width + "╣")
    print("║" + "LATENCY / RTT".center(width) + "║")
    print("╠" + "═" * width + "╣")

    if result["latency_ms"]:

        for i, latency in enumerate(
            result["latency_ms"],
            start=1
        ):
            print(
                row(
                    f"Request {i}",
                    f"{latency} ms"
                )
            )

    else:
        print(
            row(
                "Status",
                "No response received."
            )
        )

    print("╠" + "═" * width + "╣")
    print("║" + "RTT STATISTICS".center(width) + "║")
    print("╠" + "═" * width + "╣")

    min_rtt = (
        f"{result['min_rtt']} ms"
        if result["min_rtt"] is not None
        else "N/A"
    )

    avg_rtt = (
        f"{result['avg_rtt']} ms"
        if result["avg_rtt"] is not None
        else "N/A"
    )

    max_rtt = (
        f"{result['max_rtt']} ms"
        if result["max_rtt"] is not None
        else "N/A"
    )

    print(row("Minimum RTT", min_rtt))
    print(row("Average RTT", avg_rtt))
    print(row("Maximum RTT", max_rtt))

    print("╚" + "═" * width + "╝")
    print()


if __name__ == "__main__":

    print()
    print("Network Diagnostics - Ping + RTT")
    print("--------------------------------")

    target = input(
        "Enter hostname or IP address: "
    ).strip()

    if not target:
        print("Please enter a valid hostname or IP address.")

    else:
        result = ping(target)

        if "error" in result:
            print()
            print(f"Error: {result['error']}")

        display_results(result)