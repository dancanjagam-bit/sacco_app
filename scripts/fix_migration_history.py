"""Deprecated safety stub for a previously proposed migration-row deleter.

Migration recorder rows are historical evidence and must not be deleted to
force an upgrade. Use the additive, schema-checked migration strategy and
verify it on an isolated restored copy. This legacy command is retained so an
old invocation fails safely instead of mutating a database.
"""

raise SystemExit(
    "Refusing to alter django_migrations. Preserve migration history and "
    "follow the verified copy-only procedure in REPAIR_TASKS.md."
)
