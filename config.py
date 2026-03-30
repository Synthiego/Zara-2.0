# ─── Anti-Nuke Thresholds ───────────────────────────────────────────
ANTINUKE = {
    "ban_threshold": 3,
    "kick_threshold": 5,
    "channel_delete_threshold": 3,
    "channel_create_threshold": 5,
    "role_delete_threshold": 3,
    "role_create_threshold": 5,
    "webhook_create_threshold": 3,
    "time_window": 10,           # seconds
    "punishment": "ban",         # "ban" | "kick" | "strip_roles"
}

# ─── AI Moderation (Perspective API) ────────────────────────────────
AI_MOD = {
    "toxic_threshold": 0.75,     # 0.0–1.0, higher = less strict
    "nsfw_threshold": 0.80,
    "action": "delete_and_warn", # "delete" | "delete_and_warn" | "timeout"
    "timeout_minutes": 10,
    "log_borderlines": True,     # Log messages that score 0.5+ but below threshold
}

# ─── Spam Detection (local, no API) ─────────────────────────────────
SPAM = {
    "max_messages": 5,
    "per_seconds": 5,
    "duplicate_threshold": 3,
}

# ─── Logging ────────────────────────────────────────────────────────
LOG_CHANNEL_NAME = "mod-logs"
