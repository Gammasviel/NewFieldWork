import logging, datetime
from pathlib import Path

log_file: Path

class CustomFormatter(logging.Formatter):
    def formatTime(self, record, datefmt = None):
        ct = datetime.datetime.fromtimestamp(record.created)
        if datefmt:
            return ct.strftime(datefmt)
        else:
            return super().formatTime(record, datefmt)

def register_log_file(path: str = 'logs'):
    global log_file
    path_ = Path(path)
    path_.mkdir(parents=True, exist_ok=True)
    log_file = path_ / datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S-%f.log')

def get_module_logger(name: str, log_level: int = 10) -> logging.Logger:
    
    file_handler = logging.FileHandler(
        filename=log_file,
        mode='a',
        encoding='utf-8'
    )
    
    # stream_handler = logging.StreamHandler()
    
    formatter = CustomFormatter(
        "%(levelname)s - %(name)s - %(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S.%f"
    )
    
    file_handler.setFormatter(formatter)
    # stream_handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    logger.addHandler(file_handler)
    # logger.addHandler(stream_handler)
    
    return logger

register_log_file()