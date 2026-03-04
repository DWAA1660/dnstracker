import argparse
import datetime
import socket
import threading
import time
import struct
import ssl
from dnslib import DNSRecord, QTYPE

import db_manager

# Upstream DNS server to forward to (1.1.1.1)
UPSTREAM_DNS = '1.1.1.1'
UPSTREAM_PORT = 53

class DNSProxy(threading.Thread):
    def __init__(self, port=53, bind='0.0.0.0', dot_port=853, certfile=None, keyfile=None):
        super().__init__()
        self.port = port
        self.bind = bind
        self.dot_port = dot_port
        self.certfile = certfile
        self.keyfile = keyfile
        self.daemon = True
        self.running = False
        
        # UDP socket for standard DNS
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.bind, self.port))
            print(f"[*] UDP Socket successfully bound to {self.bind}:{self.port}", flush=True)
        except Exception as e:
            self._log_bind_error(e, self.port, "UDP")
            raise e
            
        # TCP socket for standard DNS (required for large queries/zone transfers)
        try:
            self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_sock.bind((self.bind, self.port))
            self.tcp_sock.listen(20)
            print(f"[*] TCP Socket successfully bound to {self.bind}:{self.port}", flush=True)
        except Exception as e:
            self._log_bind_error(e, self.port, "TCP")
            raise e
            
        # DoT (DNS over TLS) socket
        self.dot_sock = None
        if self.certfile and self.keyfile:
            try:
                self.dot_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
                self.dot_context.load_cert_chain(certfile=self.certfile, keyfile=self.keyfile)
                
                self.dot_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.dot_sock.bind((self.bind, self.dot_port))
                self.dot_sock.listen(20)
                print(f"[*] DoT (TLS) Socket successfully bound to {self.bind}:{self.dot_port}", flush=True)
            except Exception as e:
                self._log_bind_error(e, self.dot_port, "DoT/TLS")
                # We don't raise here to allow standard DNS to run even if DoT fails
                print(f"[!] Warning: DoT server failed to start: {e}", flush=True)
        
        # Upstream socket
        self.upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.upstream_sock.settimeout(5.0)

    def _log_bind_error(self, e, port, proto):
        print(f"[!] Failed to bind {proto} to {self.bind}:{port}. Error: {e}", flush=True)
        if port < 1024:
            print("[!] Privileged ports (below 1024) require root/admin privileges.", flush=True)
        if "Address already in use" in str(e) or "[Errno 98]" in str(e):
            print(f"[!] Port {port} is likely occupied by another service (e.g., systemd-resolved).", flush=True)

    def run(self):
        print(f"[*] DNS Server running...", flush=True)
        self.running = True
        
        # Start TCP listener
        threading.Thread(target=self.listen_tcp, args=(self.tcp_sock, self.handle_tcp_client, "Standard TCP"), daemon=True).start()
        
        # Start DoT listener if enabled
        if self.dot_sock:
            threading.Thread(target=self.listen_dot, daemon=True).start()
        
        # Main thread handles UDP
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                client_ip = addr[0]
                threading.Thread(target=self.handle_udp_request, args=(data, addr, client_ip)).start()
            except Exception as e:
                if self.running:
                    print(f"Error receiving DNS query: {e}")

    def listen_tcp(self, sock, handler, name):
        while self.running:
            try:
                client_sock, addr = sock.accept()
                threading.Thread(target=handler, args=(client_sock, addr)).start()
            except Exception as e:
                if self.running:
                    print(f"Error accepting {name} connection: {e}")

    def listen_dot(self):
        while self.running:
            try:
                client_sock, addr = self.dot_sock.accept()
                # Wrap socket with SSL
                try:
                    ssl_sock = self.dot_context.wrap_socket(client_sock, server_side=True)
                    threading.Thread(target=self.handle_tcp_client, args=(ssl_sock, addr)).start()
                except ssl.SSLError as e:
                    print(f"SSL Handshake failed for {addr[0]}: {e}")
                    client_sock.close()
            except Exception as e:
                if self.running:
                    print(f"Error accepting DoT connection: {e}")

    def handle_tcp_client(self, conn, addr):
        client_ip = addr[0]
        try:
            # RFC 1035: TCP messages are prefixed with a 2-byte length field
            length_bytes = conn.recv(2)
            if not length_bytes:
                return
            length = struct.unpack("!H", length_bytes)[0]
            
            # Read the actual DNS message
            data = conn.recv(length)
            while len(data) < length:
                chunk = conn.recv(length - len(data))
                if not chunk:
                    break
                data += chunk
            
            # Process request
            response_data = self.process_query(data, client_ip)
            
            if response_data:
                # Send response length + response
                response_len = struct.pack("!H", len(response_data))
                conn.sendall(response_len + response_data)
                
        except Exception as e:
            # Suppress common connection reset errors
            pass
        finally:
            conn.close()

    def handle_udp_request(self, data, addr, client_ip):
        response_data = self.process_query(data, client_ip)
        if response_data:
            try:
                self.sock.sendto(response_data, addr)
            except Exception as e:
                print(f"Error sending UDP response to {client_ip}: {e}")

    def process_query(self, data, client_ip):
        """Common logic for processing DNS queries (UDP & TCP)"""
        start_time = time.time()
        
        try:
            # Parse the DNS query
            request = DNSRecord.parse(data)
            qname = str(request.q.qname)
            qtype = QTYPE[request.q.qtype]
            
            # Check if domain is blocked
            if db_manager.check_blocked_domain(qname):
                # Create a blocked response (NXDOMAIN)
                reply = request.reply()
                reply.header.rcode = RCODE.NXDOMAIN
                
                end_time = time.time()
                response_time_ms = (end_time - start_time) * 1000
                
                # Log to database
                db_manager.log_query(client_ip, qname, qtype, response_time_ms, 'BLOCKED')
                
                return reply.pack()

            # Forward to upstream (using UDP always for simplicity)
            # Note: For robust production usage, we might want to support TCP upstream too
            self.upstream_sock.sendto(data, (UPSTREAM_DNS, UPSTREAM_PORT))
            response_data, _ = self.upstream_sock.recvfrom(4096)
            
            # Calculate response time
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            # Parse response for status
            response = DNSRecord.parse(response_data)
            status = 'NOERROR' if response.header.rcode == 0 else 'ERROR'
            
            # Log to database
            db_manager.log_query(client_ip, qname, qtype, response_time_ms, status)
            
            return response_data
            
        except Exception as e:
            print(f"Error handling query from {client_ip}: {e}")
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            # Log failure if we can parse the request partially
            try:
                if 'request' not in locals():
                    request = DNSRecord.parse(data)
                
                db_manager.log_query(client_ip, str(request.q.qname), 
                                     QTYPE[request.q.qtype], 
                                     response_time_ms, 'FAILED')
            except:
                pass # Can't parse request, skip logging
            
            return None

    def stop(self):
        self.running = False
        try:
            self.sock.close()
        except: pass
        try:
            self.tcp_sock.close()
        except: pass
        try:
            self.upstream_sock.close()
        except: pass

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
