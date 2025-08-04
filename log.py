import logging
import colorlog


logger = None

class CustomFormatter(colorlog.ColoredFormatter):
    def format(self, record):
        # Nếu là MainThread thì để trống threadName
        if record.threadName == "MainThread" or record.threadName == "Dừng":
            record.threadName = ""
        else:
            record.threadName = " - [Tab-" + record.threadName + "]"
        return super().format(record)

# Thiết lập logging
def setup_logging():
    global logger
    logger = logging.getLogger("my_logger")
    logger.setLevel(logging.INFO)

    # Định dạng log với màu sắc cho console

    console_formatter = CustomFormatter(
        "%(log_color)s%(asctime)s%(threadName)s - %(message)s",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        },
        datefmt='%H:%M:%S'
    )

    # Định dạng log cho file
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.terminator = "\n"  # đảm bảo chỉ 1 dòng xuống
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler('amazon_reg_tool.log', encoding='utf-8')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

# Gọi thiết lập logging
setup_logging()