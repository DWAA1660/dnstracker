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
            
            # Create table for blocked domains
            conn.execute('''
                CREATE TABLE IF NOT EXISTS blocked_domains (
                    domain TEXT PRIMARY KEY,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
            
            # Blocked domains count
            blocked_count = conn.execute('SELECT COUNT(*) FROM blocked_domains').fetchone()[0]
            
            return {
                'total_queries': total_queries,
                'top_domains': [dict(row) for row in top_domains],
                'top_clients': [dict(row) for row in top_clients],
                'time_series': [dict(row) for row in time_series],
                'blocked_count': blocked_count
            }
        finally:
            conn.close()

def get_recent_queries(limit=50, client_ip=None, search_term=None, timeframe_minutes=None):
    with _lock:
        conn = get_connection()
        try:
            sql = '''
                SELECT q.timestamp, q.client_ip, COALESCE(d.name, q.client_ip) as client_name, 
                       q.domain, q.record_type, q.status
                FROM queries q
                LEFT JOIN devices d ON q.client_ip = d.ip
                WHERE 1=1
            '''
            params = []
            
            if client_ip:
                sql += ' AND q.client_ip = ?'
                params.append(client_ip)
            
            if search_term:
                sql += ' AND q.domain LIKE ?'
                params.append(f'%{search_term}%')
                
            if timeframe_minutes:
                cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=timeframe_minutes)).strftime('%Y-%m-%d %H:%M:%S')
                sql += ' AND q.timestamp >= ?'
                params.append(cutoff)
                
            sql += ' ORDER BY q.timestamp DESC LIMIT ?'
            params.append(limit)
            
            queries = conn.execute(sql, params).fetchall()
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

def get_blocked_domains():
    with _lock:
        conn = get_connection()
        try:
            domains = conn.execute('SELECT * FROM blocked_domains ORDER BY added_at DESC').fetchall()
            return [dict(row) for row in domains]
        finally:
            conn.close()

def add_blocked_domain(domain):
    with _lock:
        conn = get_connection()
        try:
            conn.execute('INSERT OR IGNORE INTO blocked_domains (domain) VALUES (?)', (domain,))
            conn.commit()
        finally:
            conn.close()

def remove_blocked_domain(domain):
    with _lock:
        conn = get_connection()
        try:
            conn.execute('DELETE FROM blocked_domains WHERE domain = ?', (domain,))
            conn.commit()
        finally:
            conn.close()

def check_blocked_domain(domain):
    with _lock:
        conn = get_connection()
        try:
            # Check for exact match first
            # We might want to handle subdomains later, but let's start with exact/wildcard if needed.
            # For now, let's assume exact match or simple subdomain check if we implement it.
            # Let's just do exact match + "ends with .domain" logic if we want to be fancy, 
            # but the user just asked to "block domains".
            
            # Simple check: is the domain in the table?
            # Remove trailing dot if present for consistency
            clean_domain = domain.rstrip('.')
            
            # Check exact match
            result = conn.execute('SELECT 1 FROM blocked_domains WHERE domain = ?', (clean_domain,)).fetchone()
            if result:
                return True
                
            # Check if any parent domain is blocked (e.g. if example.com is blocked, ads.example.com should be too)
            # This requires iterating parts.
            parts = clean_domain.split('.')
            for i in range(len(parts) - 1):
                parent = '.'.join(parts[i:])
                result = conn.execute('SELECT 1 FROM blocked_domains WHERE domain = ?', (parent,)).fetchone()
                if result:
                    return True
                    
            return False
        finally:
            conn.close()

def cleanup_old_logs(hours=24):
    with _lock:
        conn = get_connection()
        try:
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            result = conn.execute('DELETE FROM queries WHERE timestamp < ?', (cutoff,))
            deleted_count = result.rowcount
            conn.commit()
            return deleted_count
        except Exception as e:
            print(f"Error cleaning up old logs: {e}")
            return 0
        finally:
            conn.close()
