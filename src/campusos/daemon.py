"""
campusos/daemon.py – scheduler loop.

Responsibilities
----------------
* Loads .env at startup (keys already in the environment are never overridden).
* Calls ``runner.execute_run()`` on the configured interval.
* Writes the heartbeat row in ``daemon_status`` every 5 s while sleeping.
* Polls ``settings.run_requested`` every heartbeat tick; fires immediately when set.
* Exits cleanly on SIGINT / SIGTERM, when ``kill_switch`` is set in the DB,
  or when the KILL_FILE path exists on disk.
* Never writes run data directly – that is the runner's job.

Usage
-----
    python -m campusos.daemon            # live mode
    python -m campusos.daemon --mock     # mock mode (no network)
    python -m campusos.daemon --once     # run once then exit
    python -m campusos.daemon --demo     # 60-second interval, mock mode

Environment (set in shell or .env)
-----------------------------------
    CAMPUSOS_DB    path to database (default: data/campusos.db)
    CAMPUSOS_MODE  live | mock | replay  (--mock flag overrides)
    KILL_FILE      path to kill sentinel file (default: data/KILL)
"""

import argparse
import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .db import _REPO_ROOT, connect, init_db, now_iso, resolve_path
from .env import load_env
from .runner import _mark_stale_runs_failed, execute_run

log = logging.getLogger("campusos.daemon")

_HEARTBEAT_INTERVAL = 5   # seconds between heartbeat writes while sleeping
_STOP = False             # set to True by signal handler


def _kill_file_exists() -> bool:
    """Return True if the KILL_FILE sentinel is present on disk."""
    kill_path = os.environ.get("KILL_FILE", "data/KILL")
    return resolve_path(kill_path).exists()


def _handle_signal(signum, _frame):
    global _STOP
    log.warning("received signal %d – shutting down after current run", signum)
    _STOP = True


_now_iso = now_iso


def _get_interval(conn) -> int:
    row = conn.execute("SELECT value FROM settings WHERE key='interval_s'").fetchone()
    return int(row[0]) if row else 3600


def _run_requested(conn) -> bool:
    """Return True if settings.run_requested == 'true'."""
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='run_requested'"
        ).fetchone()
        return bool(row and row[0].lower() == "true")
    except Exception:
        return False


def _heartbeat_worker(
    db_path: str | Path | None,
    pid: int,
    stop_event: threading.Event,
    next_run_holder: list,
) -> None:
    """Background worker updating heartbeat every _HEARTBEAT_INTERVAL continuously."""
    conn = None
    try:
        conn = connect(db_path)
        while not stop_event.is_set():
            try:
                now = _now_iso()
                next_iso = next_run_holder[0]
                with conn:
                    conn.execute(
                        """UPDATE daemon_status
                           SET pid=?, heartbeat_at=?, next_run_at=?
                           WHERE id=1""",
                        (pid, now, next_iso),
                    )
            except Exception as exc:
                log.debug("heartbeat worker write error: %s", exc)
            stop_event.wait(_HEARTBEAT_INTERVAL)
    except Exception as exc:
        log.warning("heartbeat worker stopped unexpectedly: %s", exc)
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _write_heartbeat(conn, pid: int, next_run_at: str | None = None) -> None:
    now = _now_iso()
    try:
        with conn:
            conn.execute(
                """UPDATE daemon_status
                   SET pid=?, heartbeat_at=?, next_run_at=?
                   WHERE id=1""",
                (pid, now, next_run_at),
            )
    except Exception as exc:
        log.warning("heartbeat write failed: %s", exc)


def _mark_started(conn, pid: int) -> None:
    now = _now_iso()
    with conn:
        conn.execute(
            """UPDATE daemon_status
               SET pid=?, started_at=?, heartbeat_at=?
               WHERE id=1""",
            (pid, now, now),
        )


