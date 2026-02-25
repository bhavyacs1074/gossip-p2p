import socket
import threading
import sys
from utils import setup_logger


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
                conn.close()
                return

            message = data.decode().strip()

            # Basic validation check
            if len(message) == 0:
                self.logger.warning(f"Blank message from {addr}")
                conn.close()
                return

            self.logger.info(f"Received from {addr}: {message}")

            # For now, just acknowledge
            conn.sendall(b"ACK")

        except Exception as e:
            self.logger.error(f"Error handling connection from {addr}: {e}")
        finally:
            conn.close()


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