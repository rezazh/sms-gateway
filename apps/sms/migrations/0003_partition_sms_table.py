from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('sms', '0002_smsmessage_sms_message_user_id_45250c_idx'),
    ]

    operations = [
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS sms_messages CASCADE;",
            reverse_sql=migrations.RunSQL.noop
        ),

        migrations.RunSQL(
            sql="""
                CREATE TABLE sms_messages
                (
                    id            uuid                     NOT NULL,
                    user_id       bigint                   NOT NULL,
                    recipient     varchar(15)              NOT NULL,
                    message       text                     NOT NULL,
                    status        varchar(20)              NOT NULL,
                    priority      varchar(10)              NOT NULL,
                    cost          numeric(10, 2)           NOT NULL,
                    scheduled_at  timestamp with time zone NULL,
                    sent_at       timestamp with time zone NULL,
                    failed_reason text NULL,
                    retry_count   integer                  NOT NULL,
                    created_at    timestamp with time zone NOT NULL,
                    updated_at    timestamp with time zone NOT NULL,
                    PRIMARY KEY (id, created_at)
                ) PARTITION BY RANGE (created_at);
                """,
            reverse_sql="DROP TABLE sms_messages;"
        ),

        migrations.RunSQL(
            sql="""
                CREATE INDEX sms_message_user_id_created_at_idx ON sms_messages (user_id, created_at DESC);
                CREATE INDEX sms_message_recipient_idx ON sms_messages (recipient);
                CREATE INDEX sms_pending_schedule_idx ON sms_messages (scheduled_at) WHERE status = 'queued';
                """,
            reverse_sql=migrations.RunSQL.noop
        ),

        migrations.RunSQL(
            sql="""
                CREATE TABLE sms_messages_default PARTITION OF sms_messages DEFAULT;

                CREATE TABLE sms_messages_2025 PARTITION OF sms_messages
                    FOR VALUES FROM
                (
                    '2025-01-01 00:00:00+00'
                ) TO
                (
                    '2026-01-01 00:00:00+00'
                );

                CREATE TABLE sms_messages_2026 PARTITION OF sms_messages
                    FOR VALUES FROM
                (
                    '2026-01-01 00:00:00+00'
                ) TO
                (
                    '2027-01-01 00:00:00+00'
                );
                """,
            reverse_sql=migrations.RunSQL.noop
        ),
    ]