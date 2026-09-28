"""Database enforcement of append-only audit events and approval history."""

from alembic import op

revision = "0002_audit_immutability"
down_revision = "2b05da32fd42"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE FUNCTION reject_history_mutation() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'history is append-only';
    END;
    $$ LANGUAGE plpgsql
    """)
    for table in ["audit_events", "approvals", "tool_executions"]:
        op.execute(f"""CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table}
                       FOR EACH ROW EXECUTE FUNCTION reject_history_mutation()""")


def downgrade():
    for table in ["audit_events", "approvals", "tool_executions"]:
        op.execute(f"DROP TRIGGER immutable_history ON {table}")
    op.execute("DROP FUNCTION reject_history_mutation()")
