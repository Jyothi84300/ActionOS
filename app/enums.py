import enum


class GoalStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionState(str, enum.Enum):
    PENDING = "PENDING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"


class VerificationResult(str, enum.Enum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class SkillStatus(str, enum.Enum):
    ENABLED = "enabled"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class SkillCapability(str, enum.Enum):
    LOCAL = "local"
    ONLINE = "online"
    BOTH = "both"


class ToolCapability(str, enum.Enum):
    LOCAL = "local"
    ONLINE = "online"


class PermissionLevel(str, enum.Enum):
    AUTOMATIC = "AUTOMATIC"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"


class MemoryType(str, enum.Enum):
    DECISION = "decision"
    APPROVAL = "approval"
    DEADLINE = "deadline"
    HISTORY_ENTRY = "history_entry"


class SourceType(str, enum.Enum):
    DOCUMENT = "document"
    CALENDAR = "calendar"
    TASK = "task"
    EMAIL = "email"
    WEB = "web"


class TrustLevel(str, enum.Enum):
    UNTRUSTED = "untrusted"


class CapabilityRoute(str, enum.Enum):
    LOCAL = "local"
    ONLINE = "online"
    PARTIAL = "partial"
