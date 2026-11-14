#!/usr/bin/env python3
"""Prepare a laptop, or run three separate Docker deployments on one computer.

Python 3.10+ standard library only. All credentials stay in ignored lab-data/.
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "lab-data"


def private_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)


def prepare(node, local=False):
    directory = LAB / node
    env = directory / ".env"
    if env.exists():
        raise RuntimeError(f"{env} already exists; retained its keys. Use start/status/seed instead.")
    index = "abc".index(node) + 1
    api, web = (8100 + index, 3100 + index) if local else (8000, 3000)
    values = {"SECRET_KEY": secrets.token_urlsafe(48), "ENCRYPTION_KEY": secrets.token_hex(16),
              "CONSENT_LEDGER_KEY": secrets.token_urlsafe(32), "DB_PASSWORD": secrets.token_hex(24),
              "ADMIN_EMAIL": f"admin-{node}@example.invalid", "ADMIN_PASSWORD": secrets.token_urlsafe(24),
              "API_PORT": str(api), "WEB_PORT": str(web), "FEDERATION_LAB_MODE": "true",
              "FEDERATION_NO_PROXY": "localhost,127.0.0.1,::1,hospital-a,hospital-b,hospital-c",
              "FEDERATION_LOCAL_EPOCHS": "10", "FEDERATION_MIN_PEERS": "2", "FEDERATION_REQUIRE_FRESH_UPDATES": "true",
              "SECURITY_ANALYSIS_INTERVAL_MINUTES": "0", "FEDERATION_SYNC_INTERVAL_MINUTES": "0",
              "FEDERATION_ROUND_INTERVAL_MINUTES": "0"}
    private_write(env, "\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    print(f"Prepared {node}: API {api}, dashboard {web}. Credentials: {env}")


def compose(node, *args, capture=False):
    env = LAB / node / ".env"
    if not env.exists():
        raise RuntimeError(f"Prepare node {node} first.")
    # Explicit project names isolate networks, volumes and containers on one host.
    cmd = ["docker", "compose", "--env-file", str(env), "-p", f"phr-fed-{node}",
           "-f", str(ROOT / "docker-compose.yml"), *args]
    return subprocess.run(cmd, cwd=ROOT, check=True, text=True, capture_output=capture)


def seed(node):
    try:
        result = compose(node, "exec", "-T", "backend", "python", "-m", "scripts.seed_federation_demo",
                         "--node", node, capture=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "See backend logs").strip().splitlines()[-1]
        raise RuntimeError(f"Seeding {node} failed: {detail}") from None
    data = json.loads(result.stdout.strip().splitlines()[-1])
    values = dict(line.split("=", 1) for line in (LAB / node / ".env").read_text().splitlines() if "=" in line)
    config = {"name": f"hospital-{node}", "url": f"http://127.0.0.1:{values['API_PORT']}",
              "user_id": data["admin_id"], "password": values["ADMIN_PASSWORD"]}
    private_write(LAB / node / "login.json", json.dumps(config, indent=2))
    print(f"Seeded {node}: 80 synthetic training and 120 separate validation examples. "
          f"Admin ID: {data['admin_id']}; password is in lab-data/{node}/.env")


def link_local_network():
    """Link only API containers; each hospital database keeps its private network."""
    network = "phr-federation-lab"
    check = subprocess.run(["docker", "network", "inspect", network], capture_output=True)
    if check.returncode:
        subprocess.run(["docker", "network", "create", network], check=True, capture_output=True)
    for node in "abc":
        container = compose(node, "ps", "-q", "backend", capture=True).stdout.strip()
        if not container:
            raise RuntimeError(f"Start node {node} before linking the local network.")
        info = json.loads(subprocess.check_output(["docker", "inspect", container], text=True))[0]
        if network not in info["NetworkSettings"]["Networks"]:
            subprocess.run(["docker", "network", "connect", "--alias", f"hospital-{node}",
                            network, container], check=True)
    print("Local API network connected; the three databases remain isolated.")


class API:
    def __init__(self, config):
        self.config, self.token = config, None

    def call(self, method, path, body=None):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.config["url"].rstrip("/") + path, method=method,
            headers=headers, data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # Do not log request bodies or authentication headers.
            detail = json.loads(exc.read()).get("detail", "request failed")
            raise RuntimeError(f"{self.config['name']} {path}: HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{self.config['name']} unreachable: {exc.reason}") from None

    def login(self):
        self.call("GET", "/api/health")
        self.token = self.call("POST", "/api/login", {"user_id": self.config["user_id"],
            "password": self.config["password"]})["access_token"]


def connect(config):
    nodes = [API(config[key]) for key in ("hub", "a", "c")]
    for node in nodes:
        node.login()
    return nodes


def wire(config):
    hub, *peers = connect(config)
    registered = hub.call("GET", "/api/admin/federated/peers")
    # A wire retry should never rotate or overwrite an existing hospital's keys.
    names = {peer["node_name"] for peer in registered["peers"]}
    for peer in peers:
        name = peer.config["name"]
        participation = peer.call("GET", "/api/admin/federated/participation")
        hub_url = peer.config.get("hub_url", config["hub"]["url"])
        if name in names:
            if participation["configured"] and participation["node_name"] == name and participation["hub_url"] == hub_url:
                continue
            raise RuntimeError(f"{name} exists on hub but is not joined here. Rotate/join using the admin UI.")
        result = hub.call("POST", "/api/admin/federated/peers", {"node_name": name})
        peer.call("PUT", "/api/admin/federated/participation", {"hub_url": hub_url,
            "node_name": name, "shared_secret": result["shared_secret"]})
    print("All three APIs reachable; both participants joined the hub.")


def experiment(config, rounds, output):
    hub, *peers = connect(config)
    nodes = [hub, *peers]
    report = {"description": "Three deployments; local validation data stays at each node. "
              "Synthetic when seeded with federation_lab.py. Not clinical efficacy evidence.", "snapshots": []}

    def snapshot(round_number, elapsed=0, aggregation=None):
        report["snapshots"].append({"round": round_number, "elapsed_seconds": round(elapsed, 3),
            "aggregation": aggregation, "nodes": {node.config["name"]:
                node.call("GET", "/api/admin/federated/classifier")["validation"] for node in nodes}})
        private_write(output, json.dumps(report, indent=2) + "\n")
        table = io.StringIO()
        writer = csv.writer(table, lineterminator="\n")
        writer.writerow(["round", "node", "model", "accuracy", "recall", "f1", "log_loss", "local_accuracy", "candidate_accuracy", "candidate_log_loss"])
        for item in report["snapshots"]:
            for name, metrics in item["nodes"].items():
                used, local = metrics.get("in_use") or {}, metrics.get("local") or {}
                writer.writerow([item["round"], name, metrics.get("model"), used.get("accuracy"),
                    used.get("recall"), used.get("f1"), used.get("log_loss"), local.get("accuracy"),
                    (metrics.get("candidate") or {}).get("accuracy"),
                    (metrics.get("candidate") or {}).get("log_loss")])
        private_write(output.with_suffix(".csv"), table.getvalue())


    initial = hub.call("GET", "/api/admin/security/federated/status")
    if not initial["require_fresh_updates"] or initial["required_peer_submissions"] != 2:
        raise RuntimeError("Experiment requires strict fresh rounds and FEDERATION_MIN_PEERS=2 on the hub.")
    snapshot(initial["latest_round"] or 0)
    for _ in range(rounds):
        start = time.monotonic()
        for peer in peers:
            try:
                peer.call("POST", "/api/admin/federated/hub/submit")
            except RuntimeError as exc:
                # Allows resuming a round after one laptop was temporarily offline.
                if "already submitted for the open round" not in str(exc):
                    raise
        result = hub.call("POST", "/api/admin/security/federated/round")
        if result["real_peer_nodes"] != 2 or result["peer_nodes_simulated"] != 0:
            raise RuntimeError("Round did not contain exactly three real processes.")
        for peer in peers:
            pulled = peer.call("POST", "/api/admin/federated/hub/pull")
            if pulled["hub_round"] != result["round"]:
                raise RuntimeError("A participant pulled a different round; do not mix experiment results.")
        snapshot(result["round"], time.monotonic() - start,
            {"real_nodes": 3, "classifier_nodes": result["classifier"]["classifier_nodes"],
             "classifier_excluded": result["classifier"]["classifier_excluded"],
             "hub_adopted": result["used_for_detection"]})
        print(f"Round {result['round']}: three nodes, metrics saved to {output}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "start", "seed", "status", "stop", "local", "link-local", "wire", "run"])
    parser.add_argument("--node", choices=list("abc"), default="b")
    parser.add_argument("--local-ports", action="store_true")
    parser.add_argument("--config", type=Path, default=LAB / "experiment.json")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", type=Path, default=LAB / "results.json")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".json":
        parser.error("--output must end in .json; a companion .csv is written automatically")
    if not 1 <= args.rounds <= 100:
        parser.error("--rounds must be between 1 and 100")
    try:
        if args.action == "prepare":
            prepare(args.node, args.local_ports)
        elif args.action == "start":
            compose(args.node, "up", "--build", "-d", "--wait")
        elif args.action == "seed":
            seed(args.node)
        elif args.action == "status":
            compose(args.node, "ps")
        elif args.action == "stop":
            compose(args.node, "down")  # retains database volumes
        elif args.action == "link-local":
            link_local_network()
        elif args.action == "local":
            for node in "bac":
                prepare(node, local=True)
                compose(node, "up", "--build", "-d", "--wait")
                seed(node)
            config = {key: json.loads((LAB / node / "login.json").read_text())
                      for key, node in (("hub", "b"), ("a", "a"), ("c", "c"))}
            link_local_network()
            # Requests originate inside the participants on the shared API network.
            for key in ("a", "c"):
                config[key]["hub_url"] = "http://hospital-b:8000"
            private_write(args.config, json.dumps(config, indent=2))
            wire(config)
            experiment(config, args.rounds, args.output)
        else:
            config = json.loads(args.config.read_text())
            if args.action == "wire":
                wire(config)
            else:
                experiment(config, args.rounds, args.output)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
