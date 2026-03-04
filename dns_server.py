import argparse
import datetime
import socket
import threading
import time
from dnslib import DNSRecord, QTYPE

import db_manager

# Upstream DNS server to forward to (1.1.1.1)
UPSTREAM_DNS = '1.1.1.1'
UPSTREAM_PORT = 53

class DNSProxy(threading.Thread):
    def __init__(self, port=53, bind='0.0.0.0'):
        super().__init__()
        self.port = port
        self.bind = bind
        self.daemon = True
        self.running = False
        
        # UDP socket for handling DNS requests
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.bind, self.port))
            print(f"[*] Socket successfully bound to {self.bind}:{self.port}", flush=True)
        except Exception as e:
            print(f"[!] Failed to bind to {self.bind}:{self.port}. Error: {e}", flush=True)
            if self.port < 1024:
                print("[!] Privileged ports (below 1024) require root/admin privileges.", flush=True)
            raise e
        
        # Upstream socket
        self.upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.upstream_sock.settimeout(5.0)

    def run(self):
        print(f"[*] DNS Server listening on {self.bind}:{self.port}", flush=True)
        self.running = True
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                client_ip = addr[0]
                
                # Handle request in a separate thread to avoid blocking
                threading.Thread(target=self.handle_request, args=(data, addr, client_ip)).start()
            except Exception as e:
                print(f"Error receiving DNS query: {e}")

    def handle_request(self, data, addr, client_ip):
        start_time = time.time()
        
        try:
            # Parse the DNS query
            request = DNSRecord.parse(data)
            qname = str(request.q.qname)
            qtype = QTYPE[request.q.qtype]
            
            # Forward to upstream
            self.upstream_sock.sendto(data, (UPSTREAM_DNS, UPSTREAM_PORT))
            response_data, _ = self.upstream_sock.recvfrom(4096)
            
            # Send response back to client
            self.sock.sendto(response_data, addr)
            
            # Calculate response time
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            # Parse response for status
            response = DNSRecord.parse(response_data)
            status = 'NOERROR' if response.header.rcode == 0 else 'ERROR'
            
            # Log to database
            db_manager.log_query(client_ip, qname, qtype, response_time_ms, status)
            
        except Exception as e:
            print(f"Error handling query from {client_ip}: {e}")
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            db_manager.log_query(client_ip, str(request.q.qname) if 'request' in locals() else 'unknown', 
                                 QTYPE[request.q.qtype] if 'request' in locals() else 'unknown', 
                                 response_time_ms, 'FAILED')

    def stop(self):
        self.running = False
        self.sock.close()
        self.upstream_sock.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DNS Tracker')
    parser.add_argument('--port', type=int, default=53, help='Port to listen on')
    parser.add_argument('--bind', type=str, default='0.0.0.0', help='IP to bind to')
    args = parser.parse_args()

    db_manager.init_db()
    proxy = DNSProxy(port=args.port, bind=args.bind)
    proxy.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Stopping DNS Server...")
        proxy.stop()
