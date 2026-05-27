import socket

ESP32_IP = "192.168.4.1"
ESP32_PORT = 4210

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(2)

sock.sendto(b"PING", (ESP32_IP, ESP32_PORT))

try:
    data, addr = sock.recvfrom(1024)
    print("Received:", data.decode(), "from", addr)
except socket.timeout:
    print("No response from ESP32")
finally:
    sock.close()