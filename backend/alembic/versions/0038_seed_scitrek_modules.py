"""Seed the real SciTrek module catalog.

Salvaged from PR #50 (the in-app bulk event builder, otherwise dropped — the
feature is not wanted). The seed itself is still needed: nothing else in the
migration chain creates a module, so a fresh production database comes up with
an empty catalog, and an event cannot be created without a module to hang it
on. These nine are the modules SciTrek actually runs, transcribed from the
working dev database rather than from the PR, which had gone stale in four
ways: it wrote to ``module_templates`` (renamed to ``modules`` in 0032), set a
``type`` column (dropped in PR #51), used provisional slugs, and split the two
CRISPR modules into separate orientation families when in practice they share
one — a volunteer oriented for CRISPR 1 is oriented for CRISPR 2.

Idempotent: ON CONFLICT DO NOTHING, so running this against a database whose
catalog was built by hand changes nothing. The PR also archived the old
intro-bio / intro-chem / intro-physics / orientation placeholders; that is not
repeated here because migration 0012 already did it.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0038_seed_scitrek_modules"
down_revision = "0037_add_shifts"
branch_labels = None
depends_on = None


SEED_MODULES = [
    {
        "slug": "best-bread",
        "name": "Best Bread",
        "description": "An exploration of the biochemistry of aerobic respiration through "
        "experiments with yeast. Results from variable manipulation are "
        "followed by an engineering activity where students try to get their "
        "yeast to make the most CO2, or the best bread.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "best-bread",
        "materials": ["yeast", "respiration", "engineering challenge"],
        "metadata": {
            "grades": ["7", "8"],
            "school_year": "2026-2027",
            "school_level": "middle",
        },
    },
    {
        "slug": "bioinformatics-gene-expression-cancer",
        "name": "Bioinformatics - Gene Expression & Cancer",
        "description": "Students use bioinformatics tools to compare gene expression in "
        "healthy and cancerous cells. They identify patterns, form "
        "hypotheses, and present findings on how specific genes may "
        "contribute to cancer.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "bioinformatics-gene-expression-cancer",
        "materials": ["bioinformatics tools", "gene expression", "cancer data"],
        "metadata": {
            "grades": ["9", "12"],
            "school_year": "2026-2027",
            "school_level": "high",
        },
    },
    {
        "slug": "conservation-of-mass",
        "name": "Conservation of Mass",
        "description": "A fun look at what happens to materials when they undergo physical "
        "and chemical transformations. The module culminates with an "
        "engineering challenge where students create a solution to a "
        "real-world problem.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "conservation-of-mass",
        "materials": [
            "physical transformations",
            "chemical transformations",
            "engineering challenge",
        ],
        "metadata": {
            "grades": ["7", "8"],
            "school_year": "2026-2027",
            "school_level": "middle",
        },
    },
    {
        "slug": "crispr-gene-editing-basics",
        "name": "CRISPR Module 1 - Gene Editing Basics",
        "description": "Students learn lab skills such as micropipetting and sterile "
        "technique, then perform a CRISPR knockout experiment on the LacZ "
        "gene in E. coli. They analyze bacterial growth and color changes "
        "while exploring how CRISPR works.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "crispr",
        "materials": ["micropipetting", "sterile technique", "E. coli", "LacZ"],
        "metadata": {
            "grades": ["9", "12"],
            "school_year": "2026-2027",
            "school_level": "high",
        },
    },
    {
        "slug": "crispr-mutations-knockout-strategies",
        "name": "CRISPR Module 2 - Mutations & Knockout Strategies",
        "description": "Building on Module 1, students investigate different types of "
        "mutations and compare knockout strategies. They evaluate results and "
        "discuss real-world applications and ethics of gene editing.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "crispr",
        "materials": ["mutations", "knockout strategies", "gene editing ethics"],
        "metadata": {
            "grades": ["9", "12"],
            "school_year": "2026-2027",
            "school_level": "high",
        },
    },
    {
        "slug": "germs",
        "name": "Germs",
        "description": "An investigation into bacteria and how germs spread. Students learn "
        "plating techniques, test how environments affect bacterial growth, "
        "model how germs move through a population, and present scientific "
        "conclusions in a poster challenge.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "germs",
        "materials": ["bacteria", "plating techniques", "poster challenge"],
        "metadata": {
            "grades": ["7", "8"],
            "school_year": "2026-2027",
            "school_level": "middle",
        },
    },
    {
        "slug": "glucose-sensing",
        "name": "Glucose Sensing - Enzyme Function & Diagnostics",
        "description": "Students test glucose sensors using enzyme-based reactions, generate "
        "calibration curves, and analyze mystery patient samples. They "
        "explore how enzyme activity is influenced by conditions and connect "
        "findings to diabetes management.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "glucose-sensing",
        "materials": ["glucose sensors", "enzymes", "calibration curves"],
        "metadata": {
            "grades": ["9", "12"],
            "school_year": "2026-2027",
            "school_level": "high",
        },
    },
    {
        "slug": "thermodynamics-heat-transfer-calorimetry",
        "name": "Thermodynamics - Heat Transfer & Calorimetry",
        "description": "A hands-on high school module introducing heat transfer, energy "
        "distribution, and calorimetry through inquiry-based investigations. "
        "Students apply q = mCdeltaT, investigate food calorie content with "
        "chip calorimetry, calculate percent error, and present "
        "evidence-based conclusions.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "thermodynamics-heat-transfer-calorimetry",
        "materials": [
            "heat transfer",
            "calorimetry",
            "chip calorimetry",
            "data analysis",
        ],
        "metadata": {
            "grades": ["9", "12"],
            "school_year": "2026-2027",
            "school_level": "high",
        },
    },
    {
        "slug": "waves",
        "name": "Waves",
        "description": "Students learn how waves surround us in the air and everywhere. They "
        "cover the shape, function, and effects of waves on the sensory "
        "system and on materials, then design an environment for waves to "
        "propagate and make music.",
        "default_capacity": 24,
        "duration_minutes": 120,
        "session_count": 1,
        "family_key": "waves",
        "materials": ["wave models", "sound", "engineering challenge"],
        "metadata": {
            "grades": ["7", "8"],
            "school_year": "2026-2027",
            "school_level": "middle",
        },
    },
]


def upgrade():
    conn = op.get_bind()
    insert_sql = sa.text(
        """
        INSERT INTO modules
            (slug, name, description, default_capacity, duration_minutes,
             session_count, family_key, materials, metadata)
        VALUES
            (:slug, :name, :description, :default_capacity, :duration_minutes,
             :session_count, :family_key, :materials, :metadata)
        ON CONFLICT (slug) DO NOTHING
        """
    ).bindparams(
        sa.bindparam("materials", type_=postgresql.ARRAY(sa.String)),
        sa.bindparam("metadata", type_=postgresql.JSONB),
    )
    for module in SEED_MODULES:
        conn.execute(insert_sql, module)


def downgrade():
    # Events reference a module by its slug as a plain string, not a foreign
    # key, so removing these rows cannot orphan an event — it only empties the
    # catalog they were chosen from.
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM modules WHERE slug = ANY(:slugs)"),
        {"slugs": [m["slug"] for m in SEED_MODULES]},
    )
