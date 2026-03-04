# DNS Tracker

A Python-based DNS server that forwards queries to 1.1.1.1 (Cloudflare) while keeping detailed track of what websites are queried by which devices. It includes a beautiful web dashboard built with Tailwind CSS and Chart.js to visualize the statistics.

## Features

- **DNS Forwarding:** Acts as a proxy, forwarding all queries to 1.1.1.1 and sending the responses back.
- **Detailed Logging:** Logs every query, including the client IP, domain, record type, response time, and status.
- **Web Dashboard:** A modern, responsive web interface to view:
  - Total queries and active devices
  - Queries over time (line chart)
  - Top requested domains (bar chart)
  - Top clients (by volume of requests)
  - Real-time recent queries log
- **Device Management:** Assign friendly names to IP addresses on your network.
- **Long-term Storage:** Uses SQLite to store queries efficiently over long periods.

## Requirements

- Python 3.8+
- Root/Administrator privileges (required to bind to port 53 for DNS)

## Installation

1. Clone or download this repository.
2. Install the required Python packages:

```bash
pip install -r requirements.txt
```

## Usage

Since DNS uses port 53, you typically need root or administrator privileges to run the server.

```bash
# On Linux/macOS
sudo python main.py

# On Windows (Run Command Prompt or PowerShell as Administrator)
python main.py
```

### Command Line Arguments

You can customize the ports and bind addresses if you don't want to use the defaults:

```bash
# Bind both DNS and Web to a specific public IP
python main.py --host 170.205.30.132

# Bind to different IPs/ports individually
python main.py --dns-port 5353 --web-port 4000 --host 0.0.0.0
```

- `--host`: Global bind IP for both DNS and Web (default: 0.0.0.0).
- `--dns-port`: Port for the DNS server to listen on (default: 53).
- `--dns-bind`: IP for the DNS server to bind to (overrides --host).
- `--web-port`: Port for the Web Dashboard (default: 4000).
- `--web-bind`: IP for the Web Dashboard to bind to (overrides --host).

## Accessing the Dashboard

Once the server is running, open your web browser and navigate to:

```
http://localhost:4000
```
*(Or replace `localhost` with the IP address of the machine running the tracker)*

## Using the DNS Server

To actually track queries, you need to point your devices to use this machine as their DNS server.

1. Find the IP address of the machine running DNS Tracker (e.g., `192.168.1.100`).
2. Go to your device's network settings (Windows, macOS, iOS, Android).
3. Change the DNS Server settings from Automatic/DHCP to Manual.
4. Enter the IP address of the DNS Tracker machine.

Alternatively, to track your entire network, you can change the DNS settings in your home router to point to this machine.

## Architecture

- `dns_server.py`: The UDP socket server that parses DNS requests using `dnslib` and forwards them to 1.1.1.1.
- `web_app.py`: A Flask application providing the REST API and serving the dashboard.
- `db_manager.py`: Handles all SQLite database operations securely with thread locks.
- `main.py`: The entry point that uses `multiprocessing` to run both the DNS server and the Web app concurrently.
- `templates/index.html`: The frontend dashboard using Tailwind CSS and Chart.js.
