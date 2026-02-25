import logging
import os

def setup_logger(node_type, port):
    logger = logging.getLogger(f"{node_type}_{port}")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Prevent duplicate logs

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    file_path = os.path.join(os.getcwd(), "outputfile.txt")

    file_handler = logging.FileHandler(file_path, mode="a")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger