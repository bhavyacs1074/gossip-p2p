import socket
import threading
import sys
import time
import json
import random
import hashlib
from utils import setup_logger, read_seed_config


class PeerNode:
    def __init__(self, host, port):
        self.host = host
        self.port = int(port)
        self.logger = setup_logger("PEER", self.port)

        # Seeds and registration state
        self.seeds = read_seed_config()
        self.registered_seeds = []  # seeds we registered with

        # Peers and neighbors
        self.candidate_peers = set()
        self.neighbors = {}  # retained for backward-compat but not used for persistent sockets

        # Message list to avoid duplicate forwarding
        self.message_list = {}  # hash -> metadata

        # Gossip generation
        self.msg_counter = 0
        self.max_messages = 10

        # Synchronization
        self.lock = threading.Lock()
        # Neighbor list
        self.neighbor_list = []

    def start(self):
        # Start server to accept peer connections
        server = threading.Thread(target=self._start_server, daemon=True)
        server.start()

        # Step 1: register with quorum of seeds
        self.register_with_seeds()

        # Step 2: fetch peer lists and compute neighbors
        self.request_peer_lists()
        self.compute_powerlaw_neighbors()

        # Step 3: connect to neighbors
        self.connect_neighbors()

        # Start gossip generation and liveness threads
        threading.Thread(target=self.generate_gossip_loop, daemon=True).start()
        threading.Thread(target=self.ping_neighbors_loop, daemon=True).start()

        # keep main thread alive
        while True:
            time.sleep(1)

    def _start_server(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((self.host, self.port))
            sock.listen(10)
            self.logger.info(f"Peer listening on {self.host}:{self.port}")
        except Exception as e:
            self.logger.error(f"Failed to start peer server: {e}")
            sys.exit(1)

        while True:
            conn, addr = sock.accept()
            threading.Thread(target=self.handle_connection, args=(conn, addr), daemon=True).start()

    def handle_connection(self, conn, addr):
        try:
            data = conn.recv(8192)
            if not data:
                return
            msg = data.decode().strip()
            try:
                obj = json.loads(msg)
            except Exception:
                self.logger.warning(f"Invalid JSON from {addr}")
                return

            t = obj.get("type")
            if t == "GOSSIP":
                self.handle_gossip(obj, addr)
            elif t == "PING_PEER":
                # simple ack
                conn.sendall(json.dumps({"status": "ALIVE"}).encode())
            elif t == "SUSPICION":
                # peer asks if we can reach a node
                target_ip = obj.get("target_ip")
                target_port = obj.get("target_port")
                can_reach = self._tcp_ping(target_ip, int(target_port))
                resp = {"type": "SUSPICION_RESPONSE", "can_reach": can_reach}
                conn.sendall(json.dumps(resp).encode())
            else:
                self.logger.info(f"Unknown peer message type: {t} from {addr}")
        except Exception as e:
            self.logger.error(f"Error handling peer connection: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def register_with_seeds(self):
        # Register with floor(n/2)+1 random seeds
        n = len(self.seeds)
        if n == 0:
            self.logger.error("No seeds configured")
            return

        k = (n // 2) + 1
        chosen = random.sample(self.seeds, k)
        self.logger.info(f"Registering with seeds: {chosen}")

        for (ip, port) in chosen:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, port))
                    req = {"type": "REGISTER", "ip": self.host, "port": self.port}
                    s.sendall(json.dumps(req).encode())
                    data = s.recv(4096)
                    try:
                        resp = json.loads(data.decode())
                        if resp.get("status") in ("REGISTERED", "ALREADY_REGISTERED"):
                            self.registered_seeds.append((ip, port))
                    except Exception:
                        # older seed may return plain text
                        text = data.decode()
                        if "REGISTERED" in text or "ALREADY_REGISTERED" in text:
                            self.registered_seeds.append((ip, port))
            except Exception as e:
                self.logger.error(f"Failed to register with seed {ip}:{port} - {e}")

        self.logger.info(f"Successfully registered with seeds: {self.registered_seeds}")

    def request_peer_lists(self):
        # Request peer lists from registered seeds and union them
        peers = set()
        for (ip, port) in self.registered_seeds:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, port))
                    req = {"type": "GET_PEER_LIST"}
                    s.sendall(json.dumps(req).encode())
                    data = s.recv(8192)
                    resp = json.loads(data.decode())
                    if resp.get("type") == "PEER_LIST":
                        for p in resp.get("peers", []):
                            peers.add((p.get("ip"), int(p.get("port"))))
            except Exception as e:
                self.logger.error(f"Failed to get peer list from {ip}:{port} - {e}")

        # Remove self if present
        peers.discard((self.host, self.port))
        self.candidate_peers = peers
        self.logger.info(f"Fetched {len(peers)} candidate peers")

    def compute_powerlaw_neighbors(self, alpha=2.0, max_degree=8):
        # Choose a degree following an approximate Zipf (power-law) distribution
        m = min(max_degree, max(1, len(self.candidate_peers)))
        # build pmf
        weights = [1.0 / (k ** alpha) for k in range(1, m + 1)]
        total = sum(weights)
        probs = [w / total for w in weights]
        # sample degree
        r = random.random()
        cum = 0.0
        deg = 1
        for k, p in enumerate(probs, start=1):
            cum += p
            if r <= cum:
                deg = k
                break

        deg = max(1, deg)
        deg = min(deg, len(self.candidate_peers))

        chosen = set()
        candidates = list(self.candidate_peers)
        if not candidates:
            self.logger.info("No candidate peers to choose from")
            return

        # Prefer high-degree nodes by weighting selection by 1/rank
        random.shuffle(candidates)
        while len(chosen) < deg and candidates:
            chosen.add(candidates.pop())

        self.neighbor_list = list(chosen)
        self.logger.info(f"Selected {len(self.neighbor_list)} neighbors: {self.neighbor_list}")

    def connect_neighbors(self):
        for (ip, port) in self.neighbor_list:
            try:
                # test connectivity with a short-lived socket; do not keep persistent sockets
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(5)
                    s.connect((ip, port))
                self.logger.info(f"Neighbor reachable: {ip}:{port}")
            except Exception as e:
                self.logger.error(f"Failed to reach neighbor {ip}:{port} - {e}")

    def generate_gossip_loop(self):
        while self.msg_counter < self.max_messages:
            time.sleep(5)
            self.msg_counter += 1
            ts = int(time.time())
            msg = f"{ts}:{self.host}:{self.msg_counter}"
            packet = {"type": "GOSSIP", "msg": msg, "origin": {"ip": self.host, "port": self.port}, "ts": ts}
            self._record_and_forward(packet, sender=None)

    def handle_gossip(self, obj, addr):
        msg = obj.get("msg")
        if not msg:
            return
        h = hashlib.sha256(msg.encode()).hexdigest()
        with self.lock:
            if h in self.message_list:
                return
            self.message_list[h] = {"first_seen": time.time(), "origin": obj.get("origin")}

        # Log first-time gossip
        origin = obj.get("origin")
        self.logger.info(f"GOSSIP first-time: {msg} from {origin}")

        # Forward to neighbors except sender
        self._forward_to_neighbors(obj, exclude_addr=addr)

    def _record_and_forward(self, packet, sender=None):
        msg = packet.get("msg")
        h = hashlib.sha256(msg.encode()).hexdigest()
        with self.lock:
            if h in self.message_list:
                return
            self.message_list[h] = {"first_seen": time.time(), "origin": packet.get("origin")}

        # send to neighbors
        self._forward_to_neighbors(packet, exclude_addr=sender)

    def _forward_to_neighbors(self, packet, exclude_addr=None):
        data = json.dumps(packet).encode()
        for (ip, port) in list(self.neighbor_list):
            # exclude the sender if provided
            if exclude_addr and (ip, port) == (exclude_addr[0], exclude_addr[1]):
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(3)
                    s.connect((ip, port))
                    s.sendall(data)
            except Exception:
                # leave actual failure handling to ping logic
                pass

    def ping_neighbors_loop(self):
        while True:
            time.sleep(10)
            for (ip, port) in list(self.neighbor_list):
                alive = self._tcp_ping(ip, port)
                if not alive:
                    # start suspicion process
                    threading.Thread(target=self.initiate_suspicion, args=(ip, port), daemon=True).start()

    def _tcp_ping(self, ip, port, timeout=3):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((ip, int(port)))
                s.sendall(json.dumps({"type": "PING_PEER"}).encode())
                data = s.recv(1024)
                try:
                    resp = json.loads(data.decode())
                    return resp.get("status") == "ALIVE"
                except Exception:
                    return False
        except Exception:
            return False

    def initiate_suspicion(self, ip, port):
        # Contact our neighbors asking if they can reach the target
        self.logger.info(f"Initiating suspicion on {ip}:{port}")
        votes_yes = 0
        votes_no = 0
        total = 0
        for (n_ip, n_port) in self.neighbor_list:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(3)
                    s.connect((n_ip, n_port))
                    req = {"type": "SUSPICION", "target_ip": ip, "target_port": port}
                    s.sendall(json.dumps(req).encode())
                    data = s.recv(2048)
                    resp = json.loads(data.decode())
                    if resp.get("type") == "SUSPICION_RESPONSE":
                        total += 1
                        if not resp.get("can_reach"):
                            votes_yes += 1
                        else:
                            votes_no += 1
            except Exception:
                # treat failure to contact neighbor as abstain
                pass

        # require majority among neighbors who responded
        if total == 0:
            self.logger.info(f"No neighbors responded to suspicion for {ip}:{port}")
            return

        if votes_yes >= (total // 2) + 1:
            self.logger.info(f"Peer-level consensus: {ip}:{port} declared dead by neighbors")
            self.send_dead_report_to_seeds(ip, port)
        else:
            self.logger.info(f"Peer-level consensus: {ip}:{port} NOT declared dead (votes_yes={votes_yes}, total={total})")

    def send_dead_report_to_seeds(self, dead_ip, dead_port):
        report = {
            "type": "DEAD_REPORT",
            "dead_ip": dead_ip,
            "dead_port": int(dead_port),
            "reporter": {"ip": self.host, "port": self.port},
            "ts": time.time()
        }

        for (ip, port) in self.registered_seeds:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect((ip, port))
                    s.sendall(json.dumps(report).encode())
                    data = s.recv(4096)
                    try:
                        resp = json.loads(data.decode())
                        self.logger.info(f"Seed {ip}:{port} report response: {resp}")
                    except Exception:
                        self.logger.info(f"Seed {ip}:{port} responded: {data.decode()}")
            except Exception as e:
                self.logger.error(f"Failed to send dead report to seed {ip}:{port} - {e}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python peer.py <port>")
        sys.exit(1)

    port = int(sys.argv[1])
    p = PeerNode("127.0.0.1", port)
    p.start()
