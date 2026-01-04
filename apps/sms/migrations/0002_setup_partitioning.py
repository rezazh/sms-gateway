
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('sms', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL("DROP TABLE IF EXISTS sms_messages CASCADE;"),

        migrations.RunSQL("""
                          CREATE TABLE sms_messages
                          (
                              id            UUID                     NOT NULL,
                              recipient     VARCHAR(15)              NOT NULL,
                              message       TEXT                     NOT NULL,
                              status        VARCHAR(20)              NOT NULL,
                              priority      VARCHAR(10)              NOT NULL,
                              cost          NUMERIC(10, 2)           NOT NULL,
                              scheduled_at  TIMESTAMP WITH TIME ZONE NULL,
                              sent_at       TIMESTAMP WITH TIME ZONE NULL,
                              failed_reason TEXT                     NOT NULL DEFAULT '',
                              retry_count   INTEGER                  NOT NULL DEFAULT 0,
                              created_at    TIMESTAMP WITH TIME ZONE NOT NULL,
                              updated_at    TIMESTAMP WITH TIME ZONE NOT NULL,
                              user_id       BIGINT                   NOT NULL,

                              CONSTRAINT sms_messages_pkey PRIMARY KEY (id, created_at),
                              CONSTRAINT sms_messages_user_id_fk FOREIGN KEY (user_id) REFERENCES users (id) DEFERRABLE INITIALLY DEFERRED
                          ) PARTITION BY RANGE (created_at);
                          """),

        migrations.RunSQL("""
                          CREATE INDEX sms_message_user_id_idx ON sms_messages (user_id, id DESC);
                          CREATE INDEX sms_pending_schedule_idx ON sms_messages (scheduled_at) WHERE status = 'queued';
                          """),

        migrations.RunSQL("""
                          CREATE TABLE sms_messages_y2025 PARTITION OF sms_messages
                              FOR VALUES FROM
                          (
                              '2025-01-01 00:00:00+00'
                          ) TO
                          (
                              '2026-01-01 00:00:00+00'
                          );
                          """),

        migrations.RunSQL("""
                          CREATE TABLE sms_messages_y2026 PARTITION OF sms_messages
                              FOR VALUES FROM
                          (
                              '2026-01-01 00:00:00+00'
                          ) TO
                          (
                              '2027-01-01 00:00:00+00'
                          );
                          """),
    ]