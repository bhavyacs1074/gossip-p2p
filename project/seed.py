import socket
import threading
import sys
import time
from utils import setup_logger, read_seed_config
import json



class SeedNode:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.peer_list = {}  # (ip, port) -> metadata
        self.logger = setup_logger("SEED", port)
        self.all_seeds = read_seed_config()
        self.other_seeds = [
            (ip, port)
            for (ip, port) in self.all_seeds
            if not (ip == self.host and port == self.port)
        ]
        self.num_seeds = len(self.all_seeds)
        self.quorum = (self.num_seeds // 2) + 1 if self.num_seeds > 0 else 1
        self.logger.info(f"Quorum for registration/removal: {self.quorum} of {self.num_seeds}")
        self.logger.info(f"Other seeds: {self.other_seeds}")

    def start_server(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.bind((self.host, self.port))
            server_socket.listen(10)
            self.logger.info(f"Seed listening on {self.host}:{self.port}")
        except Exception as e:
            print("Failed to start server:", e)
            sys.exit(1)

        while True:
            try:
                conn, addr = server_socket.accept()
                thread = threading.Thread(
                    target=self.handle_connection,
                    args=(conn, addr),
                    daemon=True
                )
                thread.start()
            except Exception as e:
                self.logger.error(f"Error accepting connection: {e}")

    def handle_connection(self, conn, addr):
        try:
            data = conn.recv(4096)

            if not data:
                self.logger.warning(f"Empty data from {addr}")
                return

            message = data.decode().strip()
            self.logger.info(f"Received from {addr}: {message}")

            # Parse JSON
            try:
                message_dict = json.loads(message)
            except json.JSONDecodeError:
                self.logger.warning(f"Invalid JSON from {addr}")
                conn.sendall(b"ERROR:INVALID_JSON")
                return

            msg_type = message_dict.get("type")

            if msg_type == "REGISTER":
                self.handle_register(message_dict, conn)

            elif msg_type == "SEED_PROPOSE":
                self.handle_seed_propose(message_dict, conn)

            elif msg_type == "SEED_COMMIT":
                self.handle_seed_commit(message_dict)

            elif msg_type == "DEAD_REPORT":
                self.handle_dead_report(message_dict, conn)

            elif msg_type == "GET_PEER_LIST":
                self.handle_get_peer_list(conn)
            elif msg_type == "PING_SEED":
                response = {"status": "ALIVE"}
                conn.sendall(json.dumps(response).encode())

            else:
                self.logger.warning(f"Unknown message type from {addr}")
                conn.sendall(b"ERROR:UNKNOWN_MESSAGE")

        except Exception as e:
            self.logger.error(f"Error handling connection from {addr}: {e}")
        finally:
            conn.close()
    def handle_register(self, message_dict, conn):
        ip = message_dict.get("ip")
        port = message_dict.get("port")

        if not ip or port is None:
            conn.sendall(b"ERROR:MALFORMED_REGISTER")
            return

        try:
            port = int(port)
        except ValueError:
            conn.sendall(b"ERROR:INVALID_PORT")
            return

        peer_key = (ip, port)

        if peer_key in self.peer_list:
            self.logger.info(f"Peer already registered: {peer_key}")
            conn.sendall(json.dumps({"status": "ALREADY_REGISTERED"}).encode())
            return

        # Initiate seed-level consensus: propose registration to other seeds
        votes = 1  # include self
        self.logger.info(f"Proposing registration of {peer_key} to seeds")

        for (s_ip, s_port) in self.other_seeds:
            try:
                proposal = {
                    "type": "SEED_PROPOSE",
                    "ip": ip,
                    "port": port,
                    "proposer": {"ip": self.host, "port": self.port},
                    "ts": time.time()
                }

                resp = self.send_to_seed(s_ip, s_port, proposal)
                if resp and resp.get("vote") == "YES":
                    votes += 1
            except Exception as e:
                self.logger.error(f"Error proposing to seed {s_ip}:{s_port} - {e}")

        self.logger.info(f"Votes for {peer_key}: {votes}/{self.num_seeds}")

        if votes >= self.quorum:
            # Commit locally
            self.peer_list[peer_key] = {"status": "alive"}
            self.logger.info(f"Peer registered (committed): {peer_key}")

            # Notify other seeds of commit to ensure consistency
            commit_msg = {
                "type": "SEED_COMMIT",
                "ip": ip,
                "port": port,
                "committer": {"ip": self.host, "port": self.port},
                "ts": time.time()
            }

            for (s_ip, s_port) in self.other_seeds:
                try:
                    self.send_to_seed(s_ip, s_port, commit_msg)
                except Exception:
                    pass

            conn.sendall(json.dumps({"status": "REGISTERED", "votes": votes}).encode())
        else:
            self.logger.info(f"Registration rejected for {peer_key} (insufficient votes)")
            conn.sendall(json.dumps({"status": "REJECTED", "votes": votes}).encode())
    def handle_get_peer_list(self, conn):
        peers = [
            {"ip": ip, "port": port}
            for (ip, port) in self.peer_list.keys()
        ]

        response = {
            "type": "PEER_LIST",
            "peers": peers
        }

        conn.sendall(json.dumps(response).encode())
    def send_to_seed(self, ip, port, message_dict):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, port))
                s.sendall(json.dumps(message_dict).encode())
                data = s.recv(4096)
                try:
                    return json.loads(data.decode())
                except Exception:
                    return None
        except Exception as e:
            self.logger.error(f"Failed to contact seed {ip}:{port} - {e}")
            return None

    def handle_seed_propose(self, message_dict, conn):
        # Another seed is proposing to add a peer; decide and vote
        ip = message_dict.get("ip")
        port = message_dict.get("port")
        action = message_dict.get("action", "ADD")

        try:
            port = int(port)
        except Exception:
            resp = {"type": "SEED_VOTE", "vote": "NO"}
            conn.sendall(json.dumps(resp).encode())
            return

        peer_key = (ip, port)

        # Policy depends on action
        if action == "REMOVE":
            # Vote YES to remove only if we currently have the peer
            vote = "YES" if peer_key in self.peer_list else "NO"
        else:
            # ADD/registration: vote NO if already present, else YES
            vote = "NO" if peer_key in self.peer_list else "YES"

        self.logger.info(f"Voting {vote} on proposal ({action}) for {peer_key}")
        resp = {"type": "SEED_VOTE", "vote": vote}
        conn.sendall(json.dumps(resp).encode())

    def handle_seed_commit(self, message_dict):
        ip = message_dict.get("ip")
        port = message_dict.get("port")
        action = message_dict.get("action", "ADD")

        try:
            port = int(port)
        except Exception:
            return

        peer_key = (ip, port)
        if action == "REMOVE":
            if peer_key in self.peer_list:
                del self.peer_list[peer_key]
                self.logger.info(f"Peer removed via commit: {peer_key}")
            else:
                self.logger.info(f"Remove commit received but peer not present: {peer_key}")
            return

        # Default: ADD
        if peer_key in self.peer_list:
            self.logger.info(f"Commit received but peer already present: {peer_key}")
            return

        self.peer_list[peer_key] = {"status": "alive"}
        self.logger.info(f"Peer added via commit: {peer_key}")

    def handle_dead_report(self, message_dict, conn):
        # Received a dead-node report from a peer
        dead_ip = message_dict.get("dead_ip")
        dead_port = message_dict.get("dead_port")
        reporter = message_dict.get("reporter")

        if not dead_ip or dead_port is None:
            conn.sendall(json.dumps({"status": "ERROR", "reason": "MALFORMED_DEAD_REPORT"}).encode())
            return

        try:
            dead_port = int(dead_port)
        except Exception:
            conn.sendall(json.dumps({"status": "ERROR", "reason": "INVALID_PORT"}).encode())
            return

        dead_key = (dead_ip, dead_port)
        self.logger.info(f"Received dead-node report for {dead_key} from {reporter}")

        # Propose removal to other seeds
        votes = 1
        for (s_ip, s_port) in self.other_seeds:
            try:
                proposal = {
                    "type": "SEED_PROPOSE",
                    "ip": dead_ip,
                    "port": dead_port,
                    "action": "REMOVE",
                    "proposer": {"ip": self.host, "port": self.port},
                    "ts": time.time()
                }
                resp = self.send_to_seed(s_ip, s_port, proposal)
                if resp and resp.get("vote") == "YES":
                    votes += 1
            except Exception as e:
                self.logger.error(f"Error proposing removal to seed {s_ip}:{s_port} - {e}")

        self.logger.info(f"Removal votes for {dead_key}: {votes}/{self.num_seeds}")

        if votes >= self.quorum:
            # Commit removal locally
            if dead_key in self.peer_list:
                del self.peer_list[dead_key]
                self.logger.info(f"Peer {dead_key} removed after quorum")
            else:
                self.logger.info(f"Peer {dead_key} not present locally, but removal committed")

            # Notify other seeds to commit
            commit_msg = {
                "type": "SEED_COMMIT",
                "ip": dead_ip,
                "port": dead_port,
                "action": "REMOVE",
                "committer": {"ip": self.host, "port": self.port},
                "ts": time.time()
            }
            for (s_ip, s_port) in self.other_seeds:
                try:
                    self.send_to_seed(s_ip, s_port, commit_msg)
                except Exception:
                    pass

            conn.sendall(json.dumps({"status": "REMOVED", "votes": votes}).encode())
        else:
            self.logger.info(f"Removal rejected for {dead_key} (insufficient votes)")
            conn.sendall(json.dumps({"status": "REJECTED", "votes": votes}).encode())

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python seed.py <port>")
        sys.exit(1)

    try:
        port = int(sys.argv[1])
    except ValueError:
        print("Port must be an integer.")
        sys.exit(1)

    seed = SeedNode("127.0.0.1", port)
    seed.start_server()