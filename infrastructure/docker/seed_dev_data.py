#!/usr/bin/env python3
"""Seed sample Indiana legal chunks into pgvector for local development.

Usage:
    python infrastructure/docker/seed_dev_data.py

Requires the postgres container to be running (docker compose up -d postgres).
Generates deterministic embeddings (no Bedrock needed).
"""
from __future__ import annotations

import hashlib

import psycopg

DATABASE_URL = (
    __import__("os").environ.get(
        "DATABASE_URL",
        "postgresql://indyleg:changeme@localhost:5432/indyleg",
    )
    .replace("+psycopg", "")   # psycopg3 connect() doesn't use the SQLAlchemy driver suffix
)

# ── Sample Indiana legal chunks ──────────────────────────────────────────────

CHUNKS = [
    {
        "chunk_id": "ic-35-43-4-2-001",
        "source_id": "indiana-code-35-43-4",
        "section": "IC 35-43-4-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-43-4-2 — Theft. "
            "A person who knowingly or intentionally exerts unauthorized control over "
            "property of another person, with intent to deprive the other person of any "
            "part of its value or use, commits theft, a Class A misdemeanor. "
            "However, the offense is: (1) a Level 6 felony if the fair market value of "
            "the property is at least $750 and less than $50,000; (2) a Level 5 felony "
            "if the fair market value of the property is at least $50,000."
        ),
        "citations": ["IC 35-43-4-2"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "35", "article": "43",
        },
    },
    {
        "chunk_id": "ic-35-43-4-2-002",
        "source_id": "indiana-code-35-43-4",
        "section": "IC 35-43-4-2",
        "section_idx": 1,
        "content": (
            "Theft penalties under IC 35-43-4-2: The offense is a Level 6 felony if "
            "the property is a firearm or the value is $750-$50,000. It is a Level 5 "
            "felony if the value is $50,000 or more or the property was taken from a "
            "person's body. Theft of a motor vehicle (regardless of value) is a Level 6 "
            "felony. Theft from a person over 65 years of age: Level 6 felony if value "
            "under $750, Level 5 felony if $750 or more."
        ),
        "citations": ["IC 35-43-4-2"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "35", "article": "43",
        },
    },
    {
        "chunk_id": "ic-35-43-4-2-003",
        "source_id": "indiana-code-35-43-4",
        "section": "IC 35-43-4-2",
        "section_idx": 2,
        "content": (
            "Indiana theft sentencing ranges: A Class A misdemeanor carries up to 1 year "
            "in jail and a fine up to $5,000. A Level 6 felony carries 6 months to 2.5 years "
            "with an advisory sentence of 1 year, and a fine up to $10,000. A Level 5 felony "
            "carries 1 to 6 years with an advisory sentence of 3 years, and a fine up to "
            "$10,000. Courts may also order restitution to the victim. IC 35-50-2-7 (Level 6), "
            "IC 35-50-2-6 (Level 5), IC 35-50-3-2 (Class A misdemeanor)."
        ),
        "citations": ["IC 35-43-4-2", "IC 35-50-2-7", "IC 35-50-2-6", "IC 35-50-3-2"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "35", "article": "50",
        },
    },
    {
        "chunk_id": "ic-35-43-4-3-001",
        "source_id": "indiana-code-35-43-4",
        "section": "IC 35-43-4-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-43-4-3 — Receiving stolen property. "
            "A person who knowingly or intentionally receives, retains, or disposes of "
            "the property of another person that has been the subject of theft commits "
            "receiving stolen property, a Class A misdemeanor. The offense levels mirror "
            "the theft statute: Level 6 felony ($750-$50,000), Level 5 felony ($50,000+)."
        ),
        "citations": ["IC 35-43-4-3"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "35", "article": "43",
        },
    },
    {
        "chunk_id": "ic-35-43-4-2a-001",
        "source_id": "indiana-code-35-43-4",
        "section": "IC 35-43-4-2.5",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-43-4-2.5 — Conversion. "
            "A person who knowingly or intentionally exerts unauthorized control over "
            "property of another person commits criminal conversion, a Class A misdemeanor. "
            "Unlike theft, conversion does not require intent to deprive. Conversion of a "
            "motor vehicle is a Level 6 felony. Conversion is often charged as an alternative "
            "to theft when intent to permanently deprive cannot be proven."
        ),
        "citations": ["IC 35-43-4-2.5"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "35", "article": "43",
        },
    },
    {
        "chunk_id": "ic-35-43-2-1-001",
        "source_id": "indiana-code-35-43-2",
        "section": "IC 35-43-2-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-43-2-1 — Burglary. "
            "A person who breaks and enters the building or structure of another person, "
            "with intent to commit a felony or theft in it, commits burglary, a Level 5 "
            "felony. The offense is a Level 4 felony if it results in bodily injury, "
            "Level 3 if it is a dwelling, Level 2 if a dwelling with injury, and Level 1 "
            "if a dwelling with a deadly weapon resulting in serious bodily injury."
        ),
        "citations": ["IC 35-43-2-1"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "35", "article": "43",
        },
    },
    {
        "chunk_id": "ic-35-43-4-2-enhance-001",
        "source_id": "indiana-code-35-43-4",
        "section": "IC 35-43-4-2",
        "section_idx": 3,
        "content": (
            "Theft enhancement factors under Indiana law: Prior convictions for theft or "
            "related offenses may enhance the penalty. Habitual offender enhancement under "
            "IC 35-50-2-8 may add up to an additional term. Theft committed as part of a "
            "pattern of criminal activity (organized retail theft) may be charged under "
            "IC 35-45-6-2 as a Level 5 felony. Shoplifting (retail theft) valued under $750 "
            "is a Class A misdemeanor under IC 35-43-4-2(a)."
        ),
        "citations": ["IC 35-43-4-2", "IC 35-50-2-8", "IC 35-45-6-2"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "35", "article": "43",
        },
    },
    {
        "chunk_id": "eviction-ic-32-31-001",
        "source_id": "indiana-code-32-31",
        "section": "IC 32-31-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 32-31-1 — Landlord-Tenant Relations. "
            "Indiana landlord-tenant law is governed by IC 32-31. A landlord must provide "
            "written notice before filing an eviction. For nonpayment of rent, the landlord "
            "must give 10 days' written notice. For lease violations, 30 days' notice is "
            "typically required. The eviction process begins with the landlord filing a "
            "complaint in small claims court. The tenant has the right to appear and contest."
        ),
        "citations": ["IC 32-31-1"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "32", "article": "31",
        },
    },
    {
        "chunk_id": "eviction-ic-32-31-002",
        "source_id": "indiana-code-32-31",
        "section": "IC 32-31-1-6",
        "section_idx": 1,
        "content": (
            "Eviction procedure in Indiana: After a judgment in the landlord's favor, "
            "the court issues a writ of possession. The sheriff executes the writ, giving "
            "the tenant 48 hours to vacate. Self-help evictions (changing locks, removing "
            "belongings, shutting off utilities) are illegal under Indiana law. A landlord "
            "must follow the judicial process. Damages for illegal eviction may include "
            "actual damages, attorney fees, and punitive damages."
        ),
        "citations": ["IC 32-31-1-6"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "32", "article": "31",
        },
    },
    {
        "chunk_id": "dui-ic-9-30-5-001",
        "source_id": "indiana-code-9-30-5",
        "section": "IC 9-30-5",
        "section_idx": 0,
        "content": (
            "Indiana Code § 9-30-5 — Operating While Intoxicated (OWI). "
            "A person who operates a vehicle with a BAC of 0.08% or more commits OWI, "
            "a Class C misdemeanor. OWI with BAC of 0.15% or more is a Class A misdemeanor. "
            "OWI causing serious bodily injury is a Level 6 felony. OWI causing death is a "
            "Level 4 felony. Prior OWI convictions within 7 years enhance the offense to a "
            "Level 6 felony. Penalties include license suspension, fines, and possible jail."
        ),
        "citations": ["IC 9-30-5"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "9", "article": "30",
        },
    },
    {
        "chunk_id": "child-custody-ic-31-17-001",
        "source_id": "indiana-code-31-17",
        "section": "IC 31-17-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 31-17-2 — Child Custody Determination. "
            "In determining custody, the court shall consider all relevant factors, "
            "including: (1) the age and sex of the child; (2) the wishes of the parents; "
            "(3) the wishes of the child (given more weight if age 14+); (4) the mental "
            "and physical health of all individuals; (5) the child's adjustment to home, "
            "school, and community; (6) evidence of domestic violence. The court applies "
            "the 'best interests of the child' standard per IC 31-17-2-8."
        ),
        "citations": ["IC 31-17-2", "IC 31-17-2-8"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "31", "article": "17",
        },
    },
    {
        "chunk_id": "divorce-ic-31-15-001",
        "source_id": "indiana-code-31-15",
        "section": "IC 31-15-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 31-15-2 — Dissolution of Marriage. "
            "Indiana is a no-fault divorce state. The sole ground for dissolution is "
            "irretrievable breakdown of the marriage under IC 31-15-2-3. A 60-day "
            "waiting period is required from the date of filing. Property division follows "
            "the presumption of equal division under IC 31-15-7-5. Spousal maintenance "
            "(alimony) is limited under IC 31-15-7-2 to cases of incapacity, caregiver "
            "situations, or rehabilitative maintenance."
        ),
        "citations": ["IC 31-15-2", "IC 31-15-2-3", "IC 31-15-7-5", "IC 31-15-7-2"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "31", "article": "15",
        },
    },
    # ── Tax evasion / tax fraud ───────────────────────────────────────────────
    {
        "chunk_id": "ic-6-8-1-10-1-001",
        "source_id": "indiana-code-6-8.1-10",
        "section": "IC 6-8.1-10-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 6-8.1-10-1 — Failure to pay tax. "
            "If a person fails to file a return or pay the full amount of tax shown on a "
            "return by the due date, the person is liable for a penalty equal to 10% of "
            "the unpaid tax. In addition, interest accrues on any unpaid tax at the rate "
            "established under IC 6-8.1-10-1(c). The Indiana Department of Revenue may "
            "waive the penalty upon a showing of reasonable cause. Failure to pay is "
            "treated separately from fraudulent evasion."
        ),
        "citations": ["IC 6-8.1-10-1"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "6", "article": "8.1",
        },
    },
    {
        "chunk_id": "ic-6-8-1-10-2-001",
        "source_id": "indiana-code-6-8.1-10",
        "section": "IC 6-8.1-10-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 6-8.1-10-2 — Tax evasion and fraud penalties. "
            "A person who (1) fails to file a required tax return intending to evade tax, "
            "(2) makes or subscribes a false or fraudulent return, statement, or document, "
            "or (3) willfully attempts to evade or defeat any tax imposed under Indiana law "
            "commits tax evasion, a Level 6 felony. If the amount of tax evaded is $50,000 "
            "or more, the offense is a Level 5 felony. In addition to criminal penalties, "
            "the taxpayer is liable for a fraud penalty of 100% of the unpaid tax and "
            "applicable interest under IC 6-8.1-10-4."
        ),
        "citations": ["IC 6-8.1-10-2", "IC 6-8.1-10-4"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "6", "article": "8.1",
        },
    },
    {
        "chunk_id": "ic-6-8-1-10-4-001",
        "source_id": "indiana-code-6-8.1-10",
        "section": "IC 6-8.1-10-4",
        "section_idx": 0,
        "content": (
            "Indiana Code § 6-8.1-10-4 — Civil fraud penalty for tax. "
            "If the Indiana Department of Revenue determines that any part of a tax "
            "deficiency is due to fraud with intent to evade tax, the person is liable "
            "for a civil penalty equal to 100% of the unpaid tax attributable to fraud. "
            "The fraud penalty is in addition to the 10% failure-to-pay penalty and "
            "interest. The Department bears the burden of proving fraud by clear and "
            "convincing evidence. The fraud penalty applies to all taxes administered "
            "by the Department, including individual income tax, corporate income tax, "
            "and sales tax."
        ),
        "citations": ["IC 6-8.1-10-4", "IC 6-8.1-10-1"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "6", "article": "8.1",
        },
    },
    {
        "chunk_id": "ic-6-8-1-10-sentencing-001",
        "source_id": "indiana-code-6-8.1-10",
        "section": "IC 6-8.1-10-2",
        "section_idx": 1,
        "content": (
            "Indiana tax evasion sentencing ranges and consequences: "
            "Tax evasion as a Level 6 felony (under $50,000 evaded) carries 6 months to "
            "2.5 years imprisonment with an advisory sentence of 1 year, and a fine up to "
            "$10,000 (IC 35-50-2-7). Tax evasion as a Level 5 felony ($50,000 or more) "
            "carries 1 to 6 years with an advisory sentence of 3 years, and a fine up to "
            "$10,000 (IC 35-50-2-6). Federal tax evasion under 26 U.S.C. § 7201 is a "
            "separate offense carrying up to 5 years federal imprisonment and $250,000 in "
            "fines. Indiana may also seek injunctive relief and seizure of assets."
        ),
        "citations": ["IC 6-8.1-10-2", "IC 35-50-2-7", "IC 35-50-2-6"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "6", "article": "8.1",
        },
    },
    {
        "chunk_id": "ic-6-8-1-10-elements-001",
        "source_id": "indiana-code-6-8.1-10",
        "section": "IC 6-8.1-10-2",
        "section_idx": 2,
        "content": (
            "Elements of Indiana tax evasion offense under IC 6-8.1-10-2: "
            "To prove tax evasion the State must show: (1) the defendant had a legal duty "
            "to file a return or pay a tax; (2) the defendant knew of that duty; and "
            "(3) the defendant willfully evaded or attempted to evade the tax. Willfulness "
            "requires a voluntary, intentional violation of a known legal duty. Mere "
            "negligence or mistake is not sufficient. Evidence of evasion includes "
            "maintaining false records, filing false returns, using nominee accounts, "
            "concealing income, or structuring transactions to avoid reporting."
        ),
        "citations": ["IC 6-8.1-10-2"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "6", "article": "8.1",
        },
    },
    {
        "chunk_id": "ic-6-3-2-001",
        "source_id": "indiana-code-6-3",
        "section": "IC 6-3-2-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 6-3-2-1 — Individual Adjusted Gross Income Tax. "
            "Indiana imposes an adjusted gross income tax on every resident individual "
            "and on every nonresident individual with Indiana-source income. The current "
            "flat tax rate is 3.05% of Indiana adjusted gross income. Employers must "
            "withhold Indiana income tax from wages under IC 6-3-4-8. Failure to withhold "
            "or remit withheld taxes can constitute a separate offense from personal tax "
            "evasion. County income taxes are additional surtaxes collected under IC 6-3.6."
        ),
        "citations": ["IC 6-3-2-1", "IC 6-3-4-8", "IC 6-3.6"],
        "metadata": {
            "court": "indiana", "jurisdiction": "Indiana",
            "type": "statute", "title": "6", "article": "3",
        },
    },
]


