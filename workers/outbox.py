import logging
import os

from packages.core.pipeline.outbox import OutboxPublisher
from packages.core.observability import WorkerHeartbeat, configure_loki_logging


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    configure_loki_logging("worker-outbox")
    WorkerHeartbeat("outbox").start()
    try:
        OutboxPublisher().run_forever()
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Outbox Worker shutdown requested")


if __name__ == "__main__":
    main()
