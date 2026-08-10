"""Index the lookups every page in the app performs.

BASE-CONFIG-15 / BASE-CONFIG-14 from the pre-deployment audit.

Postgres indexes a foreign key's *target* (the primary key it references),
never the referencing column — a common and expensive surprise. Two
lookups were running as sequential scans:

* ``slots.event_id`` — every event page loads its slots by event id.
* ``signups.slot_id`` (+ ``status``) — every roster, every capacity check,
  every waitlist promotion. The composite covers the FK lookup and the
  status filter in one index.

The shift-based equivalent, ``shift_signups (shift_id, status)``, already
exists — 0037 creates it — and is deliberately not repeated here. Creating it
again with IF NOT EXISTS was harmless on the way up and actively wrong on the
way down: this migration's downgrade dropped an index that 0037's downgrade
then tried to drop again, breaking every migration round-trip test.

Plus the pgvector HNSW index on ``corpus_chunks.embedding``. Without it
every copilot retrieval is an exact scan over the whole corpus, which is
correct and slow, and gets slower with each ingestion run.

All three use IF NOT EXISTS because a database whose indexes were created by
hand during development must not fail the upgrade.

A note on HNSW: building it on an empty table is legal and useless — the
index is populated as rows arrive, so if this migration runs before the
corpus is ingested the index is still correct, just built incrementally.
Non-concurrent creation is deliberate; the tables are small today, and
CONCURRENTLY cannot run inside alembic's transaction.
"""

from alembic import op

revision = "0039_add_missing_hot_path_indexes"
down_revision = "0038_seed_scitrek_modules"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_slots_event_id ON slots (event_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signups_slot_id_status "
        "ON signups (slot_id, status)"
    )
    # Guarded: the corpus tables only exist where the copilot migrations ran,
    # and the operator class only exists where the pgvector extension did.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'corpus_chunks'
            ) AND EXISTS (
                SELECT 1 FROM pg_opclass WHERE opcname = 'vector_cosine_ops'
            ) THEN
                CREATE INDEX IF NOT EXISTS ix_corpus_chunks_embedding_hnsw
                    ON corpus_chunks
                    USING hnsw (embedding vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64);
            END IF;
        END $$;
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_corpus_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_signups_slot_id_status")
    op.execute("DROP INDEX IF EXISTS ix_slots_event_id")
