import socket
import sys
import json

if len(sys.argv) < 3:
    print("Usage:")
    print("REGISTER: python test_client.py <seed_port> REGISTER <peer_port>")
    print("GET:      python test_client.py <seed_port> GET")
    print("DEAD:     python test_client.py <seed_port> DEAD <dead_peer_port>")
    sys.exit(1)

HOST = "127.0.0.1"
seed_port = int(sys.argv[1])
command = sys.argv[2]

# Build JSON message
if command == "REGISTER":
    if len(sys.argv) != 4:
        print("REGISTER requires peer_port")
        sys.exit(1)

    peer_port = int(sys.argv[3])

    message_dict = {
        "type": "REGISTER",
        "ip": HOST,
        "port": peer_port
    }

elif command == "GET":
    message_dict = {
        "type": "GET_PEER_LIST"
    }

elif command == "DEAD":
    if len(sys.argv) != 4:
        print("DEAD requires dead_peer_port")
        sys.exit(1)

    dead_port = int(sys.argv[3])
    message_dict = {
        "type": "DEAD_REPORT",
        "dead_ip": HOST,
        "dead_port": dead_port,
        "reporter": {"ip": HOST, "port": 0}
    }

else:
    print("Unknown command. Use REGISTER or GET")
    sys.exit(1)

# Convert dictionary to JSON string
message = json.dumps(message_dict)

# Send to seed
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, seed_port))
    s.sendall(message.encode())
    data = s.recv(4096)

print("Response from seed:", data.decode())