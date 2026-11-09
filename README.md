# File Retention Manager

A Flask dashboard plus a separate APScheduler worker for scheduled, recursive file-retention cleanup.

## Safety defaults

- New installations use **Dry Run** mode.
- Retention defaults to **4 calendar months** (not a fixed 120-day approximation).
- Only regular files are eligible. Directories and symbolic links are skipped.
- Files are checked again immediately before unlinking.
- Per-file filesystem errors are logged and do not stop the scan.
- Logs rotate at 5 MB with 10 backups.
- The dashboard requires a password and CSRF protection.

**Deletion is permanent.** Test with Dry Run, inspect the preview and logs, and back up important data before disabling Dry Run. Run the service under a dedicated OS account with write access only to intended cleanup targets.

## Project Structure

```text
file-retention-manager/
├── data/               # SQLite database directory (git-ignored)
├── logs/               # Application & audit logs (git-ignored)
├── static/             # Frontend assets (CSS/JS)
├── templates/          # Jinja2 dashboard templates
├── .env.example        # Environment variable template
├── .gitignore          # Version control ignore patterns
├── app.py              # Flask web dashboard
├── worker.py           # APScheduler background worker
├── requirements.txt    # Python dependencies
└── README.md           # Documentation
```

## Quick start

Python 3.11+ is recommended.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Export environment variables from `.env` (or use a process manager that loads it). Set a unique `SECRET_KEY` and strong `ADMIN_PASSWORD` before running.

```bash
export $(grep -v '^#' .env | xargs)
python app.py
```

Open http://127.0.0.1:5000. In another terminal, start the worker:

```bash
export $(grep -v '^#' .env | xargs)
python worker.py
```

The dashboard and worker share the SQLite database. Dashboard Start/Stop controls update the persistent worker setting; the worker polls it and applies changes. Keep the worker process running as a service for 24/7 operation.

## Linux systemd deployment

Create a dedicated service account and install the project in `/opt/file-retention-manager`. Create `/opt/file-retention-manager/.env` with absolute `DATABASE_PATH` and `LOG_PATH` values, a strong secret, and admin password. Protect it with `chmod 600`.

`/etc/systemd/system/retention-worker.service`:

```ini
[Unit]
Description=File Retention Manager worker
After=network.target

[Service]
Type=simple
User=retention
Group=retention
WorkingDirectory=/opt/file-retention-manager
EnvironmentFile=/opt/file-retention-manager/.env
ExecStart=/opt/file-retention-manager/.venv/bin/python worker.py
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=/opt/file-retention-manager/data /opt/file-retention-manager/logs /srv/archive

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/retention-dashboard.service`:

```ini
[Unit]
Description=File Retention Manager dashboard
After=network.target

[Service]
Type=simple
User=retention
Group=retention
WorkingDirectory=/opt/file-retention-manager
EnvironmentFile=/opt/file-retention-manager/.env
ExecStart=/opt/file-retention-manager/.venv/bin/gunicorn --workers 1 --bind 127.0.0.1:5000 --access-logfile - app:app
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Adjust `ReadWritePaths` and filesystem permissions to match your actual targets. The dashboard can be placed behind an HTTPS reverse proxy. Do not expose the development Flask server directly to the internet.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now retention-worker retention-dashboard
sudo systemctl status retention-worker retention-dashboard
```

Use one worker service instance. Do not run multiple worker processes against the same database and targets.

## Windows service (NSSM)

1. Install Python 3.11+, create a virtual environment, and install `requirements.txt`.
2. Create `.env` with absolute Windows paths, for example `DATABASE_PATH=C:/ProgramData/RetentionManager/retention.db`.
3. Use NSSM to install two services:
   - `RetentionWorker`: Application = `C:\path\to\.venv\Scripts\python.exe`; Arguments = `worker.py`; Startup directory = project directory.
   - `RetentionDashboard`: Application = `C:\path\to\.venv\Scripts\waitress-serve.exe` (install `waitress`); Arguments = `--listen=127.0.0.1:5000 app:app`. Add `waitress>=3,<4` to requirements if using this option.
4. Configure both services to load the same environment variables. Set service recovery to restart on failure.
5. Run services under a dedicated Windows account with access only to intended target directories.

For NSSM, set the application directory and stdout/stderr log destinations in the service I/O tab. Do not run the dashboard or worker as an unrestricted administrator account.

## Configuration

| Setting | Default | Limits |
|---|---:|---:|
| Retention | 4 months | 1–120 |
| Schedule interval | 24 hours | 1–720 |
| Dry Run | On | On/Off |
| Target paths | None | Up to 50 absolute paths |

The schedule interval is measured from the worker's scheduled job start. The first scheduled run occurs after one interval. Use the dashboard's **Run dry-run preview now** button for an immediate scan.

## Operational notes

- The worker heartbeat is updated while the worker is alive. If it becomes stale, inspect the system service status and worker logs.
- Logs are written to `LOG_PATH`; the dashboard displays the latest 200 lines.
- The preview is capped at 500 displayed paths to keep the dashboard responsive. The summary count includes all eligible files.
- The application does not delete empty directories.
- Avoid overlapping target roots; duplicate roots can cause repeated scans.
- SQLite is appropriate for a single host and one worker. For multi-host deployments, use a server database and distributed job coordination.
- This is a strong operational baseline, but validate it against your filesystem, backup policy, security requirements, and change-control process before production deletion.

## Maintainer

- **Khummeung Wattanasaroj** - [khummeung.wattanasaroj@gmail.com](mailto:khummeung.wattanasaroj@gmail.com)
