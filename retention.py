from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from dateutil.relativedelta import relativedelta

_run_lock = Lock()

@dataclass
class CleanupResult:
    scanned: int = 0
    eligible: int = 0
    deleted: int = 0
    errors: int = 0
    skipped: int = 0
    preview: list = None

    def __post_init__(self):
        if self.preview is None:
            self.preview = []

    def to_dict(self):
        return asdict(self)

def retention_cutoff(months: int, now: datetime | None = None) -> datetime:
    if not 1 <= int(months) <= 120:
        raise ValueError("Retention must be between 1 and 120 months.")
    now = now or datetime.now().astimezone()
    return now - relativedelta(months=int(months))

def run_cleanup(target_paths: list[str], months: int, dry_run: bool,
                logger: logging.Logger, preview_limit: int = 500) -> dict:
    if not _run_lock.acquire(blocking=False):
        return {"busy": True, "scanned": 0, "eligible": 0, "deleted": 0,
                "errors": 0, "skipped": 0, "preview": []}

    result = CleanupResult()
    cutoff = retention_cutoff(months).timestamp()
    try:
        for raw_root in target_paths:
            try:
                root = Path(raw_root).expanduser().resolve(strict=True)
                if not root.is_dir():
                    logger.warning("Skipping target; not a directory: %s", root)
                    result.errors += 1
                    continue
            except (OSError, RuntimeError) as exc:
                logger.error("Cannot access target %r: %s", raw_root, exc)
                result.errors += 1
                continue

            logger.info("Scanning target: %s", root)
            # followlinks=False prevents traversal through directory symlinks.
            for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(current) / d).is_symlink()]
                for name in names:
                    path = Path(current) / name
                    try:
                        # Never delete symlinks, sockets, devices, or directories.
                        info = path.lstat()
                        if not stat.S_ISREG(info.st_mode):
                            result.skipped += 1
                            continue
                        result.scanned += 1
                        if info.st_mtime >= cutoff:
                            continue

                        result.eligible += 1
                        item = {
                            "path": str(path),
                            "modified": datetime.fromtimestamp(
                                info.st_mtime, tz=timezone.utc
                            ).astimezone().isoformat(timespec="seconds"),
                            "size_bytes": info.st_size,
                        }
                        if len(result.preview) < preview_limit:
                            result.preview.append(item)

                        if dry_run:
                            logger.info("[DRY RUN] Would delete: %s", path)
                            continue

                        # Re-check immediately before unlinking to avoid following
                        # a file replaced by a symlink between scan and deletion.
                        current_info = path.lstat()
                        if not stat.S_ISREG(current_info.st_mode):
                            result.skipped += 1
                            continue
                        if current_info.st_mtime >= cutoff:
                            result.skipped += 1
                            continue
                        path.unlink()
                        result.deleted += 1
                        logger.info("Deleted: %s", path)

                    except FileNotFoundError:
                        result.skipped += 1
                        logger.info("Skipped; file disappeared: %s", path)
                    except PermissionError as exc:
                        result.errors += 1
                        logger.warning("Permission denied: %s (%s)", path, exc)
                    except OSError as exc:
                        result.errors += 1
                        logger.warning("Could not process %s: %s", path, exc)

        logger.info(
            "Cleanup finished: scanned=%d eligible=%d deleted=%d errors=%d skipped=%d dry_run=%s",
            result.scanned, result.eligible, result.deleted, result.errors,
            result.skipped, dry_run
        )
        data = result.to_dict()
        data.update({"busy": False, "dry_run": dry_run})
        return data
    finally:
        _run_lock.release()
