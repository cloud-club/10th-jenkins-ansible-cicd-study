"""Select the inactive slot from our existing, uniform Nginx upstream."""

import argparse
import json
import re
import sys


def read_slots(config, upstream, hosts, blue_port=20003, green_port=21003):
    config = re.sub(r"#[^\n]*", "", config)
    blocks = re.findall(r"\bupstream\s+" + re.escape(upstream) + r"\s*\{([^{}]*)\}", config)
    if len(blocks) != 1:
        raise ValueError("Expected exactly one existing application upstream")
    directives = [line.strip() for line in blocks[0].split(";") if line.strip()]
    endpoints = []
    for directive in directives:
        match = re.fullmatch(r"server\s+([\d.]+):(\d+)", directive)
        if not match:
            raise ValueError(f"Unsupported upstream directive: {directive!r}")
        endpoints.append((match[1], int(match[2])))
    for slot, port in (("blue", blue_port), ("green", green_port)):
        if sorted(endpoints) == sorted((host, port) for host in hosts):
            return {"active_slot": slot, "target_slot": "green" if slot == "blue" else "blue"}
    raise ValueError("All three expected app servers must use the same assigned slot port")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--hosts", nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps(read_slots(sys.stdin.read(), args.upstream, args.hosts)))
