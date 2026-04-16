from __future__ import annotations

import logging
import time

import requests

from config import load_settings
from heartbeat import send_heartbeat
from job_runner import process_one_job
from monitor import read_device_snapshot


def run() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    logger = logging.getLogger("edge-agent")
    logger.info("Starting edge-agent for device '%s'", settings.device_code)
    logger.info("Backend base URL: %s", settings.backend_base_url)
    logger.info("MOCK_PRINT=%s", settings.mock_print)

    session = requests.Session()
    next_heartbeat_at = 0.0

    while True:
        now = time.monotonic()
        if now >= next_heartbeat_at:
            snapshot = read_device_snapshot(settings)
            try:
                response = send_heartbeat(session, settings, snapshot)
                logger.info(
                    "Heartbeat ok (%s/%s): %s",
                    snapshot.status,
                    snapshot.printer_status,
                    response.get("status"),
                )
            except requests.RequestException as exc:
                logger.warning("Heartbeat failed: %s", exc)
            next_heartbeat_at = now + settings.heartbeat_interval_sec

        try:
            processed = process_one_job(session, settings)
        except requests.RequestException as exc:
            logger.warning("Job polling failed: %s", exc)
            processed = False

        if not processed:
            time.sleep(settings.poll_interval_sec)


if __name__ == "__main__":
    run()
