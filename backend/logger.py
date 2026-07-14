import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger():
    # Ensure logs directory exists at the root of the project
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "backend.log")
    
    # Create logger
    logger = logging.getLogger("fraud_detection_api")
    logger.setLevel(logging.INFO)
    
    # Create rotating file handler (max 5MB per file, keep 3 backups)
    handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    if not logger.handlers:
        logger.addHandler(handler)
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logger()
