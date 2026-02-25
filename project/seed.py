import socket
import threading
import sys
from utils import setup_logger
import json



class SeedNode:

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.peer_list = {}  # (ip, port) -> metadata
        self.logger = setup_logger("SEED", port)

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

            elif msg_type == "GET_PEER_LIST":
                self.handle_get_peer_list(conn)

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
            conn.sendall(b"ALREADY_REGISTERED")
            return

        self.peer_list[peer_key] = {
            "status": "alive"
        }

        self.logger.info(f"Peer registered successfully: {peer_key}")
        conn.sendall(b"REGISTERED")
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