def run_daemon(
    db_path: str | Path | None = None,
    mode: str = "live",
    run_once: bool = False,
    demo: bool = False,
    replay_run: int | None = None,
    replay_run_id: int | None = None,
) -> None:
    """
    Main daemon loop.

    Parameters
    ----------
    db_path:
        Path to the SQLite database.
    mode:
        ``'live'``, ``'mock'``, or ``'replay'``.
    run_once:
        If True, execute one run then return (useful for cron / testing).
    demo:
        If True, force mock mode and 60-second interval (shows the loop fast).
    replay_run:
        If set, run in replay mode using raw payloads from this run ID.
    """
    # Load .env first so CAMPUSOS_DB, CAMPUSOS_MODE etc. are available
    loaded = load_env()
    if loaded:
        log.info("loaded .env keys: %s", list(loaded.keys()))

    effective_replay_run = replay_run if replay_run is not None else replay_run_id
    if effective_replay_run is not None:
        mode = "replay"
        run_once = True

    # --demo forces mock + fast interval
    if demo:
        mode = "mock"
        log.info("--demo mode: mock + 60-second interval")

    # CLI --mock flag takes priority; fall back to CAMPUSOS_MODE env var
    if mode == "live":
        mode = os.environ.get("CAMPUSOS_MODE", "live")

    if db_path is None:
        if mode == "mock" and "CAMPUSOS_DB" not in os.environ:
            db_path = "data/mock.db"

    pid = os.getpid()
    resolved_db = str(resolve_path(db_path or os.environ.get("CAMPUSOS_DB") or "data/campusos.db"))
    log.info("daemon starting  pid=%d  db=%s  mode=%s", pid, resolved_db, mode)

    # Boot: init DB, mark stale runs from crashes, write started_at
    conn = connect(db_path)
    init_db(conn)
    _mark_stale_runs_failed(conn)
    _mark_started(conn, pid)
    conn.close()

    # Start continuous background heartbeat thread (active during runs and sleep)
    stop_event = threading.Event()
    next_run_holder = [None]
    hb_thread = threading.Thread(
        target=_heartbeat_worker,
        args=(db_path, pid, stop_event, next_run_holder),
        daemon=True,
    )
    hb_thread.start()

    try:
        while not _STOP:
            # Check kill file before each run (DB kill_switch is checked inside runner)
            if _kill_file_exists():
                log.warning("KILL_FILE detected – exiting")
                break

            # ── Run ──────────────────────────────────────────────────────────────
            next_run_holder[0] = None
            log.info("starting run  mode=%s", mode)
            result = execute_run(
                db_path=db_path,
                trigger="scheduler",
                mode=mode,
                replay_run=effective_replay_run,
            )
            log.info(
                "run %d finished  state=%s  sources=%d  new=%d  changed=%d  errors=%d",
                result.run_id, result.state,
                result.sources_checked, result.listings_new,
                result.listings_changed, len(result.errors),
            )
            if result.errors:
                for err in result.errors:
                    log.warning("  error: %s", err)

            if run_once or _STOP:
                break

            # ── Sleep with heartbeat + run_requested polling ──────────────────────
            hb_conn = connect(db_path)
            interval = 60 if demo else _get_interval(hb_conn)
            wake_at = time.monotonic() + interval
            next_iso = datetime.fromtimestamp(
                time.time() + interval, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            next_run_holder[0] = next_iso
            log.info("sleeping %d s until %s", interval, next_iso)

            while time.monotonic() < wake_at and not _STOP:
                # Check for a manual run request every tick
                if _run_requested(hb_conn):
                    log.info("run_requested flag detected – triggering manual run")
                    next_run_holder[0] = None
                    execute_run(
                        db_path=db_path,
                        trigger="manual",
                        mode=mode,
                        replay_run=effective_replay_run,
                    )
                    # Reset wake-at so we sleep the full interval again after the manual run
                    wake_at = time.monotonic() + interval
                    next_iso = datetime.fromtimestamp(
                        time.time() + interval, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                    next_run_holder[0] = next_iso

                time.sleep(min(_HEARTBEAT_INTERVAL, max(0, wake_at - time.monotonic())))

            hb_conn.close()
    finally:
        stop_event.set()
        hb_thread.join(timeout=1.0)

    log.info("daemon exiting  pid=%d", pid)


# ---------------------------------------------------------------------------
# Entry point:  python -m campusos.daemon
# ---------------------------------------------------------------------------

def main() -> None:
    # Register signal handlers inside main() so they don't fire on import
    signal.signal(signal.SIGINT,  _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="CampusOS daemon")
    parser.add_argument("--mock",       action="store_true", help="mock mode (no network calls)")
    parser.add_argument("--once",       action="store_true", help="run once then exit")
    parser.add_argument("--demo",       action="store_true", help="mock mode with 60-second interval")
    parser.add_argument("--db",         default=None,        help="path to SQLite database")
    parser.add_argument("--replay",     type=int, default=None, help="run ID to replay payloads from (implies mode 'replay' and --once)")
    parser.add_argument("--replay-run", type=int, default=None, help="alias for --replay")
    args = parser.parse_args()

    replay = args.replay if args.replay is not None else args.replay_run
    mode = "mock" if (args.mock or args.demo) else "live"
    run_once = args.once
    if replay is not None:
        mode = "replay"
        run_once = True

    run_daemon(
        db_path=args.db,
        mode=mode,
        run_once=run_once,
        demo=args.demo,
        replay_run=replay,
    )


if __name__ == "__main__":
    main()
