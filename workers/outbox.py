import logging
import os

from packages.core.pipeline.outbox import OutboxPublisher


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    OutboxPublisher().run_forever()


if __name__ == "__main__":
    main()
