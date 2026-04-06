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
    __import__("os")
    .environ.get(
        "DATABASE_URL",
        "postgresql://indyleg:changeme@localhost:5432/indyleg",
    )
    .replace("+psycopg", "")  # psycopg3 connect() doesn't use the SQLAlchemy driver suffix
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "43",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "43",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "43",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "43",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "43",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "43",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "32",
            "article": "31",
            "case_type": "Civil",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "32",
            "article": "31",
            "case_type": "Civil",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "9",
            "article": "30",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "31",
            "article": "17",
            "case_type": "Family",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "31",
            "article": "15",
            "case_type": "Family",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "6",
            "article": "8.1",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "6",
            "article": "8.1",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "6",
            "article": "8.1",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "6",
            "article": "8.1",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "6",
            "article": "8.1",
            "case_type": "Criminal",
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
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "6",
            "article": "3",
            "case_type": "Tax",
        },
    },
    # ── Homicide (IC 35-42-1) ─────────────────────────────────────────────────
    {
        "chunk_id": "ic-35-42-1-1-001",
        "source_id": "indiana-code-35-42-1",
        "section": "IC 35-42-1-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-1-1 — Murder. "
            "A person who: (1) knowingly or intentionally kills another human being; "
            "(2) kills another human being while committing or attempting to commit arson, "
            "burglary, child molesting, criminal deviate conduct, kidnapping, rape, robbery, "
            "carjacking, human trafficking, or sexual trafficking of a minor; or "
            "(3) kills another human being while committing or attempting to commit dealing "
            "in or manufacturing cocaine, a narcotic drug, or methamphetamine; or "
            "(4) knowingly or intentionally kills a fetus that has attained viability; "
            "commits murder, a felony. "
            "Sentence under IC 35-50-2-9: advisory 55 years, minimum 45 years, maximum "
            "65 years. Life imprisonment without parole if aggravating circumstances "
            "outweigh mitigating circumstances. Maximum criminal penalty includes a "
            "fine up to $10,000."
        ),
        "citations": ["IC 35-42-1-1", "IC 35-50-2-9"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-42-1-1-002",
        "source_id": "indiana-code-35-42-1",
        "section": "IC 35-42-1-1",
        "section_idx": 1,
        "content": (
            "Indiana felony murder rule (IC 35-42-1-1(2)-(3)): A murder committed during "
            "the course of a specified felony constitutes murder even if unintentional. "
            "Predicate felonies include arson, burglary, child molesting, confinement, "
            "kidnapping, rape, robbery, carjacking, human trafficking, and drug dealing. "
            "All participants in the underlying felony may be charged with murder for a "
            "killing during the crime, even if only one participant delivered the fatal "
            "blow, under aider/abettor liability (IC 35-41-2-4). The State does not need "
            "to prove intent to kill — only intent to commit the predicate felony."
        ),
        "citations": ["IC 35-42-1-1", "IC 35-41-2-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-42-1-3-001",
        "source_id": "indiana-code-35-42-1",
        "section": "IC 35-42-1-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-1-3 — Voluntary manslaughter, a Level 2 felony. "
            "A person who knowingly or intentionally kills another human being while acting "
            "under sudden heat commits voluntary manslaughter, a Level 2 felony. The offense "
            "is a Level 1 felony if committed by means of a deadly weapon. "
            "'Sudden heat' is a mitigating circumstance that reduces murder to voluntary "
            "manslaughter. Once the defendant presents substantial evidence of sudden heat, "
            "the State must prove beyond a reasonable doubt that the defendant was not acting "
            "under sudden heat. "
            "Sentence as Level 2 felony: advisory 17.5 years, minimum 10 years, maximum "
            "30 years. Level 1: advisory 30 years, minimum 20, maximum 40 years."
        ),
        "citations": ["IC 35-42-1-3", "IC 35-50-2-3", "IC 35-50-2-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-42-1-4-001",
        "source_id": "indiana-code-35-42-1",
        "section": "IC 35-42-1-4",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-1-4 — Involuntary manslaughter, a Level 5 felony. "
            "A person who kills another human being while committing or attempting to commit "
            "(1) a Class C misdemeanor, (2) a Class A misdemeanor, or (3) a Level 5 or "
            "Level 6 felony that inherently poses a risk of serious bodily injury commits "
            "involuntary manslaughter. Distinct from reckless homicide (IC 35-42-1-5) which "
            "is based on a reckless act without an underlying crime. "
            "Sentence: advisory 3 years, minimum 1 year, maximum 6 years, fine up to $10,000."
        ),
        "citations": ["IC 35-42-1-4", "IC 35-42-1-5", "IC 35-50-2-6"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-42-1-5-001",
        "source_id": "indiana-code-35-42-1",
        "section": "IC 35-42-1-5",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-1-5 — Reckless homicide, a Level 5 felony. "
            "A person who recklessly kills another human being commits reckless homicide. "
            "'Recklessly' means the person is aware of and consciously disregards a "
            "substantial and unjustifiable risk that the conduct might cause the result "
            "(IC 35-41-2-2(c)). Common scenarios: extremely dangerous driving without "
            "intoxication, discharging a firearm recklessly in a populated area, or "
            "vehicular homicide below OWI threshold. "
            "Sentence: advisory 3 years, minimum 1 year, maximum 6 years."
        ),
        "citations": ["IC 35-42-1-5", "IC 35-41-2-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-50-2-9-001",
        "source_id": "indiana-code-35-50-2",
        "section": "IC 35-50-2-9",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-50-2-9 — Murder sentencing and criminal penalties. "
            "For a conviction of murder (IC 35-42-1-1), the court shall sentence the person "
            "to a fixed term between 45 and 65 years with an advisory sentence of 55 years, "
            "or to life imprisonment without parole. "
            "Life without parole is imposed when aggravating circumstances (listed in "
            "IC 35-50-2-9(b)) outweigh mitigating circumstances. Aggravating circumstances "
            "include: victim under age 12; killing of a public safety official or judge; "
            "prior murder conviction; use of an explosive or weapon of mass destruction; "
            "killing a witness to prevent testimony; murder for hire; multiple murders."
        ),
        "citations": ["IC 35-50-2-9", "IC 35-42-1-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    # ── Self-Defense / Castle Doctrine (IC 35-41-3-2) ────────────────────────
    {
        "chunk_id": "ic-35-41-3-2-001",
        "source_id": "indiana-code-35-41-3",
        "section": "IC 35-41-3-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-41-3-2 — Justification for use of force (Stand Your Ground). "
            "A person is justified in using reasonable force against another person to "
            "protect themselves or a third person from what they reasonably believe to be "
            "the imminent use of unlawful force. Deadly force is justified only if needed "
            "to prevent serious bodily injury or death. "
            "Indiana has no duty to retreat: a person may stand their ground in any place "
            "they have a legal right to be. Codified in 2006 and expanded in 2012 "
            "(P.L. 142-2012). A person who uses justified force is immune from civil "
            "liability for that force."
        ),
        "citations": ["IC 35-41-3-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "41",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-41-3-2-002",
        "source_id": "indiana-code-35-41-3",
        "section": "IC 35-41-3-2",
        "section_idx": 1,
        "content": (
            "Indiana Castle Doctrine (IC 35-41-3-2(b)): A person is justified in using "
            "reasonable force, including deadly force, against another person if the other "
            "person is unlawfully and forcibly entering or has entered a dwelling, curtilage, "
            "or occupied motor vehicle, or is attempting to remove another person against "
            "their will from those locations. No duty to retreat applies in these situations. "
            "The law creates a presumption that a person who forcibly and unlawfully enters "
            "a dwelling intends harm. "
            "Exceptions to justification: force is not justified if the person is committing "
            "a crime, provoked the attack with intent to cause injury, or is the initial "
            "aggressor who has not communicated withdrawal."
        ),
        "citations": ["IC 35-41-3-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "41",
            "case_type": "Criminal",
        },
    },
    # ── Battery (IC 35-42-2-1) ────────────────────────────────────────────────
    {
        "chunk_id": "ic-35-42-2-1-001",
        "source_id": "indiana-code-35-42-2",
        "section": "IC 35-42-2-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-2-1 — Battery. "
            "A person who knowingly or intentionally touches another in a rude, insolent, "
            "or angry manner commits battery: "
            "Class B misdemeanor (base); Class A misdemeanor if causes bodily injury; "
            "Level 6 felony if causes moderate bodily injury or victim is a public safety "
            "official with bodily injury; "
            "Level 5 felony if causes serious bodily injury, or victim is under 14 and "
            "defendant is at least 18; "
            "Level 4 felony if committed with a deadly weapon, victim is an endangered "
            "adult or public safety official, or causes bodily injury to a pregnant woman "
            "when defendant knew of pregnancy; "
            "Level 3 felony if causes serious bodily injury to a public safety official "
            "performing their duties; "
            "Level 2 felony if causes serious bodily injury by means of a deadly weapon, "
            "or defendant has a prior battery conviction causing injury."
        ),
        "citations": ["IC 35-42-2-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-42-2-1-3-001",
        "source_id": "indiana-code-35-42-2",
        "section": "IC 35-42-2-1.3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-2-1.3 — Domestic battery. "
            "A person who knowingly or intentionally touches a family or household member "
            "in a rude, insolent, or angry manner causing bodily injury commits domestic "
            "battery, a Class A misdemeanor. Enhanced to: "
            "Level 6 felony with prior battery or domestic battery conviction; "
            "Level 5 felony if committed in the presence of a child under 16, or victim "
            "is under 14 and defendant is at least 18; "
            "Level 3 felony if committed with a deadly weapon causing serious bodily injury. "
            "'Family or household member' includes current/former spouses, parents, "
            "children, cohabitants, persons with a child in common, and persons in or "
            "formerly in an intimate relationship. "
            "A domestic battery conviction triggers loss of federal firearm rights "
            "(18 U.S.C. § 922(g)(9))."
        ),
        "citations": ["IC 35-42-2-1.3"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    # ── Felony Sentencing Table (IC 35-50-2) ──────────────────────────────────
    {
        "chunk_id": "ic-35-50-2-overview-001",
        "source_id": "indiana-code-35-50-2",
        "section": "IC 35-50-2",
        "section_idx": 0,
        "content": (
            "Indiana felony sentencing ranges (effective July 1, 2014 — HEA 1006-2014): "
            "Murder (IC 35-50-2-9): 45–65 years, advisory 55 years, or life without parole. "
            "Level 1 felony (IC 35-50-2-2): 20–40 years, advisory 30 years. "
            "Level 2 felony (IC 35-50-2-3): 10–30 years, advisory 17.5 years. "
            "Level 3 felony (IC 35-50-2-4): 3–16 years, advisory 9 years. "
            "Level 4 felony (IC 35-50-2-4.5): 2–12 years, advisory 6 years. "
            "Level 5 felony (IC 35-50-2-6): 1–6 years, advisory 3 years. "
            "Level 6 felony (IC 35-50-2-7): 6 months–2.5 years, advisory 1 year. "
            "All felony fines: up to $10,000. Courts must state reasons for departing "
            "from the advisory sentence (IC 35-38-1-3)."
        ),
        "citations": [
            "IC 35-50-2-2",
            "IC 35-50-2-3",
            "IC 35-50-2-4",
            "IC 35-50-2-4.5",
            "IC 35-50-2-6",
            "IC 35-50-2-7",
            "IC 35-50-2-9",
        ],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-50-2-2-001",
        "source_id": "indiana-code-35-50-2",
        "section": "IC 35-50-2-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-50-2-2 — Level 1 felony sentence. "
            "A person convicted of a Level 1 felony shall be imprisoned for a fixed term "
            "between 20 and 40 years, with an advisory sentence of 30 years. Fine up to "
            "$10,000. Level 1 is the most serious classification below murder. "
            "Examples: Rape resulting in serious bodily injury (IC 35-42-4-1(b)(2)); "
            "dealing cocaine/methamphetamine ≥ 10 grams resulting in death "
            "(IC 35-48-4-1(b)(1)(D)); child molesting (IC 35-42-4-3(b)) if penetration "
            "and victim is under 14."
        ),
        "citations": ["IC 35-50-2-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-50-2-3-001",
        "source_id": "indiana-code-35-50-2",
        "section": "IC 35-50-2-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-50-2-3 — Level 2 felony sentence. "
            "Fixed term 10–30 years, advisory sentence 17.5 years, fine up to $10,000. "
            "Examples: Voluntary manslaughter (IC 35-42-1-3); robbery resulting in death "
            "(IC 35-42-5-1(a)); dealing cocaine/methamphetamine ≥ 10 grams "
            "(IC 35-48-4-1(b)(1)(B)); criminal confinement resulting in serious bodily "
            "injury; kidnapping (certain circumstances)."
        ),
        "citations": ["IC 35-50-2-3"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-50-2-4-001",
        "source_id": "indiana-code-35-50-2",
        "section": "IC 35-50-2-4",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-50-2-4 — Level 3 felony sentence. "
            "Fixed term 3–16 years, advisory sentence 9 years, fine up to $10,000. "
            "Examples: Burglary of a dwelling (IC 35-43-2-1(b)(2)); robbery while armed "
            "with a deadly weapon (IC 35-42-5-1(a)(2)); dealing cocaine/methamphetamine "
            "5–10 grams (IC 35-48-4-1(b)(1)(A)(iii)); rape (base offense when no "
            "aggravating factors, IC 35-42-4-1(a)); OWI causing death with prior "
            "conviction (IC 9-30-5-5)."
        ),
        "citations": ["IC 35-50-2-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-50-2-4-5-001",
        "source_id": "indiana-code-35-50-2",
        "section": "IC 35-50-2-4.5",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-50-2-4.5 — Level 4 felony sentence. "
            "Fixed term 2–12 years, advisory sentence 6 years, fine up to $10,000. "
            "Created by the 2014 criminal code reform (HEA 1006-2014, effective July 1, 2014) "
            "to fill the gap between former Class B and Class C felonies. "
            "Examples: Arson causing property damage ≥ $10,000; OWI causing death "
            "(IC 9-30-5-4); dealing cocaine/methamphetamine 1–5 grams "
            "(IC 35-48-4-1(b)(1)(A)(ii)); child molesting without penetration when "
            "victim is under 14 (IC 35-42-4-3(a))."
        ),
        "citations": ["IC 35-50-2-4.5"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-50-3-001",
        "source_id": "indiana-code-35-50-3",
        "section": "IC 35-50-3",
        "section_idx": 0,
        "content": (
            "Indiana misdemeanor sentencing (IC 35-50-3): "
            "Class A misdemeanor (IC 35-50-3-2): fixed term up to 1 year county jail, "
            "fine up to $5,000. Examples: OWI (.15+ BAC), battery with bodily injury, "
            "theft under $750, possession of marijuana (first offense >30g), carrying "
            "a handgun without a license. "
            "Class B misdemeanor (IC 35-50-3-3): up to 180 days, fine up to $1,000. "
            "Examples: possession of marijuana (<30g, first offense), reckless driving, "
            "disorderly conduct, basic battery (no injury). "
            "Class C misdemeanor (IC 35-50-3-4): up to 60 days, fine up to $500. "
            "Examples: OWI (BAC .08–.15, first offense), public intoxication. "
            "Courts may impose split sentences: part jail, part probation."
        ),
        "citations": ["IC 35-50-3-2", "IC 35-50-3-3", "IC 35-50-3-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    # ── Habitual Offender & Sentencing Factors ────────────────────────────────
    {
        "chunk_id": "ic-35-50-2-8-001",
        "source_id": "indiana-code-35-50-2",
        "section": "IC 35-50-2-8",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-50-2-8 — Habitual offender enhancement. "
            "A person who has accumulated two or more prior unrelated felony convictions "
            "(at least one resulting in imprisonment) may be found a habitual offender. "
            "If found habitual, the court shall add a fixed additional term: "
            "6 to 20 years (advisory 10 years) for a Level 1–4 base offense; "
            "2 to 6 years (advisory 4 years) for a Level 5–6 base offense. "
            "The finding must be made by the jury in a separate sentencing phase. "
            "The enhancement cannot be suspended, reduced, or run concurrent with the base. "
            "Habitual substance offender (IC 35-50-2-10): separate enhancement for "
            "repeat drug convictions — adds 1–8 years."
        ),
        "citations": ["IC 35-50-2-8", "IC 35-50-2-10"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "50",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-38-1-7-1-001",
        "source_id": "indiana-code-35-38-1",
        "section": "IC 35-38-1-7.1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-38-1-7.1 — Aggravating and mitigating circumstances. "
            "Courts may impose above the advisory sentence based on aggravating circumstances "
            "including: prior criminal history; need for correctional treatment; refusal of "
            "treatment; victim age under 12 or over 65; victim was mentally/physically "
            "infirm; defendant was in a position of trust; use of a firearm; defendant was "
            "on probation/parole at time of offense; harm greater than elements require. "
            "Courts may impose below advisory based on mitigating circumstances: no prior "
            "criminal history; unlikely to reoffend; victim induced or facilitated the "
            "crime; substantial assistance to the State; mental illness or intellectual "
            "disability; character suggests responsiveness to probation. "
            "Sentencing statement required: the court must identify and weigh "
            "aggravating/mitigating factors on the record (IC 35-38-1-3)."
        ),
        "citations": ["IC 35-38-1-7.1", "IC 35-38-1-3"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    # ── Drug Offenses (IC 35-48-4) ────────────────────────────────────────────
    {
        "chunk_id": "ic-35-48-4-1-001",
        "source_id": "indiana-code-35-48-4",
        "section": "IC 35-48-4-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-48-4-1 — Dealing in cocaine, narcotic drug, or "
            "methamphetamine. A person who knowingly or intentionally manufactures, "
            "finances manufacture, delivers, or finances delivery of cocaine, a narcotic "
            "drug, or methamphetamine; or possesses with intent: "
            "Level 5 felony (base, < 1 gram pure); "
            "Level 4 felony (1 gram to < 5 grams pure); "
            "Level 3 felony (5 grams to < 10 grams pure; or offense within 1,000 ft of "
            "school or in a school building); "
            "Level 2 felony (≥ 10 grams pure); "
            "Level 1 felony (≥ 10 grams AND death of another results from the substance, "
            "or delivery to person under 18). "
            "Enhancements apply for delivery at or near a school, use of a firearm, "
            "delivery to a minor, or a prior drug felony conviction."
        ),
        "citations": ["IC 35-48-4-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "48",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-48-4-6-001",
        "source_id": "indiana-code-35-48-4",
        "section": "IC 35-48-4-6",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-48-4-6 — Possession of a controlled substance. "
            "A person who knowingly or intentionally possesses a Schedule I, II, III, IV, "
            "or V controlled substance (excluding marijuana, hash oil, hashish, salvia) "
            "commits possession: "
            "Class A misdemeanor (base offense; Schedule III–V or Schedule I–II in small "
            "amounts); "
            "Level 6 felony if prior drug conviction exists, or if the substance is a "
            "Schedule I or II drug in an amount of 5 grams or more. "
            "Possession of cocaine or methamphetamine (IC 35-48-4-6.1): "
            "Class A misdemeanor < 5 grams pure; "
            "Level 6 felony 5–10 grams or with prior; "
            "Level 5 felony ≥ 10 grams or prior felony drug conviction. "
            "Constructive possession may be charged when a person has control over "
            "a substance without exclusive physical possession."
        ),
        "citations": ["IC 35-48-4-6", "IC 35-48-4-6.1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "48",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-48-4-11-001",
        "source_id": "indiana-code-35-48-4",
        "section": "IC 35-48-4-11",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-48-4-11 — Possession of marijuana, hash oil, hashish, "
            "or salvia. "
            "Class B misdemeanor: possession of ≤ 30 grams marijuana (first offense). "
            "Class A misdemeanor: possession > 30 grams, or any amount with a prior "
            "drug conviction. "
            "Level 6 felony: prior drug felony conviction AND amount > 30 grams, OR "
            "any amount possessed in or near a school or public park. "
            "Indiana has not legalized recreational or medical marijuana as of 2025. "
            "Hemp-derived CBD products containing ≤ 0.3% THC are exempt (IC 15-15-13). "
            "Dealing marijuana (IC 35-48-4-10): Class A misdemeanor for ≤ 30g; "
            "Level 6 felony for > 30g; Level 5 felony for > 10 lbs or prior conviction."
        ),
        "citations": ["IC 35-48-4-11", "IC 35-48-4-10"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "48",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-48-4-school-001",
        "source_id": "indiana-code-35-48-4",
        "section": "IC 35-48-4-1",
        "section_idx": 1,
        "content": (
            "Indiana drug offense school zone enhancement. "
            "Under IC 35-48-4-1 and related provisions, a drug dealing offense is enhanced "
            "one level when committed: in a school building or on school grounds; on a "
            "school bus; within 1,000 feet of school property; in a public park while "
            "persons under 18 were present; or in a family housing complex. "
            "Effect: Level 5 → Level 4; Level 4 → Level 3; Level 3 → Level 2. "
            "This enhancement is cumulative with quantity-based elevations. The prosecution "
            "must allege the factual basis for the enhancement in the charging information "
            "and prove it beyond a reasonable doubt separately."
        ),
        "citations": ["IC 35-48-4-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "48",
            "case_type": "Criminal",
        },
    },
    # ── OWI Expanded (IC 9-30-5) ──────────────────────────────────────────────
    {
        "chunk_id": "ic-9-30-5-1-001",
        "source_id": "indiana-code-9-30-5",
        "section": "IC 9-30-5-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 9-30-5-1 — OWI Class C misdemeanor (BAC .08). "
            "A person who operates a vehicle while intoxicated commits OWI, a Class C "
            "misdemeanor. 'Intoxicated' means under the influence of alcohol (BAC ≥ .08% "
            "per se), a controlled substance, or a controlled substance analogue so that "
            "there is an impairment of thought, action, or description. "
            "Penalties: up to 60 days jail, fine up to $500, license suspension 90–180 days. "
            "SR-22 insurance required for 2 years. First-offense Class C OWI qualifies for "
            "a specialized driving privileges (SDP) petition under IC 9-30-16 "
            "(allows limited driving during suspension). "
            "The per se BAC rule: a BAC test of .08%+ constitutes intoxication as a matter "
            "of law without proof of actual impairment."
        ),
        "citations": ["IC 9-30-5-1", "IC 9-30-16"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "9",
            "article": "30",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-9-30-5-2-001",
        "source_id": "indiana-code-9-30-5",
        "section": "IC 9-30-5-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 9-30-5-2 — OWI endangering a person, Class A misdemeanor. "
            "A person who operates a vehicle with BAC ≥ .15% or operates while intoxicated "
            "in a manner that endangers a person commits OWI endangering, a Class A "
            "misdemeanor. Penalties: up to 1 year jail, fine up to $5,000. "
            "License suspension: minimum 90 days for first offense. "
            "Persistent drunk driver designation (IC 9-30-10-4): applies to a person "
            "with 2+ lifetime OWI convictions or 1 conviction with BAC ≥ .15%. Consequences: "
            "minimum 480 hours community service OR 1 year imprisonment; ignition interlock "
            "device required for not less than 1 year after license reinstatement."
        ),
        "citations": ["IC 9-30-5-2", "IC 9-30-10-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "9",
            "article": "30",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-9-30-5-3-001",
        "source_id": "indiana-code-9-30-5",
        "section": "IC 9-30-5-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 9-30-5-3 — OWI causing serious bodily injury, Level 6 felony. "
            "A person who operates a vehicle while intoxicated and causes serious bodily "
            "injury to another person commits a Level 6 felony. Sentence: 6 months–2.5 years, "
            "advisory 1 year, fine up to $10,000. "
            "'Serious bodily injury' means injury that creates substantial risk of death, "
            "causes permanent disfigurement, or causes permanent loss or impairment of a "
            "bodily organ or member (IC 35-31.5-2-292). "
            "Note: If injury is only 'bodily injury' (pain without permanent damage) the "
            "offense remains Class A misdemeanor. If the victim dies, it escalates to "
            "IC 9-30-5-4 (Level 4 felony) or IC 9-30-5-5 (Level 3 with prior conviction)."
        ),
        "citations": ["IC 9-30-5-3", "IC 35-31.5-2-292"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "9",
            "article": "30",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-9-30-5-4-001",
        "source_id": "indiana-code-9-30-5",
        "section": "IC 9-30-5-4",
        "section_idx": 0,
        "content": (
            "Indiana Code § 9-30-5-4 — OWI causing death, Level 4 felony. "
            "A person who operates a vehicle while intoxicated and causes the death of "
            "another person commits a Level 4 felony. Sentence: 2–12 years, advisory 6 "
            "years, fine up to $10,000. "
            "IC 9-30-5-5: OWI causing death with a prior OWI conviction within 7 years "
            "is a Level 3 felony (3–16 years, advisory 9 years). "
            "The prosecution must show the defendant's intoxicated operation was a "
            "proximate cause of death — not that it was the sole cause. The death of a "
            "viable fetus whose mother was killed constitutes a death under this statute. "
            "License revocation: minimum 2 years after sentence served."
        ),
        "citations": ["IC 9-30-5-4", "IC 9-30-5-5"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "9",
            "article": "30",
            "case_type": "Criminal",
        },
    },
    # ── Robbery (IC 35-42-5-1) ────────────────────────────────────────────────
    {
        "chunk_id": "ic-35-42-5-1-001",
        "source_id": "indiana-code-35-42-5",
        "section": "IC 35-42-5-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-5-1 — Robbery. "
            "A person who knowingly or intentionally takes property from another person or "
            "from the presence of another by using or threatening to use force, or by "
            "putting any person in fear, commits robbery: "
            "Level 5 felony (base, no bodily injury, no deadly weapon); "
            "Level 3 felony if armed with a deadly weapon or results in bodily injury; "
            "Level 2 felony if results in serious bodily injury; "
            "Level 1 felony if results in death. "
            "An unloaded but operable and displayed firearm qualifies as a 'deadly weapon.' "
            "Attempted robbery is charged one level below the completed offense. "
            "Robbery with a co-defendant triggers accomplice liability for all participants "
            "under IC 35-41-2-4."
        ),
        "citations": ["IC 35-42-5-1", "IC 35-41-2-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    # ── Rape / Sex Offenses ───────────────────────────────────────────────────
    {
        "chunk_id": "ic-35-42-4-1-001",
        "source_id": "indiana-code-35-42-4",
        "section": "IC 35-42-4-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-42-4-1 — Rape. "
            "A person who knowingly or intentionally has sexual intercourse with another "
            "person, or causes another to perform or submit to other sexual conduct, when: "
            "(1) compelled by force or imminent threat of force; "
            "(2) the other person is unaware the sexual intercourse or conduct is occurring; "
            "or (3) the other person is so mentally disabled or deficient that consent "
            "cannot be given; commits rape, a Level 3 felony. "
            "Enhanced to Level 1 felony if: results in serious bodily injury, or the "
            "defendant is armed with a deadly weapon. "
            "Sentence: Level 3 = 3–16 years advisory 9; Level 1 = 20–40 years advisory 30. "
            "A rape conviction requires lifetime registration on the Indiana Sex and Violent "
            "Offender Registry (IC 11-8-8-5)."
        ),
        "citations": ["IC 35-42-4-1", "IC 11-8-8-5"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "42",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-11-8-8-5-001",
        "source_id": "indiana-code-11-8-8",
        "section": "IC 11-8-8-5",
        "section_idx": 0,
        "content": (
            "Indiana Code § 11-8-8-5 — Sex and Violent Offender Registry (SVOR). "
            "Persons convicted of listed sex and violent offenses must register with local "
            "law enforcement. Registerable offenses include: rape, child molesting, sexual "
            "misconduct with a minor, kidnapping with sexual intent, and others. "
            "Registration duties: must register within 3 business days of release from "
            "incarceration, conviction (if no incarceration), or change of address. "
            "Must verify registration: annually for most offenders, every 180 days for "
            "sexually violent predators. "
            "Registration period: 10 years for most sex offenses; lifetime for sexually "
            "violent predators and certain serious offenses. "
            "Failure to register (IC 11-8-8-17): Level 6 felony (first), Level 5 felony "
            "(subsequent)."
        ),
        "citations": ["IC 11-8-8-5", "IC 11-8-8-17"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "11",
            "article": "8",
            "case_type": "Criminal",
        },
    },
    # ── Family Law: Child Support & Custody ───────────────────────────────────
    {
        "chunk_id": "ic-31-16-6-1-001",
        "source_id": "indiana-code-31-16",
        "section": "IC 31-16-6-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 31-16-6-1 — Child support: income shares model. "
            "Indiana uses the Income Shares model (Indiana Child Support Guidelines, "
            "updated periodically by the Indiana Supreme Court). Calculation steps: "
            "(1) Determine each parent's weekly gross income from all sources (wages, "
            "salary, self-employment, bonuses, unemployment, disability, rental income); "
            "(2) Calculate combined weekly adjusted income; "
            "(3) Reference the Guideline Schedule to find the basic weekly support obligation; "
            "(4) Prorate each parent's share proportional to their income contribution. "
            "A parent who earns 60% of the combined income pays 60% of the basic obligation. "
            "Deductions for extraordinary medical, educational, and extracurricular expenses "
            "may be added. Courts may deviate from guidelines upon written findings. "
            "Child support is not dischargeable in bankruptcy."
        ),
        "citations": ["IC 31-16-6-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "31",
            "article": "16",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-31-16-8-1-001",
        "source_id": "indiana-code-31-16",
        "section": "IC 31-16-8-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 31-16-8-1 — Child support modification and termination. "
            "A support order may be modified on showing of a substantial and continuing "
            "change in circumstances. A 20% deviation from current guidelines is a "
            "rebuttable presumption of substantial change. "
            "Retroactive modification: support cannot be modified retroactively before "
            "the date the petition for modification was filed. "
            "Termination under IC 31-16-6-6: "
            "(1) child marries or is emancipated; "
            "(2) child enlists in the armed forces; "
            "(3) child reaches age 19 AND has not continuously attended school since "
            "age 18 — if attending high school, support continues through graduation; "
            "(4) court finds child emancipated by circumstances. "
            "Income imputation: if a parent voluntarily underearns, the court may impute "
            "income at their earning capacity to prevent manipulation of support."
        ),
        "citations": ["IC 31-16-8-1", "IC 31-16-6-6"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "31",
            "article": "16",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-31-14-7-1-001",
        "source_id": "indiana-code-31-14",
        "section": "IC 31-14-7-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 31-14-7-1 — Establishment of paternity. "
            "Paternity may be established by: "
            "(1) Voluntary paternity affidavit (IC 16-37-2-2.1): signed and notarized by "
            "both parents at the hospital or vital statistics office; becomes a final "
            "judgment after 60 days unless rescinded; "
            "(2) Court action: either parent or the State (prosecutor's office) may file; "
            "court shall order genetic testing on request (IC 31-14-6-1); DNA test with "
            "probability ≥ 99% creates a rebuttable presumption of paternity; "
            "(3) Presumption by marriage: husband of the child's mother at time of birth "
            "is presumed to be the father (IC 31-14-7-2(1)). "
            "Paternity affects: child support obligation; right to custody or visitation; "
            "inheritance rights; Social Security survivor benefits; health insurance."
        ),
        "citations": ["IC 31-14-7-1", "IC 16-37-2-2.1", "IC 31-14-6-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "31",
            "article": "14",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-31-17-4-2-001",
        "source_id": "indiana-code-31-17",
        "section": "IC 31-17-4-2",
        "section_idx": 0,
        "content": (
            "Indiana Parenting Time Guidelines — standard schedule. "
            "The Indiana Supreme Court's Parenting Time Guidelines are presumed to serve "
            "the child's best interests. Standard schedule for the non-custodial parent: "
            "Alternating weekends from Friday evening to Sunday evening; one mid-week "
            "evening per week (typically 3 hours); alternating major holidays (Thanksgiving, "
            "Christmas Day, Easter, Fourth of July, Labor Day, Memorial Day); each parent's "
            "birthday and the child's birthday; and extended summer parenting time "
            "(typically 6 consecutive weeks). "
            "Age modifications: infants under 2 may have shorter visits without overnight "
            "stays initially; children over 12 may have more input into schedule. "
            "Long-distance (> 100 miles): mid-week visits replaced with additional "
            "extended weekend/holiday time. Parties may agree to different arrangements."
        ),
        "citations": ["IC 31-17-4-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "31",
            "article": "17",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-31-17-2-21-001",
        "source_id": "indiana-code-31-17",
        "section": "IC 31-17-2-21",
        "section_idx": 0,
        "content": (
            "Indiana Code § 31-17-2-21 — Relocation with child: notice requirement. "
            "A parent with primary physical custody who intends to relocate must provide "
            "written notice to the other parent at least 90 days before the proposed move. "
            "Notice must include: new address; proposed relocation date; proposed modified "
            "parenting schedule; and a statement of reasons for the relocation. "
            "The non-relocating parent may file an objection within 60 days. "
            "The relocating parent bears the burden of proving the relocation is in good "
            "faith and for a legitimate reason. The court considers: distance; hardship; "
            "educational opportunities; preserving the parent-child relationship; and "
            "history of domestic violence. Court may modify custody if relocation "
            "substantially harms the child's relationship with the other parent."
        ),
        "citations": ["IC 31-17-2-21"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "31",
            "article": "17",
            "case_type": "Family",
        },
    },
    # ── Civil Law: Tort & Contract ────────────────────────────────────────────
    {
        "chunk_id": "ic-34-11-2-1-001",
        "source_id": "indiana-code-34-11-2",
        "section": "IC 34-11-2-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-11-2-1 — Statute of limitations: personal injury. "
            "Actions for injury to person or personal property must be brought within "
            "2 years after the cause of action accrues. The cause of action accrues when "
            "the plaintiff knows or should reasonably know of the injury and its cause. "
            "Tolling: "
            "(1) Minor plaintiff (IC 34-11-6-1): SOL tolled while the plaintiff is under 18; "
            "the 2-year period begins at age 18. "
            "(2) Fraudulent concealment: SOL is tolled during any period in which the "
            "defendant fraudulently conceals the cause of action. "
            "Product liability (IC 34-20-3-1): 2-year SOL from accrual, with an absolute "
            "10-year repose from delivery of the product, regardless of when harm appears."
        ),
        "citations": ["IC 34-11-2-1", "IC 34-11-6-1", "IC 34-20-3-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "11",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-34-11-2-7-001",
        "source_id": "indiana-code-34-11-2",
        "section": "IC 34-11-2-7",
        "section_idx": 0,
        "content": (
            "Indiana statutes of limitations for contract and written instrument actions. "
            "IC 34-11-2-7: Actions on contracts, accounts, or written instruments — "
            "6 years from when the cause of action accrues (typically the date of breach). "
            "IC 26-1-3.1-118 (UCC Article 3): Actions on negotiable instruments — "
            "6 years from the due date. "
            "IC 26-1-2-725 (UCC Article 2 — Sale of Goods): 4 years from the date accrual, "
            "regardless of discovery, unless the warranty explicitly extends to the future. "
            "The contract limitations period begins on the date of breach, not when the "
            "plaintiff discovers the breach, absent fraudulent concealment. "
            "Note: IC 34-11-2-4 (written lease or specialty contracts) provides 10 years."
        ),
        "citations": ["IC 34-11-2-7", "IC 26-1-2-725"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "11",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-34-51-2-001",
        "source_id": "indiana-code-34-51-2",
        "section": "IC 34-51-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-51-2 — Comparative fault (modified 51% bar rule). "
            "Indiana follows a modified comparative fault system. A plaintiff whose fault "
            "is greater than 50% of the total fault is barred from recovery. If 50% or less, "
            "the plaintiff may recover but damages are reduced by their percentage of fault. "
            "IC 34-51-2-5: Claimant barred if fault > 50%. "
            "IC 34-51-2-6: Each defendant is only severally liable for their proportionate "
            "share; joint and several liability eliminated for defendants whose fault is "
            "less than 25% of total fault. "
            "IC 34-51-2-7: The trier of fact determines the fault percentage for each party. "
            "IC 34-51-2-8: Court reduces claimant's award by their fault percentage. "
            "Fault includes negligence, contributory negligence, assumption of risk, "
            "and misuse of a product."
        ),
        "citations": ["IC 34-51-2-5", "IC 34-51-2-6", "IC 34-51-2-8"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "51",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-34-18-14-3-001",
        "source_id": "indiana-code-34-18",
        "section": "IC 34-18-14-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-18-14-3 — Medical malpractice: damage cap and Patient's "
            "Compensation Fund (PCF). "
            "Total damages recoverable for medical malpractice are capped at $1.8 million "
            "per occurrence (for incidents on or after July 1, 2019; capped at $1.65M "
            "for prior incidents). The individual healthcare provider's liability is "
            "capped at $500,000 ($400,000 for incidents before July 1, 2019). Amounts "
            "above the individual cap are paid from the PCF. "
            "Pre-suit requirement: a claimant must file a proposed complaint with the "
            "Indiana Department of Insurance, which convenes a Medical Review Panel of "
            "three healthcare providers. The panel's opinion is admissible at trial but "
            "not binding. After the panel opinion, the claimant may proceed in court. "
            "Statute of limitations: 2 years from the date of the act, omission, or "
            "neglect (IC 34-18-7-1)."
        ),
        "citations": ["IC 34-18-14-3", "IC 34-18-7-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "18",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-34-13-3-3-001",
        "source_id": "indiana-code-34-13-3",
        "section": "IC 34-13-3-3",
        "section_idx": 0,
        "content": (
            "Indiana Tort Claims Act (IC 34-13-3-3) — notice requirement. "
            "Before suing a governmental entity for a tort, a claimant must file a notice "
            "of tort claim within 270 days of the loss (IC 34-13-3-8). For losses "
            "involving personal injury or death, the property owner must file within 180 "
            "days of discovery of the loss. "
            "Notice filed with: (for county/city) the risk management office, the city or "
            "county attorney, and the Indiana Department of Insurance when the claim "
            "involves the State. "
            "Failure to file timely notice is a jurisdictional defect that bars the lawsuit. "
            "After 90 days without a response, the claimant may file suit. If denied, "
            "the claimant must file court action within 180 days of the denial. "
            "Governmental immunity: the State and political subdivisions are immune from "
            "liability for discretionary acts (IC 34-13-3-3(7))."
        ),
        "citations": ["IC 34-13-3-3", "IC 34-13-3-8"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "13",
            "case_type": "Civil",
        },
    },
    # ── Employment Law ────────────────────────────────────────────────────────
    {
        "chunk_id": "ic-22-2-2-4-001",
        "source_id": "indiana-code-22-2-2",
        "section": "IC 22-2-2-4",
        "section_idx": 0,
        "content": (
            "Indiana Code § 22-2-2-4 — Indiana minimum wage. "
            "Indiana's minimum wage is $7.25 per hour (equal to the federal FLSA minimum). "
            "Tipped employees: minimum $2.13/hour cash wage, provided total compensation "
            "(cash + tips) averages at least $7.25/hour in each workweek. "
            "Training wage: employees under age 20 may be paid $4.25/hour during the first "
            "90 consecutive calendar days of employment with a new employer. "
            "Overtime: employees covered by the FLSA must be paid 1.5× the regular rate "
            "for hours worked over 40 in a workweek; Indiana does not impose additional "
            "overtime requirements beyond federal law. "
            "Enforcement: claims for unpaid wages may be filed with the Indiana Department "
            "of Labor (IC 22-2-2-9) or as a civil action."
        ),
        "citations": ["IC 22-2-2-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "22",
            "article": "2",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-22-3-2-2-001",
        "source_id": "indiana-code-22-3-2",
        "section": "IC 22-3-2-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 22-3-2-2 — Workers' compensation: employer liability. "
            "Employers subject to the Indiana Workers' Compensation Act must pay compensation "
            "to an employee for personal injury or death by accident arising out of and in "
            "the course of employment, without regard to fault. "
            "Coverage: most employees in Indiana including part-time and seasonal workers. "
            "Exclusions: qualifying independent contractors (6-factor test, IC 22-3-6-1(b)); "
            "certain agricultural workers; domestic service employees. "
            "Exclusive remedy (IC 22-3-2-6): workers' compensation is the exclusive remedy "
            "against the employer, precluding a separate negligence lawsuit, except for "
            "intentional torts. "
            "Employer duties: carry workers' comp insurance or be approved self-insurer; "
            "post notice of carrier; report injuries within 7 days."
        ),
        "citations": ["IC 22-3-2-2", "IC 22-3-2-6", "IC 22-3-6-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "22",
            "article": "3",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-22-3-3-10-001",
        "source_id": "indiana-code-22-3-3",
        "section": "IC 22-3-3-10",
        "section_idx": 0,
        "content": (
            "Indiana Code § 22-3-3-10 — Workers' compensation benefits. "
            "Temporary Total Disability (TTD): 2/3 of the employee's average weekly wage "
            "(AWW), capped at the state's maximum weekly benefit rate (reset annually). "
            "AWW is calculated from the 52 weeks before the accident. "
            "Permanent Total Disability (PTD): same weekly rate, payable for life. "
            "Permanent Partial Impairment (PPI): lump-sum based on a statutory schedule "
            "and the treating physician's impairment rating; 500 weeks maximum for whole "
            "body impairment at the PPD rate (2/3 of AWW). "
            "Medical benefits (IC 22-3-3-4): employer pays all reasonable and necessary "
            "medical treatment; employer selects the initial treating physician. "
            "Death benefits (IC 22-3-3-13): burial expense up to $7,500 plus weekly "
            "benefits to surviving dependents at 2/3 AWW."
        ),
        "citations": ["IC 22-3-3-10", "IC 22-3-3-4", "IC 22-3-3-13"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "22",
            "article": "3",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-22-9-1-2-001",
        "source_id": "indiana-code-22-9-1",
        "section": "IC 22-9-1-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 22-9-1-2 — Employment discrimination prohibited. "
            "Employers with 6 or more employees may not discriminate in hiring, conditions "
            "of employment, or discharge based on race, religion, color, sex, disability, "
            "national origin, or ancestry. "
            "Enforcement: claims filed with the Indiana Civil Rights Commission (ICRC) "
            "within 180 days of the discriminatory act; the ICRC investigates and may "
            "conciliate. After investigation, the complainant may file a civil lawsuit. "
            "Remedies: back pay, front pay, reinstatement, injunctive relief, attorney fees. "
            "Note: Sexual orientation and gender identity are not expressly protected under "
            "Indiana law, but federal Title VII protection (Bostock v. Clayton County, 2020) "
            "applies to employers with 15+ employees. "
            "Pregnancy (IC 22-9-5-3): job-related disabilities from pregnancy must be "
            "treated the same as other disabilities; leave and accommodations required."
        ),
        "citations": ["IC 22-9-1-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "22",
            "article": "9",
            "case_type": "Civil",
        },
    },
    # ── Property & Landlord-Tenant ────────────────────────────────────────────
    {
        "chunk_id": "ic-32-31-3-12-001",
        "source_id": "indiana-code-32-31-3",
        "section": "IC 32-31-3-12",
        "section_idx": 0,
        "content": (
            "Indiana Code § 32-31-3-12 — Security deposit: return within 45 days. "
            "Within 45 days after the rental agreement terminates and the tenant surrenders "
            "the premises, the landlord must: "
            "(1) return the full security deposit; or "
            "(2) provide an itemized written statement of damages and unpaid rent with "
            "receipts/invoices for repairs exceeding $150, and return any balance. "
            "Allowable deductions: unpaid rent; damage beyond normal wear and tear; "
            "cleaning costs if the unit was left in worse condition than move-in "
            "(accounting for normal wear). "
            "IC 32-31-3-13: If the landlord fails to return the deposit or provide the "
            "itemized statement within 45 days, the tenant may recover the entire "
            "security deposit plus a penalty equal to twice the wrongfully withheld amount. "
            "The 45-day period begins only after the tenant provides a forwarding address."
        ),
        "citations": ["IC 32-31-3-12", "IC 32-31-3-13"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "32",
            "article": "31",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-32-31-5-6-001",
        "source_id": "indiana-code-32-31-5",
        "section": "IC 32-31-5-6",
        "section_idx": 0,
        "content": (
            "Indiana Code § 32-31-5-6 — Landlord right of entry: 24-hour notice. "
            "A landlord may enter the rental unit during reasonable hours to make "
            "repairs, inspect, show to prospective tenants or buyers, or any agreed "
            "purpose, but must give at least 24 hours advance notice, except: "
            "(1) In an emergency threatening life, health, or property (no notice required); "
            "(2) When the tenant has abandoned the unit; or "
            "(3) When the tenant consents to a specific entry. "
            "A landlord who enters without proper notice may be liable for invasion of "
            "privacy and breach of the implied covenant of quiet enjoyment. "
            "Tenants may not unreasonably withhold consent to entry after proper notice. "
            "Repeated unauthorized entries may constitute constructive eviction."
        ),
        "citations": ["IC 32-31-5-6"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "32",
            "article": "31",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-6-1-1-12-37-001",
        "source_id": "indiana-code-6-1.1",
        "section": "IC 6-1.1-12-37",
        "section_idx": 0,
        "content": (
            "Indiana Code § 6-1.1-12-37 — Homestead standard deduction (property tax). "
            "Owner-occupants of a primary residence may claim the homestead standard "
            "deduction, which reduces the net assessed value for property tax calculation. "
            "For the 2025 assessment year: deduction equals 60% of assessed value, capped "
            "at $48,000. "
            "Supplemental homestead deduction (IC 6-1.1-12-37.5): additional deduction of "
            "35% on net AV up to $600,000 and 25% on net AV exceeding $600,000. "
            "Combined, the two deductions reduce property tax bills by 60–70% for most "
            "owner-occupied homes. "
            "Application: file with the county auditor by January 5 of the year the "
            "deduction is to apply. The deduction continues until the ownership or use "
            "changes. Surviving spouses may continue the deduction."
        ),
        "citations": ["IC 6-1.1-12-37", "IC 6-1.1-12-37.5"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "6",
            "article": "1.1",
            "case_type": "Tax",
        },
    },
    # ── Indiana Constitutional Rights ─────────────────────────────────────────
    {
        "chunk_id": "in-const-art1-sec11-001",
        "source_id": "indiana-constitution-art1",
        "section": "Indiana Const. Art. 1, Sec. 11",
        "section_idx": 0,
        "content": (
            "Indiana Constitution Article 1, Section 11 — Search and seizure. "
            "'The right of the people to be secure in their persons, houses, papers, and "
            "effects, against unreasonable search or seizure, shall not be violated; and "
            "no warrant shall issue, but upon probable cause, supported by oath or "
            "affirmation, and particularly describing the place to be searched, and the "
            "person or thing to be seized.' "
            "Indiana courts interpret Section 11 independently from the Fourth Amendment "
            "and may provide broader protection. The Litchfield balancing test (Litchfield v. "
            "State, 824 N.E.2d 356, Ind. 2005) evaluates: (1) degree of concern or knowledge "
            "a violation has occurred; (2) degree of intrusion on the citizen; "
            "(3) extent of law enforcement needs. Exclusionary rule applies to Section 11 "
            "violations as a matter of Indiana constitutional law."
        ),
        "citations": ["Indiana Const. Art. 1, § 11"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "constitution",
            "title": "1",
            "article": "1",
        },
    },
    {
        "chunk_id": "in-const-art1-sec13-001",
        "source_id": "indiana-constitution-art1",
        "section": "Indiana Const. Art. 1, Sec. 13",
        "section_idx": 0,
        "content": (
            "Indiana Constitution Article 1, Section 13 — Right to counsel and fair trial. "
            "'In all criminal prosecutions, the accused shall have the right to a public "
            "trial, by an impartial jury, in the county in which the offense shall have "
            "been committed; to be heard by himself and counsel; to demand the nature and "
            "cause of the accusation against him, and to have a copy thereof; to meet the "
            "witnesses face to face, and to have compulsory process for obtaining witnesses "
            "in his favor.' "
            "Indiana's right to counsel attaches at the first formal judicial proceeding "
            "(typically the initial hearing). An indigent defendant is entitled to appointed "
            "counsel for any offense carrying a potential term of imprisonment "
            "(Argersinger v. Hamlin principle applied in Indiana). "
            "Waiver of counsel must be knowing, voluntary, and intelligent."
        ),
        "citations": ["Indiana Const. Art. 1, § 13"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "constitution",
            "title": "1",
            "article": "1",
        },
    },
    {
        "chunk_id": "in-const-art1-sec14-001",
        "source_id": "indiana-constitution-art1",
        "section": "Indiana Const. Art. 1, Sec. 14",
        "section_idx": 0,
        "content": (
            "Indiana Constitution Article 1, Section 14 — Double jeopardy. "
            "'No person shall be put in jeopardy twice for the same offense.' "
            "Indiana interprets Section 14 more broadly than the Fifth Amendment federal "
            "double jeopardy clause. Indiana uses the 'actual evidence' test from "
            "Richardson v. State (717 N.E.2d 32, Ind. 1999): separate convictions "
            "violate double jeopardy if there is a reasonable possibility the jury used "
            "the same evidence to establish the essential elements of both offenses. "
            "This differs from the federal Blockburger 'same elements' test. "
            "Example: A separate battery conviction is typically barred when the battery "
            "is the same act that elevates a lower charge to a higher-level offense. "
            "Jeopardy attaches: in a jury trial when the jury is sworn; in a bench trial "
            "when the first witness is sworn."
        ),
        "citations": ["Indiana Const. Art. 1, § 14"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "constitution",
            "title": "1",
            "article": "1",
        },
    },
    {
        "chunk_id": "in-const-art1-sec18-001",
        "source_id": "indiana-constitution-art1",
        "section": "Indiana Const. Art. 1, Sec. 18",
        "section_idx": 0,
        "content": (
            "Indiana Constitution Article 1, Section 18 — Bail and criminal penalties. "
            "'Excessive bail shall not be required. Excessive fines shall not be imposed. "
            "Cruel and unusual punishments shall not be inflicted. All penalties shall be "
            "proportioned to the nature of the offense.' "
            "Pretrial release (IC 35-33-8-4): courts may release on personal recognizance, "
            "unsecured appearance bond, monetary bail, electronic monitoring, or supervised "
            "conditions. Bail may be denied for murder, treason, or if the defendant is a "
            "flight risk or danger to the community. "
            "Under Indiana Supreme Court Administrative Rule 26 (effective 2020), courts "
            "must use a validated risk assessment tool (Indiana Risk Assessment System — "
            "IRAS) to guide pretrial release decisions."
        ),
        "citations": ["Indiana Const. Art. 1, § 18", "IC 35-33-8-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "constitution",
            "title": "1",
            "article": "1",
        },
    },
    # ── Expungement (IC 35-38-9) ──────────────────────────────────────────────
    {
        "chunk_id": "ic-35-38-9-1-001",
        "source_id": "indiana-code-35-38-9",
        "section": "IC 35-38-9-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-38-9-1 — Expungement of arrest records (no conviction). "
            "A person who was arrested but not convicted may petition the court that would "
            "have had jurisdiction to expunge arrest records. Eligibility: no charges filed, "
            "charges dismissed, or conviction vacated on appeal. "
            "Waiting period: 1 year after the arrest date, or immediately if all charges "
            "were dismissed with prejudice or the person was acquitted. "
            "Effect of expungement: the court and law enforcement records are sealed; the "
            "expunged arrest may not be disclosed to non-criminal justice entities. "
            "The person may lawfully state they were not arrested for the expunged matter "
            "on applications for employment, education, or housing. "
            "An expunged arrest record is accessible only to criminal justice agencies and "
            "certain licensing boards (IC 35-38-9-10(b))."
        ),
        "citations": ["IC 35-38-9-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-38-9-2-001",
        "source_id": "indiana-code-35-38-9",
        "section": "IC 35-38-9-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-38-9-2 — Expungement of misdemeanor convictions. "
            "A person convicted of a Class A, B, or C misdemeanor (or Level 6 / Class D "
            "felony treated as a misdemeanor) may petition for expungement. "
            "Waiting period: 5 years after the date of conviction. "
            "Requirements: no criminal charges pending; no petitions for expungement "
            "within 3 years; all fines, fees, and restitution paid in full. "
            "Effect: the conviction records are sealed by the court; background check "
            "services may not disclose the conviction; the person may lawfully deny the "
            "conviction on private employer applications. "
            "IC 35-38-9-9(f): a person who has an expunged record sealed is not required to "
            "disclose the conviction to a private employer; a private employer may not use "
            "the sealed conviction as a basis for refusing to hire or for termination. "
            "Exception: certain licensing boards and criminal justice employment may still "
            "access sealed records."
        ),
        "citations": ["IC 35-38-9-2", "IC 35-38-9-9"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-38-9-3-001",
        "source_id": "indiana-code-35-38-9",
        "section": "IC 35-38-9-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-38-9-3 — Expungement of Level 6 felony convictions. "
            "A person convicted of a Level 6 felony (Class D felony under prior law) may "
            "petition for expungement under IC 35-38-9-3. "
            "Waiting period: 8 years after the date of conviction OR 3 years after "
            "completion of sentence (whichever is later). "
            "Requirements: no criminal charges pending; all fines, fees, and restitution "
            "paid; no prior expungement petitions denied within 3 years; and the "
            "prosecutor does not object (or the court overrides the objection with findings). "
            "The court has discretion to deny an expungement petition even if the "
            "petitioner meets all requirements if the interests of justice would not be "
            "served. If granted, the conviction records are sealed (not destroyed). "
            "Convictions for Level 6 felonies that are sex or violent offenses are not "
            "eligible (IC 35-38-9-8)."
        ),
        "citations": ["IC 35-38-9-3", "IC 35-38-9-8"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-38-9-4-001",
        "source_id": "indiana-code-35-38-9",
        "section": "IC 35-38-9-4",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-38-9-4 — Expungement of Level 1 through Level 5 felony "
            "convictions. "
            "A person convicted of a Level 1, 2, 3, 4, or 5 felony (other than those "
            "listed as ineligible under IC 35-38-9-8) may petition for expungement. "
            "Waiting period: 10 years after the date of conviction OR 5 years after "
            "completion of sentence (whichever is later). "
            "Additional requirement: the prosecutor must consent (or the court may grant "
            "over objection if the court makes written findings that the person has been "
            "rehabilitated and the interests of justice would be served). "
            "Prosecutor's consent is required for Level 1–4 felonies; discretionary for "
            "Level 5 felonies. "
            "Effect: records are marked 'expunged' and restricted to a limited set of "
            "agencies; the person may lawfully deny the conviction on private employer "
            "applications (IC 35-38-9-9(f))."
        ),
        "citations": ["IC 35-38-9-4", "IC 35-38-9-9"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-38-9-8-001",
        "source_id": "indiana-code-35-38-9",
        "section": "IC 35-38-9-8",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-38-9-8 — Offenses ineligible for expungement. "
            "The following convictions may NOT be expunged under Indiana law: "
            "(1) Murder (IC 35-42-1-1); "
            "(2) Sex or violent offenses requiring registration on the SVOR "
            "(IC 11-8-8) — rape, child molesting, sexual misconduct with a minor, "
            "sex trafficking, and similar offenses; "
            "(3) Any offense resulting in serious bodily injury to another person that "
            "is a Level 3 or higher felony; "
            "(4) Official misconduct (IC 35-44.1-1-1) by a public servant; "
            "(5) Perjury (IC 35-44.1-2-1); "
            "(6) Human trafficking offenses; "
            "(7) Kidnapping; "
            "(8) Any conviction for which the record-keeper is the Department of Correction "
            "for a non-expungable offense. "
            "A person who has been convicted of murder, a sex crime requiring registration, "
            "or an offense resulting in the homicide of another person is permanently "
            "ineligible to apply for expungement of any Indiana conviction."
        ),
        "citations": ["IC 35-38-9-8", "IC 11-8-8"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-38-9-10-001",
        "source_id": "indiana-code-35-38-9",
        "section": "IC 35-38-9-10",
        "section_idx": 0,
        "content": (
            "Indiana Code § 35-38-9-10 — Expungement petition procedure. "
            "To petition for expungement: "
            "(1) File a verified petition in the sentencing court (or court with "
            "jurisdiction over county of conviction); "
            "(2) State the conviction(s) to be expunged, case numbers, dates; "
            "(3) Attach proof that all fines, fees, court costs, and restitution have "
            "been paid; "
            "(4) Attach proof that no criminal charges are pending; "
            "(5) Serve the prosecutor of the county; "
            "The court shall set a hearing date. The prosecutor may object or consent. "
            "If no objection within 30 days, the court may grant the petition without a "
            "hearing (for misdemeanors and Class D / Level 6 felonies). "
            "For Level 1–5 felonies, a hearing is required. "
            "A person may file only ONE expungement petition in their lifetime "
            "(IC 35-38-9-9(g)) — all eligible convictions must be included in a single "
            "petition. Once an expungement petition is denied, the person must wait "
            "3 years before re-petitioning."
        ),
        "citations": ["IC 35-38-9-10", "IC 35-38-9-9"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    {
        "chunk_id": "ic-35-38-9-effect-001",
        "source_id": "indiana-code-35-38-9",
        "section": "IC 35-38-9-9",
        "section_idx": 0,
        "content": (
            "Indiana expungement effect on employment and background checks "
            "(IC 35-38-9-9). "
            "Once conviction records are expunged (sealed): "
            "— Private employers may not consider the sealed conviction in hiring, "
            "termination, or promotion decisions; it is unlawful employment discrimination "
            "to deny a job solely because of an expunged record (IC 35-38-9-10(b)(3)). "
            "— The person may lawfully state on a private employer application that they "
            "have no prior conviction for the expunged offense (IC 35-38-9-9(f)). "
            "— Commercial background check services must suppress the expunged record. "
            "— Law enforcement, criminal justice agencies, the Department of Child "
            "Services (DCS), certain professional licensing boards (medicine, law, "
            "education), and agencies employing persons working with children or "
            "vulnerable adults retain access to sealed records. "
            "— Federal background checks (NICS for firearms, federal employment) are NOT "
            "affected by Indiana expungement — the FBI's records are separate. "
            "— Gun rights: an expungement of a felony conviction does NOT automatically "
            "restore federal firearms rights (18 U.S.C. § 922(g)(1)); a separate "
            "restoration petition may be needed under IC 35-47-4-7."
        ),
        "citations": ["IC 35-38-9-9", "IC 35-47-4-7"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "35",
            "article": "38",
            "case_type": "Criminal",
        },
    },
    # ── IC 29-1 — Probate / Estate Law ──────────────────────────────────────
    {
        "chunk_id": "ic-29-1-2-1-001",
        "source_id": "indiana-code-29-1",
        "section": "IC 29-1-2-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 29-1-2-1 — Intestate succession: share of surviving spouse. "
            "When a person dies without a valid will, their estate passes by intestate "
            "succession. The surviving spouse's share depends on who else survives: "
            "(1) Spouse and children who are children of both the decedent and the spouse — "
            "spouse takes one-half; children share the other half equally. "
            "(2) Spouse and children who are NOT all children of the surviving spouse — "
            "spouse takes one-quarter; the remaining three-quarters goes to the children. "
            "(3) Spouse and no children or issue — spouse takes the entire estate. "
            "(4) No surviving spouse — entire estate passes to the decedent's children "
            "equally, or by right of representation to their descendants if a child is deceased."
        ),
        "citations": ["IC 29-1-2-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "29",
            "article": "1",
            "case_type": "Probate",
        },
    },
    {
        "chunk_id": "ic-29-1-2-3-001",
        "source_id": "indiana-code-29-1",
        "section": "IC 29-1-2-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 29-1-2-3 — Intestate succession: collateral heirs. "
            "If no spouse or children survive, the decedent's estate passes in order to: "
            "(1) parents of the decedent in equal shares; "
            "(2) brothers and sisters of the decedent and the descendants of deceased "
            "brothers and sisters by right of representation; "
            "(3) grandparents, then aunts and uncles if both grandparents are deceased; "
            "(4) more remote kindred as determined by the degree of kinship. "
            "If no kindred can be located within a reasonable time, the estate escheats "
            "to the State of Indiana (IC 32-34-1). "
            "Right of representation means a deceased heir's share passes to their living "
            "descendants, divided equally among them."
        ),
        "citations": ["IC 29-1-2-3", "IC 32-34-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "29",
            "article": "1",
            "case_type": "Probate",
        },
    },
    {
        "chunk_id": "ic-29-1-7-1-001",
        "source_id": "indiana-code-29-1",
        "section": "IC 29-1-7-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 29-1-7-1 — Requirements for a valid will. "
            "A will is valid in Indiana only if it is: "
            "(1) in writing (typed or handwritten); "
            "(2) signed by the testator, or signed by another person in the testator's "
            "conscious presence and at their express direction; "
            "(3) attested and subscribed in the presence of the testator by at least "
            "two (2) competent witnesses who witness the testator's signing or "
            "acknowledgment. Witnesses should be disinterested — a beneficiary who "
            "also witnesses may be forced to choose between their bequest and their "
            "witness role (interested witness rule). A will that does not meet these "
            "requirements is void. Indiana does NOT recognize holographic (handwritten "
            "but unwitnessed) wills made within the state, though foreign holographic "
            "wills may be recognized under comity."
        ),
        "citations": ["IC 29-1-7-1", "IC 29-1-7-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "29",
            "article": "1",
            "case_type": "Probate",
        },
    },
    {
        "chunk_id": "ic-29-1-7-17-001",
        "source_id": "indiana-code-29-1",
        "section": "IC 29-1-7-17",
        "section_idx": 0,
        "content": (
            "Indiana Code § 29-1-7-17 — Will contest: time limit. "
            "An action to contest the validity of a will admitted to probate must be "
            "filed within five (5) months from the date the will is admitted to probate "
            "in an Indiana court. This is a statute of limitations — once the five-month "
            "period expires, the right to contest the will is permanently barred, even "
            "if grounds for contest (such as undue influence, fraud, or lack of testamentary "
            "capacity) later become known. "
            "Grounds to contest a will include: lack of testamentary capacity (testator "
            "did not understand the nature of a will, their property, or their heirs), "
            "undue influence, fraud, forgery, or that the will was revoked prior to death. "
            "Interested parties who may contest include heirs at law and prior-will beneficiaries."
        ),
        "citations": ["IC 29-1-7-17"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "29",
            "article": "1",
            "case_type": "Probate",
        },
    },
    {
        "chunk_id": "ic-29-1-10-1-001",
        "source_id": "indiana-code-29-1",
        "section": "IC 29-1-10-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 29-1-10-1 — Personal representative: appointment and duties. "
            "A personal representative (executor/administrator) is appointed by the probate "
            "court to administer the decedent's estate. Their duties include: "
            "(1) File an inventory of estate assets with the court within two (2) months "
            "of appointment; "
            "(2) Notify creditors by publication for three (3) consecutive weeks in a "
            "local newspaper; creditors have nine (9) months from death or three (3) months "
            "from notice to file claims, whichever is later; "
            "(3) Pay valid debts, taxes (including federal estate tax if the estate exceeds "
            "the federal exemption threshold), and administration expenses; "
            "(4) Distribute remaining assets to beneficiaries per the will or intestate law; "
            "(5) File a final accounting with the court and petition for discharge. "
            "The personal representative has a fiduciary duty to all beneficiaries and "
            "creditors. Breach of fiduciary duty may result in personal liability."
        ),
        "citations": ["IC 29-1-10-1", "IC 29-1-14-1", "IC 29-1-16-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "29",
            "article": "1",
            "case_type": "Probate",
        },
    },
    {
        "chunk_id": "ic-29-1-4-1-001",
        "source_id": "indiana-code-29-1",
        "section": "IC 29-1-4-1",
        "section_idx": 0,
        "content": (
            "Indiana Code § 29-1-4-1 — Surviving spouse and children: exempt property allowance. "
            "The surviving spouse of a decedent, or the decedent's children if there is no "
            "surviving spouse, are entitled to receive from the estate exempt property with "
            "a total value of up to $25,000 (the exempt property allowance). "
            "This allowance has priority over unsecured debts of the estate — meaning it is "
            "paid before general creditors are satisfied. If the estate has insufficient "
            "assets to pay the allowance in full, all available assets go to the surviving "
            "spouse or children to the extent of the allowance. The allowance is in addition "
            "to any share the surviving spouse or children receive under the will or by "
            "intestate succession. Property that qualifies includes household goods, "
            "furniture, automobiles, and personal effects."
        ),
        "citations": ["IC 29-1-4-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "29",
            "article": "1",
            "case_type": "Probate",
        },
    },
    # ── IC 33-28-3 — Small Claims Court ─────────────────────────────────────
    {
        "chunk_id": "ic-33-28-3-2-001",
        "source_id": "indiana-code-33-28-3",
        "section": "IC 33-28-3-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 33-28-3 — Small Claims Court: overview and informal procedure. "
            "Indiana's small claims courts are divisions of the circuit, superior, and "
            "township courts designed to provide a quick, informal, and inexpensive forum "
            "for resolving minor civil disputes. "
            "Key features: (1) Relaxed evidence rules — the judge may question parties "
            "and witnesses directly to develop the facts; (2) Parties may represent "
            "themselves without an attorney; (3) Proceedings are not recorded verbatim "
            "as a rule; (4) Equitable claims (injunctions, title to real property) are "
            "NOT within small claims jurisdiction; (5) Small claims judgments are just "
            "as enforceable as any other civil judgment — through wage garnishment, bank "
            "levies, and judgment liens on real estate. "
            "Small claims is ideal for: landlord-tenant disputes (security deposits), "
            "unpaid loans between individuals, minor property damage, and unpaid services."
        ),
        "citations": ["IC 33-28-3-2"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "33",
            "article": "28",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-33-28-3-4-001",
        "source_id": "indiana-code-33-28-3",
        "section": "IC 33-28-3-4",
        "section_idx": 0,
        "content": (
            "Indiana Code § 33-28-3-4 — Small Claims Court: jurisdictional limit. "
            "Indiana township small claims courts have jurisdiction over civil claims "
            "where the amount in controversy does not exceed $8,000, exclusive of "
            "interest and costs. "
            "City and town courts may have a higher limit of up to $10,000 depending "
            "on their enabling statute. "
            "If your claim exceeds the applicable limit, you must file in the circuit "
            "or superior court (general civil division). You may voluntarily reduce your "
            "claim to bring it within the small claims limit, but you permanently waive "
            "the excess amount. "
            "Claims that cannot be heard in small claims court regardless of amount: "
            "title to real property, foreclosure of any lien, injunctions, class actions, "
            "and claims against the government requiring sovereign immunity analysis."
        ),
        "citations": ["IC 33-28-3-4"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "33",
            "article": "28",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-33-28-3-5-001",
        "source_id": "indiana-code-33-28-3",
        "section": "IC 33-28-3-5",
        "section_idx": 0,
        "content": (
            "Indiana Code § 33-28-3-5 — Small Claims Court: filing and service. "
            "To start a small claims case in Indiana: "
            "(1) Obtain a Notice of Claim form from the small claims clerk; "
            "(2) Complete the form stating the defendant's name and address, the basis "
            "of the claim (what happened), and the amount demanded; "
            "(3) File with the clerk and pay the filing fee (varies by court, "
            "typically $35–$95 for claims under $1,500 and up to $120 for larger claims); "
            "(4) Service of notice: the clerk mails the notice to the defendant by "
            "certified mail, return receipt requested, and also by first-class mail. "
            "If certified mail is unclaimed, personal service by a constable or process "
            "server is required. "
            "Service must be completed at least ten (10) days before the scheduled hearing. "
            "If the defendant does not appear, a default judgment may be entered. "
            "If the plaintiff does not appear, the case is dismissed."
        ),
        "citations": ["IC 33-28-3-5", "IC 33-28-3-6"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "33",
            "article": "28",
            "case_type": "Civil",
        },
    },
    {
        "chunk_id": "ic-33-28-3-9-001",
        "source_id": "indiana-code-33-28-3",
        "section": "IC 33-28-3-9",
        "section_idx": 0,
        "content": (
            "Indiana Code § 33-28-3-9 — Small Claims Court: judgment and appeal. "
            "After the small claims hearing, the court enters a judgment for or against "
            "the plaintiff. The judgment specifies the amount awarded plus court costs. "
            "Collecting the judgment: the winner (judgment creditor) may collect by: "
            "(1) wage garnishment — garnish up to 25% of the defendant's disposable earnings; "
            "(2) bank account levy — freeze and seize funds in the defendant's bank accounts; "
            "(3) judgment lien — file in the county recorder's office, which attaches to all "
            "real property the defendant owns in that county. "
            "Appeal: either party may appeal the small claims judgment to the circuit or "
            "superior court within thirty (30) days of the judgment. The appeal is a de novo "
            "trial — an entirely new hearing before a judge, not a review of the small claims "
            "judgment. The appealing party must pay a new, higher filing fee. "
            "A judgment not appealed within 30 days is final and may be enforced immediately."
        ),
        "citations": ["IC 33-28-3-9", "IC 34-25-3-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "33",
            "article": "28",
            "case_type": "Civil",
        },
    },
    # ── IC 34-26-5 — Protective Orders (Domestic Violence) ──────────────────
    {
        "chunk_id": "ic-34-26-5-2-001",
        "source_id": "indiana-code-34-26-5",
        "section": "IC 34-26-5-2",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-26-5-2 — Protective orders: who may petition. "
            "The following persons may petition a court for a protective order: "
            "(1) A person who is or has been a victim of domestic violence committed "
            "by a family or household member; "
            "(2) A person who is or has been the victim of stalking or a sex offense; "
            "(3) A parent or guardian petitioning on behalf of a minor. "
            '"Family or household member" is broadly defined and includes: current or '
            "former spouses, persons who have a child in common, persons related by "
            "blood or marriage (including step-relationships), persons who currently "
            "live together or previously lived together, and persons who are or were "
            "in a dating relationship (including same-sex relationships). "
            "Protective orders under IC 34-26-5 are civil in nature. A no-contact order "
            "issued as part of a criminal case is separate and governed by IC 35-33-8-3.6."
        ),
        "citations": ["IC 34-26-5-2", "IC 34-26-5-1"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "26",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-34-26-5-9-001",
        "source_id": "indiana-code-34-26-5",
        "section": "IC 34-26-5-9",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-26-5-9 — Ex parte protective order. "
            "A court may issue a protective order on an ex parte basis — without prior "
            "notice to the respondent — when the petition and supporting information "
            "demonstrate that immediate and irreparable injury, loss, or damage will "
            "result if the respondent is notified before the order is entered. "
            "Procedure: (1) The petitioner files a sworn petition the same day; "
            "(2) The judge reviews the petition without a hearing, often within hours; "
            "(3) If granted, the ex parte order is immediately effective upon issuance; "
            "(4) The respondent is served with the order and notice of a full hearing. "
            "A full hearing must be scheduled within thirty (30) days of the ex parte order. "
            "At the full hearing, both parties may present evidence. The ex parte order "
            "remains in effect until the full hearing or until the court modifies it. "
            "Ex parte orders are available without the respondent's attorney present "
            "specifically because requiring notice could endanger the petitioner."
        ),
        "citations": ["IC 34-26-5-9", "IC 34-26-5-10"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "26",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-34-26-5-3-001",
        "source_id": "indiana-code-34-26-5",
        "section": "IC 34-26-5-3",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-26-5-3 — Protective order: scope and provisions. "
            "An Indiana protective order may include any or all of the following: "
            "(1) Prohibit the respondent from threatening, harassing, contacting, or "
            "communicating with the petitioner directly or indirectly; "
            "(2) Order the respondent to vacate a shared residence (even if the respondent "
            "owns or is on the lease); "
            "(3) Prohibit the respondent from entering the petitioner's residence, workplace, "
            "school, or any place specified in the order; "
            "(4) Order the respondent to stay at least a specified distance (commonly "
            "500 feet to 1,000 feet) from the petitioner at all times; "
            "(5) Award temporary custody of minor children to the petitioner; "
            "(6) Order temporary child support during the period of the order; "
            "(7) Order the respondent to participate in counseling or batterer's "
            "intervention programs. "
            "A protective order is effective statewide and must be honored by all Indiana "
            "law enforcement agencies (IC 34-26-5-19). Orders entered in other states are "
            "recognized and enforceable in Indiana under the Violence Against Women Act."
        ),
        "citations": ["IC 34-26-5-3", "IC 34-26-5-19"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "26",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-34-26-5-14-001",
        "source_id": "indiana-code-34-26-5",
        "section": "IC 34-26-5-14",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-26-5-14 — Protective order: firearms surrender. "
            "When a court issues a protective order under IC 34-26-5, it must order the "
            "respondent to surrender all firearms, ammunition, and deadly weapons. "
            "The respondent must surrender them to a law enforcement agency or a federally "
            "licensed firearms dealer within 24 hours of service of the order. "
            "The respondent must file a receipt with the court within 48 hours confirming "
            "the surrender. Failure to surrender firearms as required is a Level 6 felony. "
            "Federal law independently prohibits any person subject to a qualifying "
            "domestic violence protective order from possessing firearms or ammunition "
            "(18 U.S.C. § 922(g)(8)). This federal prohibition applies regardless of "
            "whether the state order specifically requires surrender. "
            "Surrendered firearms are held by law enforcement during the period the "
            "protective order is in effect and returned if the order expires or is vacated."
        ),
        "citations": ["IC 34-26-5-14", "IC 34-26-5-15"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "26",
            "case_type": "Family",
        },
    },
    {
        "chunk_id": "ic-34-26-5-15-001",
        "source_id": "indiana-code-34-26-5",
        "section": "IC 34-26-5-15",
        "section_idx": 0,
        "content": (
            "Indiana Code § 34-26-5-15 — Violation of a protective order: criminal penalties. "
            "A person who knowingly or intentionally violates a protective order issued "
            "under IC 34-26-5 commits a criminal offense: "
            "(1) Class A misdemeanor: first violation, no physical contact or prior convictions. "
            "(2) Level 6 felony: (a) the respondent has a prior unrelated conviction for "
            "a protective order violation within the preceding five years; or (b) the "
            "violation was committed in the physical presence of a child under 16 years of age. "
            "(3) Level 5 felony: the violation results in bodily injury to the protected person. "
            "(4) Level 2 felony: the violation results in serious bodily injury or death. "
            "Law enforcement must arrest a person for a protective order violation if there "
            "is probable cause to believe the violation occurred, even if no warrant exists "
            "(IC 34-26-5-16 mandatory arrest provision). "
            "Contempt of court is an additional remedy — the respondent may be jailed for "
            "civil contempt regardless of the criminal charge."
        ),
        "citations": ["IC 34-26-5-15", "IC 34-26-5-16"],
        "metadata": {
            "court": "indiana",
            "jurisdiction": "Indiana",
            "type": "statute",
            "title": "34",
            "article": "26",
            "case_type": "Family",
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
            row = cur.fetchone()
            count = row[0] if row else 0
            print(f"✅ Seeded {len(CHUNKS)} chunks. Total in DB: {count}")


if __name__ == "__main__":
    main()
