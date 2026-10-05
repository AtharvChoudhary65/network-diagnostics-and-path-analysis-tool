"""Run: python -m path_analysis <target>"""
import sys

from traceroute import run_traceroute

from .analyzer import analyze_path, summary


def main():
    if len(sys.argv) < 2:
        print("usage: python -m path_analysis <target>")
        return 1
    result = run_traceroute(sys.argv[1])
    if not result.success:
        print(f"Traceroute failed: {result.error}")
        return 1
    stats, bottlenecks = analyze_path(result)
    print(summary(stats, bottlenecks, result.target, result.reached_destination))
    return 0


sys.exit(main())
