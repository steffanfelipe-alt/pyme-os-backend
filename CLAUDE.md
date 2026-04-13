# CLAUDE.md — PyME OS Backend (FastAPI + SQLAlchemy + Alembic)

## Engineering Standards

### Before Any Edit
1. **Read the target file completely** before making any change.
2. **Check all callers** of any function you modify (grep for usages).
3. For model changes: check the service layer AND the migration history.
4. For service changes: check the router AND any direct callers.

### Database Schema Rules (CRITICAL)
- **NEVER add a column to a SQLAlchemy model without a corresponding Alembic migration.**
  DB drift (model has column, DB doesn't) causes every ORM SELECT on that table to fail with a
  database error. This breaks ALL endpoints that read from that table — not just the new feature.
- **ALWAYS verify the current Alembic head before creating a migration.**
  `down_revision` must point to the actual current head. To find it: grep migrations for which
  `revision` has no other file with `down_revision` pointing to it.
- **Migration column types must match the model exactly.**
  `Mapped[float | None]` → `sa.Float(), nullable=True`. `Mapped[dict | None]` → `sa.JSON(), nullable=True`.
- After adding a migration, always verify `alembic upgrade head` will succeed by checking
  the column names match between the migration DDL and the model definition.

### API Design Rules
- **NEVER remove fields from response schemas** — only add new optional fields.
- **NEVER change the type of an existing response field** — this breaks frontend consumers.
- **Prefer structured empty states over HTTP 4xx for "not configured" conditions.**
  Example: if a report requires a config value, return `{"sin_configurar": true, "data": []}` with
  HTTP 200 instead of raising HTTP 400. The frontend can render a helpful empty state.
  Reserve HTTP 4xx for actual errors (bad input, missing required resources, auth failures).

### Code Quality
- Read the schema file before writing a new endpoint — reuse existing Pydantic models.
- Do not add `Optional` fields to existing Pydantic schemas unless the field is truly optional
  and has a sensible default.
- Any new service function must handle the case where the queried object doesn't exist
  (return 404 via HTTPException, not None or AttributeError).

### Alembic Conventions
- Migration file naming: `<8_char_hash>_<snake_case_description>.py`
- Always include a `downgrade()` that reverses the `upgrade()` exactly.
- Never create two migrations with the same `down_revision` unless deliberately creating a branch
  (which requires a subsequent merge migration).
