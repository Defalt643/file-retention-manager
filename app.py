from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from logging_setup import configure_logging
from retention import run_cleanup
from storage import init_db, get_settings, save_settings, get_worker_state, update_worker_state

csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    csrf.init_app(app)

    db_path = app.config["DATABASE_PATH"]
    init_db(db_path)
    logger = configure_logging(app.config["LOG_PATH"])
    app.extensions["retention_logger"] = logger

    # Password is configured via environment. Hash it once for comparison.
    admin_password = app.config["ADMIN_PASSWORD"]
    password_hash = generate_password_hash(admin_password) if admin_password else None

    @app.before_request
    def require_login():
        if request.endpoint in ("login", "static", "health") or session.get("authenticated"):
            return None
        return redirect(url_for("login", next=request.path))

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if not password_hash:
                flash("ADMIN_PASSWORD is not configured. Set it in the environment first.", "error")
            elif check_password_hash(password_hash, request.form.get("password", "")):
                session.clear()
                session["authenticated"] = True
                session.permanent = True
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid password.", "error")
        return render_template("login.html")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def dashboard():
        settings = get_settings(db_path)
        state = get_worker_state(db_path)
        return render_template("index.html", settings=settings, state=state)

    @app.post("/settings")
    def settings():
        try:
            paths = [line.strip() for line in request.form.get("target_paths", "").splitlines() if line.strip()]
            months = int(request.form.get("retention_months", "4"))
            interval = int(request.form.get("interval_hours", "24"))
            if not 1 <= months <= 120:
                raise ValueError("Retention must be between 1 and 120 months.")
            if not 1 <= interval <= 720:
                raise ValueError("Interval must be between 1 and 720 hours.")
            if len(paths) > 50:
                raise ValueError("A maximum of 50 target paths is allowed.")
            normalized = []
            for raw in paths:
                candidate = Path(raw).expanduser()
                if not candidate.is_absolute():
                    raise ValueError(f"Target path must be absolute: {raw}")
                normalized.append(str(candidate))
            current = get_settings(db_path)
            current.update({
                "target_paths": normalized,
                "retention_months": months,
                "interval_hours": interval,
                "dry_run": request.form.get("dry_run") == "on",
            })
            save_settings(db_path, current)
            flash("Settings saved.", "success")
        except (ValueError, OSError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("dashboard"))

    @app.post("/worker/<action>")
    def worker_control(action):
        if action not in ("start", "stop"):
            return "Not found", 404
        settings = get_settings(db_path)
        settings["worker_enabled"] = action == "start"
        save_settings(db_path, settings)
        logger.info("Worker %s requested from dashboard.", action)
        flash(f"Worker {action} requested. The worker service must be running.", "success")
        return redirect(url_for("dashboard"))

    @app.post("/preview")
    def preview():
        settings = get_settings(db_path)
        result = run_cleanup(settings["target_paths"], settings["retention_months"],
                             True, logger)
        return jsonify(result)

    @app.get("/api/status")
    def api_status():
        state = get_worker_state(db_path)
        return jsonify({"settings": get_settings(db_path), "worker": state})

    @app.get("/api/logs")
    def api_logs():
        log_path = Path(app.config["LOG_PATH"])
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
        except FileNotFoundError:
            lines = []
        return jsonify({"lines": lines})

    return app

app = create_app()

if __name__ == "__main__":
    # Development only. Use Gunicorn/systemd or Waitress/NSSM in production.
    app.run(host=os.environ.get("FLASK_HOST", "127.0.0.1"),
            port=int(os.environ.get("FLASK_PORT", "5000")), debug=False)
