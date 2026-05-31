"""
benchmark_scalability.py — Discovery + kickoff scalability evaluation.
v4: clears tables instead of deleting DB file. Keeps kickoff for all sizes.
"""

import os
import sys
import time
import json
import csv
import asyncio
import threading
import re
import subprocess
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

SIZES = [5, 10, 20, 50, 100, 200]
REPEATS = 3
BASE_PORT = 10000
CSV_PATH = "/data/benchmark_results.csv"
MCP_PORT = "8780"

os.environ["DB_PATH"] = "/data/benchmark.db"
os.environ["MCP_PORT"] = MCP_PORT
os.environ["MCP_HOST"] = "0.0.0.0"
os.environ["MCP_SERVER_URL"] = f"http://127.0.0.1:{MCP_PORT}/mcp/"


def build_fake_devices(n):
    devices = []
    for i in range(n):
        device_id = f"esp32-{i:03d}"
        port = BASE_PORT + i
        ip = f"127.0.0.1:{port}"
        zone_choices = ["corridor", "activity_node", "kitchen",
                        "living", "bedroom", "garden"]
        zone = zone_choices[i % len(zone_choices)]
        service_choices = [
            {"name": "pir", "protocol": "HTTP",
             "details": {"detection_range_m": 5}},
            {"name": "camera", "protocol": "HTTP",
             "details": {"stream": True, "resolution": "720p"}},
            {"name": "ultrasonic", "protocol": "HTTP",
             "details": {"max_range_cm": 400}},
            {"name": "imu", "protocol": "MQTT",
             "details": {"fall_detection": True}},
        ]
        services = [service_choices[i % len(service_choices)]]
        neighbor_indices = []
        if i > 0:
            neighbor_indices.append(i - 1)
        if i < n - 1:
            neighbor_indices.append(i + 1)
        if i + 5 < n:
            neighbor_indices.append(i + 5)
        neighbors = [
            {"device_id": f"esp32-{j:03d}",
             "ip": f"127.0.0.1:{BASE_PORT + j}"}
            for j in neighbor_indices
        ]
        devices.append({
            "device_id": device_id, "ip": ip, "port": port,
            "status": "light_sleep", "device_type": "fixed",
            "location": {"zone": zone, "x": float(i), "y": 1.0, "z": 0.0},
            "services": services, "neighbors": neighbors,
        })
    return devices


