"""
Centralized logging module with type-based coloring.
Outputs to stdout and optionally duplicates to console window.
"""
from enum import Enum
from datetime import datetime
from typing import Optional, Callable, Any
import os
import glob
import threading

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


# Severity ordering (lowest to highest): Debug → Success → Info → Warning → Error
LOG_LEVEL_SEVERITY = {
    LogLevel.DEBUG: 0,
    LogLevel.SUCCESS: 1,
    LogLevel.INFO: 2,
    LogLevel.WARNING: 3,
    LogLevel.ERROR: 4,
}

# Map display names (used in settings dropdowns) to LogLevel
LEVEL_NAME_MAP = {
    "Debug": LogLevel.DEBUG,
    "Success": LogLevel.SUCCESS,
    "Info": LogLevel.INFO,
    "Warning": LogLevel.WARNING,
    "Error": LogLevel.ERROR,
}


class LogColors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    
    # Log level colors
    DEBUG = "\033[90m"      # Gray
    INFO = "\033[96m"       # Cyan
    SUCCESS = "\033[92m"    # Green
    WARNING = "\033[93m"    # Yellow
    ERROR = "\033[91m"      # Red
    
    # Timestamp color
    TIMESTAMP = "\033[90m"  # Gray

    @classmethod
    def get_color(cls, level: LogLevel) -> str:
        return getattr(cls, level.value, cls.RESET)


