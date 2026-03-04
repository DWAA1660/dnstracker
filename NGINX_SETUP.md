# Setting up "Private DNS" (DNS over TLS) with Native Python Support

You can now run "Private DNS" (DoT) directly within the Python tracker. This is **better** than using Nginx for DNS because it preserves the **real client IP address** in your logs.

## Prerequisites

1.  **Domain Name**: A domain (e.g., `privatedns.lunes.host`) pointing to your server IP `170.205.30.132`.
2.  **SSL Certificate**: You need `fullchain.pem` and `privkey.pem` (e.g., from Let's Encrypt).

## 1. Stop Nginx DNS Stream (If previously configured)

If you followed the previous guide, **remove** the `stream { ... }` block from your `nginx.conf`. You only need Nginx for the Web Dashboard now.

## 2. Configure Nginx (Web Dashboard Only)

Use Nginx only to secure the Web Dashboard (HTTPS).

```nginx
# /etc/nginx/sites-available/dnstracker (or similar)

server {
    listen 80;
    server_name privatedns.lunes.host;
    return 301 https://$server_name$request_uri;
}

server {
  listen 443 ssl http2;
  server_name privatedns.lunes.host;

  ssl_certificate /etc/letsencrypt/live/privatedns.lunes.host/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/privatedns.lunes.host/privkey.pem;

  client_max_body_size 500m;

  location / {
    proxy_pass http://127.0.0.1:4000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}

```

### Enable the Site
Make sure to link the file and reload Nginx:

```bash
# 1. Check if the config is valid
sudo nginx -t

# 2. Link it to sites-enabled
sudo ln -s /etc/nginx/sites-available/dnstracker /etc/nginx/sites-enabled/

# 3. Reload Nginx
sudo systemctl reload nginx
```

## 3. Run the Tracker

Run the tracker with the SSL arguments. This will bind:
*   **UDP/53**: Standard DNS
*   **TCP/53**: Standard DNS
*   **TCP/853**: Private DNS (DoT) - **Native Support**
*   **TCP/4000**: Web Dashboard (Localhost only recommended if using Nginx)

```bash
sudo python3 main.py \
  --dns-bind 170.205.30.132 \
  --web-bind 127.0.0.1 \
  --ssl-cert /etc/letsencrypt/live/privatedns.lunes.host/fullchain.pem \
  --ssl-key /etc/letsencrypt/live/privatedns.lunes.host/privkey.pem
```

*Note: Replace `170.205.30.132` with your actual public IP. Do NOT use `0.0.0.0` if `systemd-resolved` is running on your server.*

## 4. Configure Android

1.  **Settings > Network & internet > Private DNS**.
2.  Hostname: `privatedns.lunes.host`.
3.  The tracker will now see your phone's **actual public IP**, not the server's local IP.

## Why this works without Nginx forwarding DNS

You might wonder why Nginx doesn't need to forward ports 53 or 853.
*   **Android** resolves `privatedns.lunes.host` to `170.205.30.132`.
*   **Android** then connects directly to **port 853** on that IP.
*   **Python** is listening directly on port 853 (thanks to the arguments we passed).
*   **Nginx** is only used to serve the Web Dashboard on port 443 and 80.

## Important: Firewall / Security Groups

Since Nginx isn't managing the DNS ports, you must ensure your server's firewall allows traffic on them.

**If using UFW (Ubuntu/Debian):**
```bash
sudo ufw allow 53/udp
sudo ufw allow 53/tcp
sudo ufw allow 853/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw reload
```

**If using AWS/GCP/Azure:**
You must edit your **Security Group** or **Firewall Rules** in your cloud provider's console to allow Inbound Traffic:
*   **Custom UDP** -> Port 53 (Anywhere / 0.0.0.0/0)
*   **Custom TCP** -> Port 53 (Anywhere / 0.0.0.0/0)
*   **Custom TCP** -> Port 853 (Anywhere / 0.0.0.0/0)
*   **HTTP** -> Port 80
*   **HTTPS** -> Port 443

## 5. (Optional) Run as a Systemd Service

To keep the tracker running in the background and restart automatically on boot:

1.  **Edit `dnstracker.service`**:
    *   Update `WorkingDirectory` to your actual project path (e.g., `/home/ubuntu/dnstracker`).
    *   Update `ExecStart` path to python (e.g., `/usr/bin/python3`) and your certificate paths.

2.  **Install the Service**:
    ```bash
    sudo cp dnstracker.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable dnstracker
    sudo systemctl start dnstracker
    ```

3.  **Check Status**:
    ```bash
    sudo systemctl status dnstracker
    ```

## 6. (Optional) Add Basic Auth to Nginx

Since the dashboard is public if anyone hits `https://privatedns.lunes.host`, you should add a password.

1.  **Install tools**: `sudo apt install apache2-utils`
2.  **Create user**: `sudo htpasswd -c /etc/nginx/.htpasswd admin`
3.  **Update Nginx Config**:
    Add these lines inside the `location /` block:
    ```nginx
    auth_basic "Private DNS Dashboard";
    auth_basic_user_file /etc/nginx/.htpasswd;
    ```
4.  **Reload Nginx**: `sudo systemctl reload nginx`

