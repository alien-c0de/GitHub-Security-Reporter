"""
Logging configuration with colors
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config.settings import settings

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    # Fallback if colorama not installed
    class Fore:
        RED = ''
        YELLOW = ''
        GREEN = ''
        CYAN = ''
        BLUE = ''
        MAGENTA = ''
        WHITE = ''
    
    class Style:
        RESET_ALL = ''
        BRIGHT = ''

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors and custom color tags"""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
    }
    
    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if COLORAMA_AVAILABLE and levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{Style.RESET_ALL}"
        
        # Format the message
        message = super().format(record)
        
        if COLORAMA_AVAILABLE:
            # Import color tags utility
            try:
                from src.utils.color_tags import ColorTags
                # Apply custom color tags like [blue]text[/blue]
                message = ColorTags.apply_colors(message)
            except ImportError:
                pass  # color_tags not available, skip
            
            # Color [OK], [ERROR], [WARNING] tags
            message = message.replace('[OK]', f'{Fore.GREEN}[OK]{Style.RESET_ALL}')
            message = message.replace('[ERROR]', f'{Fore.RED}[ERROR]{Style.RESET_ALL}')
            message = message.replace('[WARNING]', f'{Fore.YELLOW}[WARNING]{Style.RESET_ALL}')
            
            # Color additional status indicators
            message = message.replace('[+]', f'{Fore.CYAN}[+]{Style.RESET_ALL}')
            message = message.replace('[✓]', f'{Fore.GREEN}[✓]{Style.RESET_ALL}')
            message = message.replace('[✗]', f'{Fore.RED}[✗]{Style.RESET_ALL}')
            message = message.replace('[-]', f'{Fore.YELLOW}[-]{Style.RESET_ALL}')
        
        return message

def setup_logger(name: str = None, log_file: Path = None, level: str = None) -> logging.Logger:
    """
    Set up logger with console and file handlers
    
    Args:
        name: Logger name (defaults to root)
        log_file: Log file path (defaults to settings)
        level: Log level (defaults to settings)
        
    Returns:
        Configured logger
    """
    if name is None:
        logger = logging.getLogger()
    else:
        logger = logging.getLogger(name)
    
    if level is None:
        level = settings.log_level
    
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # ========================================================================
    # REDUCE PYGITHUB AND URLLIB3 VERBOSITY
    # Add these lines to suppress noisy request/response logs
    # ========================================================================
    logging.getLogger("github").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
    # ========================================================================
    
    # Simple format for console (more readable)
    console_format = '%(message)s'
    
    # Detailed format for file (without color tags)
    file_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = ColoredFormatter(console_format)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler without colors (strip color tags)
    if log_file is None:
        log_file = settings.log_file
    
    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    # Plain formatter for file (removes color codes)
    class PlainFormatter(logging.Formatter):
        def format(self, record):
            # Remove color tags for file output
            import re
            message = super().format(record)
            # Remove [color]text[/color] tags
            message = re.sub(r'\[/?[a-z_]+\]', '', message)
            return message
    
    file_formatter = PlainFormatter(file_format, datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_footer(logger: logging.Logger = None) -> None:
    """
    Print the standardised tool footer at the end of every report run.

    All three values — developer name, version, and copyright year — are read
    from the .env file via settings so they only need to be changed in one place:

        DEVELOPED_BY   = Santosh Susveerkar
        TOOL_VERSION   = 2.0.0
        COPYRIGHT_YEAR = 2026

    Args:
        logger: Logger instance to use. Defaults to the root logger so the
                function works whether called with or without an explicit logger.
    """
    from datetime import datetime

    if logger is None:
        logger = logging.getLogger()

    developer  = settings.developed_by   or 'Security Engineering Team'
    version    = settings.tool_version   or '1.0.0'
    year       = settings.copyright_year or str(datetime.now().year)

    logger.info("[bright_yellow]" + "-" * 100 + "[/bright_yellow]")
    logger.info(
        f"[bright_cyan]📢 Developed by: {developer}   "
        f"Ver: {version}   © {year}[/bright_cyan]"
    )
    logger.info("[bright_yellow]" + "-" * 100 + "[/bright_yellow]")
    logger.info("")