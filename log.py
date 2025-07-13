import logging
from logging.handlers import RotatingFileHandler
import colorlog


logger = None
# Thiết lập logging
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Định dạng log với màu sắc cho console
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        },
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Định dạng log cho file
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler với rotation (giới hạn 5MB, giữ 3 file backup)
    file_handler = RotatingFileHandler('amazon_reg_tool.log', maxBytes=5*1024*1024, backupCount=3)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

# Gọi thiết lập logging
setup_logging()