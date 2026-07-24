"""Seed the 5 confirmed SciTrek modules; archive stale placeholder templates.

The bulk event builder (in-app replacement for CSV import) is module-first: the
admin picks one of the confirmed modules and adds a row per school/date. Those
modules must exist on handover. The DB previously held 4 generic placeholders
(intro-bio/chem/physics + orientation) from early seed migrations; this replaces
them with the real catalog.

CRISPR 1 & 2 are separate families for now (no shared orientation credit).
All are type=module. Archiving a placeholder only sets deleted_at — existing
events keep their module_slug strings and are untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_seed_scitrek_modules"
down_revision = "0028_add_show_audit_logs_tab"
branch_labels = None
depends_on = None


SEED_MODULES = [
    (
        "crispr-1",
        "CRISPR Module 1 – Gene Editing Basics",
        "Students learn lab skills such as micropipetting and sterile technique, "
        "then perform a CRISPR knockout experiment on the LacZ gene in E. coli. "
        "They analyze bacterial growth and color changes while exploring how CRISPR works.",
    ),
    (
        "crispr-2",
        "CRISPR Module 2 – Mutations & Knockout Strategies",
        "Building on Module 1, students investigate different types of mutations and "
        "compare the effectiveness of various knockout strategies. They evaluate results "
        "and discuss real-world applications and ethics of gene editing.",
    ),
    (
        "glucose-sensing",
        "Glucose Sensing – Enzyme Function & Diagnostics",
        "Students test glucose sensors using enzyme-based reactions, generate calibration "
        "curves, and analyze “mystery patient” samples. They explore how enzyme activity "
        "is influenced by different conditions and connect findings to diabetes management.",
    ),
    (
        "bioinformatics",
        "Bioinformatics – Gene Expression & Cancer",
        "Students use bioinformatics tools to compare gene expression in healthy and "
        "cancerous cells. They identify patterns, form hypotheses, and present findings "
        "on how specific genes may contribute to cancer.",
    ),
    (
        "thermodynamics",
        "Thermodynamics – Heat Transfer & Calorimetry",
        "Students explore how thermal energy moves within systems, apply the heat transfer "
        "equation (q = mCΔT), and investigate how food calorie content relates to stored "
        "chemical energy using chip calorimetry experiments. They design experiments, "
        "analyze data, calculate percent error, and present evidence-based conclusions.",
    ),
]

PLACEHOLDER_SLUGS = ("intro-bio", "intro-chem", "intro-physics", "orientation")

DEFAULT_CAPACITY = 30
DURATION_MINUTES = 90


def upgrade():
    conn = op.get_bind()

    # 1. Seed the 5 confirmed modules (idempotent — skip existing slugs).
    insert_sql = sa.text(
        """
        INSERT INTO module_templates
            (slug, name, description, default_capacity, duration_minutes,
             type, session_count, family_key)
        VALUES
            (:slug, :name, :description, :capacity, :duration,
             'module', 1, :slug)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    for slug, name, description in SEED_MODULES:
        conn.execute(
            insert_sql,
            {
                "slug": slug,
                "name": name,
                "description": description,
                "capacity": DEFAULT_CAPACITY,
                "duration": DURATION_MINUTES,
            },
        )

    # 2. Archive the stale placeholder templates (only if still active).
    conn.execute(
        sa.text(
            """
            UPDATE module_templates
               SET deleted_at = now()
             WHERE slug = ANY(:slugs)
               AND deleted_at IS NULL
            """
        ),
        {"slugs": list(PLACEHOLDER_SLUGS)},
    )


def downgrade():
    conn = op.get_bind()

    # Restore the placeholders.
    conn.execute(
        sa.text(
            """
            UPDATE module_templates
               SET deleted_at = NULL
             WHERE slug = ANY(:slugs)
            """
        ),
        {"slugs": list(PLACEHOLDER_SLUGS)},
    )

    # Remove the seeded modules (events reference module_slug as a plain string,
    # not an FK, so deleting the template rows is safe).
    conn.execute(
        sa.text("DELETE FROM module_templates WHERE slug = ANY(:slugs)"),
        {"slugs": [m[0] for m in SEED_MODULES]},
    )
