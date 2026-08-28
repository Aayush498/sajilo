"""Worker service requests

A verified worker's trade list is frozen. Widening it goes through support,
and this table is that queue.

Revision ID: 0003
Revises: 0002
Created: 2026-08-28 22:05:13.229056+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Autogenerate also proposed dropping the server defaults on users.phone_verified,
# role, status and locale. Those are unrelated to this change and are the
# database-level fallback for rows inserted outside the ORM, so they are left
# alone deliberately.


def upgrade() -> None:
    op.create_table(
        "worker_service_requests",
        sa.Column("worker_profile_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "withdrawn", name="service_request_status"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_worker_service_requests_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            name=op.f("fk_worker_service_requests_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["worker_profile_id"],
            ["worker_profiles.id"],
            name=op.f("fk_worker_service_requests_worker_profile_id_worker_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_service_requests")),
    )
    op.create_index(
        "ix_worker_service_requests_status", "worker_service_requests", ["status"], unique=False
    )
    # Partial: one *pending* request per trade, but a worker may re-apply after
    # a rejection. A plain unique constraint would block that forever.
    op.create_index(
        "uq_worker_service_requests_pending",
        "worker_service_requests",
        ["worker_profile_id", "service_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_worker_service_requests_pending",
        table_name="worker_service_requests",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index("ix_worker_service_requests_status", table_name="worker_service_requests")
    op.drop_table("worker_service_requests")
    # drop_table leaves the enum type behind, which makes upgrade() fail on a
    # re-run with "type already exists".
    sa.Enum(name="service_request_status").drop(op.get_bind(), checkfirst=True)
