import sqlite3
import datetime
import threading
import os

DB_PATH = 'dns_tracker.db'
_lock = threading.Lock()

def get_connection():
    # Setting check_same_thread=False since we use a lock
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency between processes
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

def init_db():
    with _lock:
        conn = get_connection()
        try:
            # Create table for DNS queries
            conn.execute('''
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    client_ip TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    response_time_ms REAL,
                    status TEXT
                )
            ''')
            # Create indexes for faster querying
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON queries(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_client_ip ON queries(client_ip)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_domain ON queries(domain)')
            
            # Create a table for devices (optional, to give friendly names to IPs)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS devices (
                    ip TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    last_seen DATETIME
                )
            ''')
            conn.commit()
        finally:
            conn.close()

def log_query(client_ip, domain, record_type, response_time_ms, status):
    with _lock:
        conn = get_connection()
        try:
            now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute('''
                INSERT INTO queries (timestamp, client_ip, domain, record_type, response_time_ms, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (now, client_ip, domain, record_type, response_time_ms, status))
            
            # Update last seen for device
            conn.execute('''
                INSERT INTO devices (ip, name, last_seen)
                VALUES (?, ?, ?)
                ON CONFLICT(ip) DO UPDATE SET last_seen=excluded.last_seen
            ''', (client_ip, f"Device ({client_ip})", now))
            
            conn.commit()
        except Exception as e:
            print(f"Error logging query: {e}")
        finally:
            conn.close()

def get_stats(timeframe_hours=24):
    with _lock:
        conn = get_connection()
        try:
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=timeframe_hours)).strftime('%Y-%m-%d %H:%M:%S')
            
            # Total queries
            total_queries = conn.execute('SELECT COUNT(*) FROM queries WHERE timestamp >= ?', (cutoff,)).fetchone()[0]
            
            # Top domains
            top_domains = conn.execute('''
                SELECT domain, COUNT(*) as count 
                FROM queries 
                WHERE timestamp >= ? 
                GROUP BY domain 
                ORDER BY count DESC 
                LIMIT 10
            ''', (cutoff,)).fetchall()
            
            # Top clients
            top_clients = conn.execute('''
                SELECT q.client_ip, COALESCE(d.name, q.client_ip) as name, COUNT(*) as count 
                FROM queries q
                LEFT JOIN devices d ON q.client_ip = d.ip
                WHERE q.timestamp >= ? 
                GROUP BY q.client_ip 
                ORDER BY count DESC 
                LIMIT 10
            ''', (cutoff,)).fetchall()
            
            # Queries over time (hourly)
            time_series = conn.execute('''
                SELECT strftime('%Y-%m-%d %H:00:00', timestamp) as hour, COUNT(*) as count
                FROM queries
                WHERE timestamp >= ?
                GROUP BY hour
                ORDER BY hour ASC
            ''', (cutoff,)).fetchall()
            
            return {
                'total_queries': total_queries,
                'top_domains': [dict(row) for row in top_domains],
                'top_clients': [dict(row) for row in top_clients],
                'time_series': [dict(row) for row in time_series]
            }
        finally:
            conn.close()

def get_recent_queries(limit=50):
    with _lock:
        conn = get_connection()
        try:
            queries = conn.execute('''
                SELECT q.timestamp, q.client_ip, COALESCE(d.name, q.client_ip) as client_name, 
                       q.domain, q.record_type, q.status
                FROM queries q
                LEFT JOIN devices d ON q.client_ip = d.ip
                ORDER BY q.timestamp DESC
                LIMIT ?
            ''', (limit,)).fetchall()
            return [dict(row) for row in queries]
        finally:
            conn.close()

def get_devices():
    with _lock:
        conn = get_connection()
        try:
            devices = conn.execute('SELECT * FROM devices ORDER BY last_seen DESC').fetchall()
            return [dict(row) for row in devices]
        finally:
            conn.close()

def update_device_name(ip, name):
    with _lock:
        conn = get_connection()
        try:
            conn.execute('''
                UPDATE devices SET name = ? WHERE ip = ?
            ''', (name, ip))
            conn.commit()
        finally:
            conn.close()