class Logger:
    """
    Centralized logger with console window integration.
    
    Usage:
        Logger.info("Application started")
        Logger.warning("Something might be wrong")
        Logger.error("An error occurred")
    """
    
    _console_callback: Optional[Callable[[LogLevel, str], None]] = None
    _qt_dispatcher: Any = None
    _show_timestamps: bool = True
    _stdout_enabled: bool = True

    _stdout_level: LogLevel = LogLevel.DEBUG
    _file_level: LogLevel = LogLevel.DEBUG

    _log_file: Optional[str] = None
    _max_file_size: float = 0.0
    _max_files: float = 0.0
    _log_dir: Optional[str] = None
    _file_lock = threading.RLock()
    
    @classmethod
    def set_console_callback(cls, callback: Optional[Callable[[LogLevel, str], None]]):
        """Set the callback for sending logs to console window."""
        cls._console_callback = callback
        cls._qt_dispatcher = None

        if callback is None:
            return

        # If Qt is available and an application exists, route logs through a Qt signal so that
        # UI updates happen on the main thread (avoids intermittent native crashes).
        try:
            from PySide6.QtCore import QObject, Signal, QCoreApplication
        except Exception:
            return

        app = QCoreApplication.instance()
        if app is None:
            return

        class _QtLogDispatcher(QObject):
            log_message = Signal(object, str)

        dispatcher = _QtLogDispatcher()
        try:
            dispatcher.moveToThread(app.thread())
        except Exception:
            pass

        def _deliver(level: object, message: str) -> None:
            try:
                callback(level, message)  # type: ignore[arg-type]
            except Exception:
                # Never crash on logging delivery.
                pass

        dispatcher.log_message.connect(_deliver)
        cls._qt_dispatcher = dispatcher

    @classmethod
    def set_stdout_enabled(cls, enabled: bool):
        """Enable/disable stdout logging."""
        cls._stdout_enabled = bool(enabled)

    @classmethod
    def set_stdout_level(cls, level: LogLevel):
        """Set the minimum severity for stdout output."""
        cls._stdout_level = level

    @classmethod
    def set_file_level(cls, level: LogLevel):
        """Set the minimum severity for file logging."""
        cls._file_level = level

    @classmethod
    def should_log(cls, message_level: LogLevel, threshold: LogLevel) -> bool:
        """Return True if message_level meets or exceeds the threshold severity."""
        return LOG_LEVEL_SEVERITY[message_level] >= LOG_LEVEL_SEVERITY[threshold]

    @classmethod
    def configure_file_logging(cls, enabled: bool, log_dir: str, max_files: int, max_size_val: int, size_unit: str):
        """Configure file logging settings."""
        with cls._file_lock:
            if not enabled:
                cls._log_file = None
                return

            cls._log_dir = log_dir
            cls._max_files = max_files if max_files > 0 else float("inf")

            # Calculate max size in bytes
            multiplier = 1
            if size_unit == "KB":
                multiplier = 1024
            elif size_unit == "MB":
                multiplier = 1024 * 1024
            elif size_unit == "GB":
                multiplier = 1024 * 1024 * 1024

            cls._max_file_size = (
                (max_size_val * multiplier) if max_size_val > 0 else float("inf")
            )

            if not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except OSError:
                    print(f"Failed to create log directory: {log_dir}")
                    return

            # Create new log file for this session
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            cls._log_file = os.path.join(log_dir, f"log_{timestamp}.txt")

            # Cleanup old files
            cls._cleanup_old_files()
        
    @classmethod
    def _cleanup_old_files(cls):
        """Delete oldest files if count exceeds max_files."""
        if not cls._log_dir or cls._max_files == float('inf'):
            return
            
        try:
            current_log = None
            if cls._log_file:
                current_log = os.path.abspath(cls._log_file)

            files = glob.glob(os.path.join(cls._log_dir, "log_*.txt"))
            files = [os.path.abspath(path) for path in files]
            files.sort(key=os.path.getmtime)
            
            while len(files) > cls._max_files:
                oldest = None
                for idx, path in enumerate(files):
                    if current_log and path == current_log:
                        continue
                    oldest = files.pop(idx)
                    break

                if not oldest:
                    break
                try:
                    os.remove(oldest)
                except OSError:
                    pass
        except Exception:
            pass

    @classmethod
    def _trim_file(cls):
        """Remove lines from the beginning of the file until size is under limit."""
        if not cls._log_file:
            return

        max_size = getattr(cls, "_max_file_size", float("inf"))
        if max_size == float("inf"):
            return

        try:
            max_bytes = int(max_size)
        except Exception:
            return

        if max_bytes <= 0:
            return

        tmp_path: str | None = None
        try:
            with cls._file_lock:
                log_file = cls._log_file
                if not log_file or not os.path.exists(log_file):
                    return

                current_size = os.path.getsize(log_file)
                if current_size <= max_bytes:
                    return

                tmp_path = log_file + ".tmp"
                start_offset = max(0, current_size - max_bytes)

                with open(log_file, "rb") as src:
                    if start_offset:
                        src.seek(start_offset)
                    data = src.read()

                # If we started mid-file, align to the next newline to avoid chopping a line in half.
                if start_offset:
                    nl = data.find(b"\n")
                    if nl != -1:
                        data = data[nl + 1 :]

                with open(tmp_path, "wb") as dst:
                    dst.write(data)

                os.replace(tmp_path, log_file)
        except Exception as e:
            print(f"Error trimming log file: {e}")
            if tmp_path:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass

    @classmethod
    def _log_to_file(cls, message: str):
        """Append log message to file and manage size."""
        if not cls._log_file:
            return
            
        try:
            # We do NOT put ANSI codes in log file, they don't render well (at all)

            with cls._file_lock:
                created_new_file = not os.path.exists(cls._log_file)

                with open(cls._log_file, "a", encoding="utf-8") as f:
                    f.write(message + "\n")

                if created_new_file:
                    cls._cleanup_old_files()

                # Check size
                if cls._max_file_size != float("inf"):
                    if os.path.getsize(cls._log_file) > cls._max_file_size:
                        cls._trim_file()
                    
        except Exception:
            # Don't crash app on logging failure
            pass

    @classmethod
    def _format_message(cls, level: LogLevel, message: str, include_ansi: bool = True) -> str:
        """Format a log message with optional ANSI colors."""
        timestamp = ""
        if cls._show_timestamps:
            now = datetime.now().strftime("%H:%M:%S")
            if include_ansi:
                timestamp = f"{LogColors.TIMESTAMP}[{now}]{LogColors.RESET} "
            else:
                timestamp = f"[{now}] "
        
        level_str = f"[{level.value}]"
        
        if include_ansi:
            color = LogColors.get_color(level)
            return f"{timestamp}{color}{level_str}{LogColors.RESET} {message}"
        else:
            return f"{timestamp}{level_str} {message}"
    
    @classmethod
    def _log(cls, level: LogLevel, message: str):
        """Internal logging method."""
        # Print to stdout with ANSI colors (if enabled and level meets threshold)
        if cls._stdout_enabled and cls.should_log(level, cls._stdout_level):
            formatted_stdout = cls._format_message(level, message, include_ansi=True)
            print(formatted_stdout)

        # Console callback (filtering for console window / mini-console
        # happens at the UI layer, so always forward here)
        need_callback = cls._console_callback is not None
        need_file = cls._log_file and cls.should_log(level, cls._file_level)

        if need_callback or need_file:
            formatted_clean = cls._format_message(level, message, include_ansi=False)

            if need_callback:
                if cls._qt_dispatcher is not None:
                    try:
                        cls._qt_dispatcher.log_message.emit(level, formatted_clean)
                    except Exception:
                        cls._console_callback(level, formatted_clean)
                else:
                    cls._console_callback(level, formatted_clean)

            if need_file:
                cls._log_to_file(formatted_clean)
    
    @classmethod
    def debug(cls, message: str):
        """Log a debug message."""
        cls._log(LogLevel.DEBUG, message)
    
    @classmethod
    def info(cls, message: str):
        """Log an info message."""
        cls._log(LogLevel.INFO, message)
    
    @classmethod
    def success(cls, message: str):
        """Log a success message."""
        cls._log(LogLevel.SUCCESS, message)
    
    @classmethod
    def warning(cls, message: str):
        """Log a warning message."""
        cls._log(LogLevel.WARNING, message)
    
    @classmethod
    def error(cls, message: str):
        """Log an error message."""
        cls._log(LogLevel.ERROR, message)
