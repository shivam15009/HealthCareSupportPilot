
import json
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import database


HEALTH_URL = "http://127.0.0.1:5000/api/health"
CHECK_INTERVAL_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 5


def record_health_check():
    started = time.perf_counter()
    status_code = None
    error_message = None
    is_healthy = False

    try:
        request = Request(
            HEALTH_URL,
            headers={"Accept": "application/json"},
            method="GET",
        )

        with urlopen(
            request,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            status_code = response.status
            payload = json.loads(
                response.read().decode("utf-8")
            )

            is_healthy = (
                status_code == 200
                and payload.get("status") == "healthy"
            )

            if not is_healthy:
                error_message = (
                    "Unexpected health response: "
                    f"status={status_code}, "
                    f"body_status={payload.get('status')!r}"
                )

    except HTTPError as exc:
        status_code = exc.code
        error_message = f"HTTP {exc.code}"

    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"

    response_time_ms = round(
        (time.perf_counter() - started) * 1000,
        2,
    )
    checked_at = datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )

    with database.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_health_checks (
                checked_at,
                is_healthy,
                response_time_ms,
                status_code,
                error_message
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                checked_at,
                int(is_healthy),
                response_time_ms,
                status_code,
                error_message,
            ),
        )

    print(
        f"{checked_at} | "
        f"{'HEALTHY' if is_healthy else 'UNAVAILABLE'} | "
        f"{response_time_ms:.2f} ms"
        + (f" | {error_message}" if error_message else ""),
        flush=True,
    )


def main():
    database.init_db()

    print(f"Monitoring: {HEALTH_URL}")
    print(
        f"Check interval: {CHECK_INTERVAL_SECONDS} seconds. "
        "Press Ctrl+C to stop."
    )

    try:
        while True:
            record_health_check()
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nUptime monitoring stopped.")


if __name__ == "__main__":
    main()
