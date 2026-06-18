"""日志配置"""
import logging
import os

def setup_logging(level: str = "INFO"):
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(os.path.join(log_dir, "trading.log")),
            logging.StreamHandler()
        ]
    )
