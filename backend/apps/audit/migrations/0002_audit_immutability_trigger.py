from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE FUNCTION audit_prevent_mutation()
RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit_auditlog is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_auditlog_immutable ON audit_auditlog;
CREATE TRIGGER audit_auditlog_immutable
BEFORE UPDATE OR DELETE ON audit_auditlog
FOR EACH ROW EXECUTE FUNCTION audit_prevent_mutation();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS audit_auditlog_immutable ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_prevent_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(FORWARD_SQL, REVERSE_SQL),
    ]
