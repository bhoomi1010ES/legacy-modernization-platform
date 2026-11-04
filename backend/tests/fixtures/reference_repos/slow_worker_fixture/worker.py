import time
import sys

def execute_long_job(duration_seconds: float = 300.0, check_interval: float = 0.5):
    start = time.time()
    while time.time() - start < duration_seconds:
        time.sleep(check_interval)
    return {"status": "completed", "elapsed": time.time() - start}
