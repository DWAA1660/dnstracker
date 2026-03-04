import multiprocessing
import argparse
import time
import sys
import os

from dns_server import DNSProxy
import db_manager
from web_app import app

def run_dns_server(bind, port):
    print(f"[*] Starting DNS Server on {bind}:{port}", flush=True)
    try:
        proxy = DNSProxy(port=port, bind=bind)
        proxy.start()
        while True:
            time.sleep(1)
    except Exception as e:
        print(f"[!] Error in DNS Server process: {e}", flush=True)
    except KeyboardInterrupt:
        print("\n[*] Stopping DNS Server...", flush=True)
        if 'proxy' in locals():
            proxy.stop()

def run_web_app(host, port):
    print(f"[*] Starting Web Dashboard on http://{host}:{port}")
    # Disable reloader to prevent it from spawning multiple processes in the multiprocessing context
    app.run(host=host, port=port, use_reloader=False)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DNS Tracker')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Global bind IP for both DNS and Web (default: 0.0.0.0)')
    parser.add_argument('--dns-port', type=int, default=53, help='Port for the DNS server to listen on (default: 53)')
    parser.add_argument('--dns-bind', type=str, default=None, help='IP for the DNS server to bind to (overrides --host)')
    parser.add_argument('--web-port', type=int, default=4000, help='Port for the Web Dashboard (default: 4000)')
    parser.add_argument('--web-bind', type=str, default=None, help='IP for the Web Dashboard to bind to (overrides --host)')
    
    args = parser.parse_args()

    # Determine bind addresses
    dns_bind_ip = args.dns_bind if args.dns_bind else args.host
    web_bind_ip = args.web_bind if args.web_bind else args.host

    # Initialize the database
    print("[*] Initializing Database...", flush=True)
    db_manager.init_db()

    # Create processes for DNS server and Web app
    dns_process = multiprocessing.Process(target=run_dns_server, args=(dns_bind_ip, args.dns_port))
    web_process = multiprocessing.Process(target=run_web_app, args=(web_bind_ip, args.web_port))

    try:
        # Start both processes
        dns_process.start()
        web_process.start()
        
        # Keep main process alive
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[*] Shutting down DNS Tracker...")
        if dns_process.is_alive():
            dns_process.terminate()
            dns_process.join()
        if web_process.is_alive():
            web_process.terminate()
            web_process.join()
        print("[*] Shutdown complete.")
        sys.exit(0)
