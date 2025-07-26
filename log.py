import logging
import colorlog


class CustomColoredFormatter(colorlog.ColoredFormatter):
    def format(self, record):
        # Nếu là INFO thì xóa levelname
        if record.levelno == logging.INFO:
            record.levelname = ''
        else:
            record.levelname = record.levelname
        return super().format(record)


logger = None

def setup_logging():
    global logger
    logger = logging.getLogger("my_logger")
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    # Sử dụng custom formatter
    console_formatter = CustomColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s%(message)s",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        },
        datefmt='%H:%M:%S'
    )

    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s%(message)s',
        datefmt='%H:%M:%S'
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    file_handler = logging.FileHandler('amazon_reg_tool.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

# Setup logging
setup_logging()