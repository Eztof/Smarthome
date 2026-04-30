# ═══════════════════════════════════════════════════════════
#  core/scheduler.py  –  Hintergrund-Tasks
# ═══════════════════════════════════════════════════════════

from apscheduler.schedulers.background import BackgroundScheduler
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

_scheduler = None


def start():
    global _scheduler
    from modules.weather import fetcher as weather

    _scheduler = BackgroundScheduler(timezone=config.TIMEZONE)

    # Wetter alle X Minuten
    _scheduler.add_job(
        func=weather.fetch_and_store,
        trigger="interval",
        minutes=config.WEATHER_UPDATE_INTERVAL,
        id="weather",
        replace_existing=True,
    )

    _scheduler.start()
    print(f"[Scheduler] Wetter alle {config.WEATHER_UPDATE_INTERVAL} Min.")


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
