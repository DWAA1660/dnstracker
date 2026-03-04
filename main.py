import multiprocessing
import argparse
import time
import sys
import os

from dns_server import DNSProxy
import db_manager
from web_app import app

def run_dns_server(bind, port, dot_port, certfile, keyfile):
    print(f"[*] Starting DNS Server on {bind}:{port}", flush=True)
    if certfile and keyfile:
        print(f"[*] Starting DoT Server on {bind}:{dot_port}", flush=True)
    
    try:
        proxy = DNSProxy(port=port, bind=bind, dot_port=dot_port, certfile=certfile, keyfile=keyfile)
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
    print(f"[*] Starting Web Dashboard on http://{host}:{port}", flush=True)
    # Disable reloader to prevent it from spawning multiple processes in the multiprocessing context
    app.run(host=host, port=port, use_reloader=False)

def run_cleanup_task(interval_hours=1, retention_hours=24):
    print(f"[*] Starting Cleanup Task (Retention: {retention_hours}h, Check interval: {interval_hours}h)", flush=True)
    # Run cleanup immediately on startup
    try:
        deleted = db_manager.cleanup_old_logs(retention_hours)
        if deleted > 0:
            print(f"[*] Cleanup: Removed {deleted} old query logs.", flush=True)
    except Exception as e:
        print(f"[!] Error in initial Cleanup Task: {e}", flush=True)

    while True:
        try:
            time.sleep(interval_hours * 3600)
            deleted = db_manager.cleanup_old_logs(retention_hours)
            if deleted > 0:
                print(f"[*] Cleanup: Removed {deleted} old query logs.", flush=True)
        except Exception as e:
            print(f"[!] Error in Cleanup Task: {e}", flush=True)
            time.sleep(60) # Retry after a minute on error
        except KeyboardInterrupt:
            break

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DNS Tracker')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Global bind IP for both DNS and Web (default: 0.0.0.0)')
    parser.add_argument('--dns-port', type=int, default=53, help='Port for the DNS server to listen on (default: 53)')
    parser.add_argument('--dns-bind', type=str, default=None, help='IP for the DNS server to bind to (overrides --host)')
    parser.add_argument('--dot-port', type=int, default=853, help='Port for DNS over TLS (default: 853)')
    parser.add_argument('--ssl-cert', type=str, default=None, help='Path to SSL certificate file for DoT')
    parser.add_argument('--ssl-key', type=str, default=None, help='Path to SSL key file for DoT')
    parser.add_argument('--web-port', type=int, default=4000, help='Port for the Web Dashboard (default: 4000)')
    parser.add_argument('--web-bind', type=str, default=None, help='IP for the Web Dashboard to bind to (overrides --host)')
    parser.add_argument('--retention', type=int, default=24, help='Hours to keep logs (default: 24)')
    
    args = parser.parse_args()

    # Determine bind addresses
    dns_bind_ip = args.dns_bind if args.dns_bind else args.host
    web_bind_ip = args.web_bind if args.web_bind else args.host

    # Initialize the database
    print("[*] Initializing Database...", flush=True)
    db_manager.init_db()

    # Create processes for DNS server, Web app, and Cleanup task
    dns_process = multiprocessing.Process(target=run_dns_server, args=(dns_bind_ip, args.dns_port, args.dot_port, args.ssl_cert, args.ssl_key))
    web_process = multiprocessing.Process(target=run_web_app, args=(web_bind_ip, args.web_port))
    cleanup_process = multiprocessing.Process(target=run_cleanup_task, args=(1, args.retention))

    try:
        # Start all processes
        dns_process.start()
        web_process.start()
        cleanup_process.start()
        
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
        if cleanup_process.is_alive():
            cleanup_process.terminate()
            cleanup_process.join()
        print("[*] Shutdown complete.")
        sys.exit(0)