def deterministic_vector(text: str, dim: int = 1024) -> list[float]:
    """Hash-based deterministic pseudo-embedding (matches BedrockEmbedder._deterministic_vector)."""
    import random as _random

    seed = int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2**32)
    rng = _random.Random(seed)  # noqa: S311 — non-cryptographic deterministic embeddings
    floats = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = max(sum(x * x for x in floats) ** 0.5, 1e-9)
    return [x / norm for x in floats]


def main() -> None:
    print(f"Connecting to {DATABASE_URL} ...")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for chunk in CHUNKS:
                vec = deterministic_vector(chunk["content"])
                vec_literal = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
                cur.execute(
                    """
                    INSERT INTO legal_chunks
                        (chunk_id, source_id, section, section_idx,
                         char_start, char_end, citations, metadata, content, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        chunk["chunk_id"],
                        chunk["source_id"],
                        chunk["section"],
                        chunk["section_idx"],
                        0,
                        len(chunk["content"]),
                        chunk["citations"],
                        __import__("json").dumps(chunk["metadata"]),
                        chunk["content"],
                        vec_literal,
                    ),
                )
            conn.commit()
            cur.execute("SELECT count(*) FROM legal_chunks")
            count = cur.fetchone()[0]
            print(f"✅ Seeded {len(CHUNKS)} chunks. Total in DB: {count}")


if __name__ == "__main__":
    main()
