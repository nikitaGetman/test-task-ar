from loguru import logger as loguru_logger
import sys

DEFAULT_CONSOLE_FORMATTER = "<g><n>{time:YYYY-MM-DD HH:mm:ss.SSSSSS!UTC}</></> <lvl>[{level:7}] {extra[service]}[{extra[prefix]}] <i>{thread.name}</> <d><lc>{file}</>:<blue>{line}</></>: <n>{message}</></>"
DEFAULT_FILE_FORMATTER = "{time:YYYY-MM-DD HH:mm:ss.SSSSSS!UTC} [{level:7}] {extra[service]}[{extra[prefix]}] {thread.name} {file}:{line}: {message}"
DEFAULT_DEPTH = 1


class Logger:
    def __init__(
        self,
        service_name: str,
        diagnose=False,
        compression=None,
        rotation="50 Mb",
        retention=None,
        file_log_enabled=True,
        console_log_enabled=True,
        file_log_level="TRACE",
        console_log_level="INFO",
        file_formatter=DEFAULT_FILE_FORMATTER,
        console_formatter=DEFAULT_CONSOLE_FORMATTER,
    ):
        if not service_name:
            raise Exception("'logging_service' should be specified")

        self.logger = loguru_logger.bind(service=service_name, prefix="main")
        self.logger.configure(handlers=[])

        if file_log_enabled:
            self.logger.add(
                sink="logs/" + service_name + "_{time}.log",
                level=file_log_level,
                format=file_formatter,
                diagnose=diagnose,
                backtrace=True,
                catch=True,
                enqueue=True,
                rotation=rotation,
                retention=retention,
                compression=compression,
            )

        if console_log_enabled:
            self.logger.add(
                sink=sys.stdout,
                level=console_log_level,
                format=console_formatter,
                diagnose=diagnose,
                colorize=True,
                backtrace=True,
                catch=True,
                enqueue=True,
            )

        self.logger = LoggerWrapper(self.logger)
        self.logger.info(f"----------------- Starting logger: {service_name} -----------------")

    def __getattr__(self, name):
        return getattr(self.logger, name)


class LoggerWrapper:
    def __init__(self, logger):
        self.logger = logger

    def create_prefix(self, prefix):
        return LoggerWrapper(self.logger.bind(prefix=f"{prefix}"))

    def __getattr__(self, name):
        return getattr(self.logger, name)