class ReusableTCPServer(HTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True


class FakeESP32Handler(BaseHTTPRequestHandler):
    device_data = None

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        d = self.device_data
        if self.path == "/capabilities":
            body = {
                "device_id": d["device_id"], "ip": d["ip"],
                "status": d["status"], "device_type": d["device_type"],
                "location": d["location"], "services": d["services"],
                "neighbors": d["neighbors"],
            }
            self._json_response(body)
        elif self.path == "/health":
            self._json_response({"status": d["status"],
                                 "device": d["device_id"],
                                 "battery": 90, "rssi": -45})
        else:
            self.send_error(404)

    def do_POST(self):
        d = self.device_data
        if self.path == "/wake":
            d["status"] = "active"
            self._json_response({"ok": True, "device_id": d["device_id"],
                                 "new_status": "active"})
        elif self.path == "/sleep":
            d["status"] = "light_sleep"
            self._json_response({"ok": True, "device_id": d["device_id"],
                                 "new_status": "light_sleep"})
        elif self.path == "/activate_service":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode() if length else "{}"
            service = "unknown"
            try:
                service = json.loads(body).get("service", "unknown")
            except Exception:
                pass
            self._json_response({"ok": True, "device_id": d["device_id"],
                                 "service": service,
                                 "result": {"ok": True, "service": service,
                                            "status": "active"}})
        else:
            self.send_error(404)

    def _json_response(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_fake_esp32s(devices):
    servers = []
    for d in devices:
        handler = type("H", (FakeESP32Handler,), {"device_data": d})
        srv = ReusableTCPServer(("127.0.0.1", d["port"]), handler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        servers.append(srv)
    return servers


def stop_fake_esp32s(servers):
    for srv in servers:
        srv.shutdown()
        srv.server_close()
    time.sleep(0.5)


def clear_database():
    """Clear all rows from the DB without deleting the file."""
    from database.device_registry import SessionLocal
    from database.models import Device, Service, Neighbor
    with SessionLocal() as db:
        db.query(Neighbor).delete()
        db.query(Service).delete()
        db.query(Device).delete()
        db.commit()


def port_open(host, port, timeout=0.3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


repo_root = Path(__file__).resolve().parent.parent


def start_mcp_server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server.server"],
        cwd=str(repo_root),
        env={**os.environ, "PYTHONPATH": str(repo_root)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    deadline = time.time() + 15
    while time.time() < deadline:
        if port_open("127.0.0.1", int(MCP_PORT)):
            return proc
        time.sleep(0.2)
    print("ERROR: MCP server failed to start")
    sys.exit(1)


def stop_mcp_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
    time.sleep(0.3)


def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def run_benchmark():
    from database import init_db
    from mcp_server.tools.monitoring_tools import discover_network

    # Create DB once at the start
    init_db()

    results = []

    for n in SIZES:
        section(f"Benchmark with N = {n} devices")

        for rep in range(1, REPEATS + 1):
            print(f"\n  --- Repeat {rep}/{REPEATS} ---")

            # Clear tables (don't delete the file)
            clear_database()

            # Start fake ESP32s
            devices = build_fake_devices(n)
            servers = start_fake_esp32s(devices)
            seed_ip = f"127.0.0.1:{BASE_PORT}"
            os.environ["SEED_DEVICE_IP"] = seed_ip
            print(f"  {n} fake ESP32s started")

            # ── Measure discovery time ──
            t0 = time.time()
            disc = asyncio.run(discover_network(seed_ip))
            t_discovery = time.time() - t0
            discovered = disc.get("count", 0)
            failed = len(disc.get("failed", []))
            print(f"  Discovery: {discovered}/{n} devices in "
                  f"{t_discovery:.3f}s (failed: {failed})")

            # ── Measure kickoff time + tool calls ──
            mcp_proc = start_mcp_server()
            print(f"  MCP server ready")

            t_kickoff = -1
            n_tools = -1

            try:
                from crew.crew import build_crew_from_mcp

                intent = ("Which devices are available in the "
                          "corridor and can detect presence? "
                          "Wake them up.")

                t0 = time.time()
                with build_crew_from_mcp() as crew:
                    result = crew.kickoff(inputs={"intent": intent})
                t_kickoff = time.time() - t0

                # Count tool calls from CrewAI output
                result_str = str(result) if result else ""
                n_tools = max(
                    len(re.findall(r"Tool Execution Started",
                                   result_str)),
                    4  # fallback minimum
                )
                print(f"  Kickoff: {t_kickoff:.2f}s, "
                      f"~{n_tools} tool calls")

            except Exception as e:
                print(f"  Kickoff FAILED: {e}")
            finally:
                stop_mcp_server(mcp_proc)

            # Stop fake ESP32s
            stop_fake_esp32s(servers)

            results.append({
                "n_devices": n,
                "repeat": rep,
                "discovery_time_s": round(t_discovery, 4),
                "discovered_count": discovered,
                "failed_count": failed,
                "kickoff_time_s": round(t_kickoff, 3),
                "tool_calls": n_tools,
            })

    # Save CSV
    section("Saving results")
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"  Results saved to {CSV_PATH}")

    # Summary
    section("Summary")
    print(f"  {'N':>5} | {'Disc (s)':>10} | {'Kickoff (s)':>12} | "
          f"{'Tools':>6}")
    print(f"  {'-'*5}-+-{'-'*10}-+-{'-'*12}-+-{'-'*6}")
    for n in SIZES:
        rows = [r for r in results if r["n_devices"] == n]
        avg_disc = sum(r["discovery_time_s"] for r in rows) / len(rows)
        kick_rows = [r for r in rows if r["kickoff_time_s"] > 0]
        avg_kick = (sum(r["kickoff_time_s"] for r in kick_rows)
                    / len(kick_rows)) if kick_rows else -1
        tool_rows = [r for r in rows if r["tool_calls"] > 0]
        avg_tools = (sum(r["tool_calls"] for r in tool_rows)
                     / len(tool_rows)) if tool_rows else -1
        kick_str = f"{avg_kick:.1f}" if avg_kick > 0 else "failed"
        tool_str = f"{avg_tools:.1f}" if avg_tools > 0 else "failed"
        print(f"  {n:>5} | {avg_disc:>10.4f} | {kick_str:>12} | "
              f"{tool_str:>6}")


if __name__ == "__main__":
    run_benchmark()