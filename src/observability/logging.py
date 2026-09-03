import logging
import os
import structlog

def configure_logging():
    """
    Configures structlog across the application.
    Uses JSONRenderer for production (default), or ConsoleRenderer for local development 
    if FCE_LOG_FORMAT is set to 'console'.
    """
    # Check environment variable for log format
    log_format = os.environ.get("FCE_LOG_FORMAT", "json").lower()
    
    # Shared processors for both standard logging and structlog
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    # Configure structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.UnicodeDecoder(),
            # Use appropriate renderer
            structlog.processors.JSONRenderer() if log_format == "json" else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard python logging to also go through structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer() if log_format == "json" else structlog.dev.ConsoleRenderer(),
        ],
    )
    
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    
    # Set default log level (INFO)
    log_level_str = os.environ.get("FCE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_str, logging.INFO)
    root_logger.setLevel(level)

def get_logger(name: str) -> structlog.BoundLogger:
    """Returns a structlog BoundLogger for the given name."""
    return structlog.get_logger(name)
