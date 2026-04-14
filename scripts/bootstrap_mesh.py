"""
bootstrap_mesh.py — Tell each ESP32 the runtime IP of its neighbors,
then trigger a mesh discovery from any seed.

Why this script exists:
    IPs are handed out by DHCP, so they cannot be hard-coded at
    compile time. But the mesh discovery walk (discover_network)
    relies on each device announcing its neighbors WITH their IPs.
    This script bridges that gap: you tell it the 3 IPs you observed
    on the serial monitors, and it POSTs /set_neighbor to each device
    with the right info. After that, discovery from any seed will
    traverse the whole network.

Usage:
    python -m scripts.bootstrap_mesh \\
        --badge 192.168.1.50 \\
        --fixe  192.168.1.51 \\
        --cam   192.168.1.52

Then check everything is linked:
    curl http://192.168.1.50/capabilities
    curl http://192.168.1.51/capabilities
    curl http://192.168.1.52/capabilities

And run a full discovery from one of them:
    python -m scripts.bootstrap_mesh --discover-from 192.168.1.52
"""

import argparse
import asyncio
import json
import sys

import httpx


# Topology declaration — who is neighbor of whom.
# This mirrors the NEIGHBOR_IDS arrays hard-coded in each firmware.
# If you ever add more devices, extend this dict and the firmware to match.
TOPOLOGY = {
    "badge-001":      [],  # badge has no declared neighbors
    "esp32-fixe-001": ["esp32-cam-001"],
    "esp32-cam-001":  ["esp32-fixe-001", "badge-001"],
}


async def post_set_neighbor(http, ip, neighbor_id, neighbor_ip):
    url = f"http://{ip}/set_neighbor"
    payload = {"device_id": neighbor_id, "ip": neighbor_ip}
    try:
        r = await http.post(url, json=payload, timeout=5.0)
        r.raise_for_status()
        return True, r.json()
    except Exception as e:
        return False, str(e)


async def teach_neighbors(device_map):
    """device_map = {"badge-001": "192.168.1.50", ...}"""
    async with httpx.AsyncClient() as http:
        for device_id, device_ip in device_map.items():
            neighbors = TOPOLOGY.get(device_id, [])
            if not neighbors:
                print(f"  {device_id:<18} no declared neighbors, skipping")
                continue
            for nid in neighbors:
                if nid not in device_map:
                    print(f"  {device_id:<18} -> {nid:<18} "
                          f"WARN: neighbor IP not provided, skipping")
                    continue
                nip = device_map[nid]
                ok, resp = await post_set_neighbor(http, device_ip, nid, nip)
                status = "OK" if ok else "FAILED"
                print(f"  {device_id:<18} -> {nid:<18} "
                      f"({nip:<16}) {status}")
                if not ok:
                    print(f"      error: {resp}")


async def run_discovery(seed_ip):
    """Run the mesh discovery from a seed, print the result."""
    # Lazy import to avoid pulling CrewAI deps when not needed
    from mcp_server.tools.monitoring_tools import discover_network
    print(f"\n  Running discover_network(seed_ip={seed_ip!r})...")
    r = await discover_network(seed_ip)
    print(json.dumps(r, indent=2, default=str))


def main():
    ap = argparse.ArgumentParser(
        description="Teach each ESP32 its neighbors' IPs and/or run "
                    "a mesh discovery.")
    ap.add_argument("--badge", help="IP of the patient badge")
    ap.add_argument("--fixe",  help="IP of the ultrasonic fixed node")
    ap.add_argument("--cam",   help="IP of the ESP32-CAM")
    ap.add_argument("--discover-from",
                    help="Run discover_network from this seed IP after teaching")
    args = ap.parse_args()

    device_map = {}
    if args.badge: device_map["badge-001"]      = args.badge
    if args.fixe:  device_map["esp32-fixe-001"] = args.fixe
    if args.cam:   device_map["esp32-cam-001"]  = args.cam

    if not device_map and not args.discover_from:
        ap.print_help()
        sys.exit(1)

    if device_map:
        print("Teaching neighbors their IPs...")
        asyncio.run(teach_neighbors(device_map))

    if args.discover_from:
        port = 80 if ":" not in args.discover_from else ""
        seed = args.discover_from + (f":{port}" if port else "")
        asyncio.run(run_discovery(seed))


if __name__ == "__main__":
    main()
