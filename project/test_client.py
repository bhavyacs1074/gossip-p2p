import socket

HOST = "127.0.0.1"
PORT = 5000  # change if needed

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    s.sendall(b"HELLO_SEED")
    data = s.recv(1024)

print("Response from seed:", data.decode())