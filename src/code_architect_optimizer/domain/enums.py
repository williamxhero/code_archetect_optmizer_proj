"""Domain enums (Phase 0)."""

from enum import Enum


class FileCategory(str, Enum):
    PRODUCTION = "production"
    TEST = "test"
    GENERATED = "generated"
    VENDOR = "vendor"
    CONFIG = "config"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class CiMode(str, Enum):
    REPORT = "report"
    RATCHET = "ratchet"
    STRICT = "strict"
