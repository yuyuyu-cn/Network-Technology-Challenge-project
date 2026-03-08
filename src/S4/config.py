MODE = "hard" # 模式选择，“soft”为mode b，其他是mode a
import logging
from enum import Enum
class action(Enum):
    NOP = 1
    ADD = 2
    DEL = 3
    REPLACE = 4

class LogColor:
    """
    根据不同的日志级别，打印不颜色的日志
    info：绿色
    warning：黄色
    error：红色
    debug：灰色
    """
    # logging日志格式设置
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s: %(message)s')

    @staticmethod
    def info(message: str):
    	# info级别的日志，绿色
        logging.info("\033[0;32m" + message + "\033[0m")

    @staticmethod
    def warning(message: str):
    	# warning级别的日志，黄色
        logging.warning("\033[0;33m" + message + "\033[0m")

    @staticmethod
    def error(message: str):
    	# error级别的日志，红色
        logging.error("\033[0;31m"+"-" * 120 + '\n| ' + message + "\033[0m" + "\n" + "└"+"-" * 150)

    @staticmethod
    def debug(message: str):
    	# debug级别的日志，灰色
        logging.debug("\033[0;37m" + message + "\033[0m")