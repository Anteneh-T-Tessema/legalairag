# Indiana Courts Technology Ecosystem

**Project**: IndyLeg — Indiana Legal AI RAG Platform
**Version**: 0.7.0 | **Date**: April 2026

---

## Table of Contents

- [1. Ecosystem Overview](#1-ecosystem-overview)
- [2. Case Management & E-Filing](#2-case-management--e-filing)
- [3. Public-Facing Data Portals](#3-public-facing-data-portals)
- [4. Criminal Justice & Public Safety Systems](#4-criminal-justice--public-safety-systems)
- [5. Court Administration Tools](#5-court-administration-tools)
- [6. External Legal Data Sources](#6-external-legal-data-sources)
- [7. IndyLeg Integration Map](#7-indyleg-integration-map)
- [8. Data Flow: Source → IndyLeg Pipeline](#8-data-flow-source--indyleg-pipeline)
- [9. Access & Licensing Notes](#9-access--licensing-notes)
- [10. Contact & Governance](#10-contact--governance)

---

## 1. Ecosystem Overview

The Indiana Judicial Branch operates a comprehensive technology ecosystem managed by the **Indiana Office of Court Technology (OCT)**. IndyLeg integrates with the publicly accessible portions of this ecosystem to power its Legal RAG pipeline.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                     INDIANA COURTS TECHNOLOGY ECOSYSTEM                     │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │   Odyssey    │  │  E-Filing   │  │  mycase     │  │ public.courts   │   │
│  │  Case Mgmt   │  │  (Tyler)    │  │  .in.gov    │  │   .in.gov       │   │
│  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘   │
│         │                 │                 │                   │            │
│         ▼                 ▼                 ▼                   ▼            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Statewide Data Hub                                │   │
│  └───────────────────────────┬──────────────────────────────────────────┘   │
│                              │                                              │
│    ┌──────────┬──────────┬───┴────┬──────────┬──────────┬───────────┐      │
│    ▼          ▼          ▼        ▼          ▼          ▼           ▼      │
│  INcite   Protected   Jury   Statistics  Tax       Marriage    Supervised  │
│  Extranet  Orders    Mgmt   Reporting  Warrants  Licenses    Release     │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │        Criminal Justice / Public Safety Integration Layer           │   │
│  │  Risk Assessment · Abstract of Judgment · PSI · DCS Juvenile       │   │
│  │  Home Detention · E-Tickets · Commercial Driver · Mental Health    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Case Management & E-Filing

### 2.1 Odyssey Case Management System

| Attribute | Detail |
|---|---|
| **Vendor** | Tyler Technologies |
| **Scope** | Statewide — all 92 Indiana counties |
| **Function** | Master case management, docketing, scheduling, document management |
| **Data** | Case records, parties, events, judges, hearings, dispositions |
| **Integration** | IndyLeg reads case metadata and documents via the public API layer |
| **URL** | Internal to courts; public data exposed via `mycase.in.gov` and `public.courts.in.gov` |

Odyssey is the authoritative system of record for all Indiana court cases. Every other public-facing portal is effectively a read view on Odyssey data.

### 2.2 Electronic Filing (E-Filing)

| Attribute | Detail |
|---|---|
| **Scope** | Statewide mandatory e-filing for attorneys; optional for self-represented litigants |
| **Function** | Case initiation, document filing, service of process |
| **Data** | Filed documents (complaints, motions, orders), filing timestamps, acceptance/rejection status |
| **Integration** | E-filed documents flow into Odyssey → IndyLeg ingests via `public.courts.in.gov` API |
| **URL** | `https://efile.incourts.gov/` (filer portal) |

**IndyLeg relevance**: E-filing is the primary entry point for new documents. Near-real-time ingestion monitors newly accepted filings through the public API.

### 2.3 INcite — Indiana Court IT Extranet

| Attribute | Detail |
|---|---|
| **URL** | `https://mycourts.in.gov/` |
| **Scope** | Internal — court staff, clerks, judges |
| **Function** | Secure portal for court staff tools, reports, administration |
| **Integration** | Not directly accessible to IndyLeg (requires court staff credentials) |

**IndyLeg relevance**: Indirect — INcite internal data eventually surfaces in public-facing portals.

---

## 3. Public-Facing Data Portals

These are IndyLeg's primary data sources — publicly accessible without special credentials.

### 3.1 mycase.in.gov

| Attribute | Detail |
|---|---|
| **URL** | `https://mycase.in.gov/` |
| **Function** | Public case search for all 92 counties |
| **Data** | Case number, parties, charges, case type, events, scheduled hearings |
| **Access** | Open public access — no login required for basic search |
| **Integration** | **Active** — IndyLeg scrapes/queries for case metadata enrichment |
| **Rate Limits** | Moderate — respect robots.txt and request throttling |

**Key data points for RAG**:
- Party names and case roles
- Case type classification (Civil, Criminal, Family, Juvenile, etc.)
- Filing dates and case timeline events
- Hearing schedules and courtroom assignments
- Judge assignments

### 3.2 public.courts.in.gov

| Attribute | Detail |
|---|---|
| **URL** | `https://public.courts.in.gov/` |
| **Function** | Official public records portal; published opinions, orders, rules |
| **Data** | Appellate opinions, supreme court orders, court rules, administrative orders |
| **Access** | Open public access |
| **Integration** | **Primary** — IndyLeg's main Odyssey API client (`indiana_courts.py`) |

**Key data points for RAG**:
- Full-text appellate opinions (Indiana Supreme Court, Court of Appeals)
- Published court rules and amendments
- Administrative orders (COVID protocols, local rules, etc.)
- Docket sheets and case summaries

### 3.3 Text Message Reminder System

| Attribute | Detail |
|---|---|
| **Function** | Court date reminders via SMS for litigants |
| **Integration** | Not applicable — no legal document content |

### 3.4 Trial Court Remote Video Hearings

| Attribute | Detail |
|---|---|
| **Function** | Virtual hearing infrastructure (post-COVID) |
| **Integration** | Hearing metadata (dates, participants) flows through Odyssey → IndyLeg can ingest scheduling data |

---

## 4. Criminal Justice & Public Safety Systems

These systems contain structured data relevant to fraud detection, criminal case research, and risk assessment.

### 4.1 Protection Order Registry

| Attribute | Detail |
|---|---|
| **Function** | Statewide registry of protective/restraining orders |
| **Data** | Active protection orders, petitioner/respondent, expiration dates, conditions |
| **Integration** | **Planned** — relevant for family law research and fraud detection (identity reuse across protection orders) |
| **Access** | Public registry; courts.in.gov portal |

### 4.2 Supervised Release System

| Attribute | Detail |
|---|---|
| **Function** | Tracking individuals on probation, parole, community corrections |
| **Data** | Release conditions, supervision terms, compliance status |
| **Integration** | **Future** — restricted access; relevant for criminal justice research |

### 4.3 Risk Assessment

| Attribute | Detail |
|---|---|
| **Function** | Evidence-based pretrial and sentencing risk assessment tools |
| **Data** | Risk scores, assessed factors, recommended conditions |
| **Integration** | **Future** — structured data for criminal justice research patterns |

### 4.4 Abstract of Judgment

| Attribute | Detail |
|---|---|
| **Function** | Official record of court judgments (sentencing, fines, restitution) |
| **Data** | Sentence terms, fines, restitution amounts, judgment dates |
| **Integration** | **Planned** — valuable for case outcome analysis and sentencing research |

### 4.5 Presentence Investigation (PSI)

| Attribute | Detail |
|---|---|
| **Function** | Reports prepared for judges before sentencing |
| **Data** | Defendant background, criminal history, victim impact, recommendations |
| **Integration** | **Restricted** — confidential; not for public RAG ingestion |
| **Note** | PSI content is sealed under IC § 35-38-1-13; IndyLeg excludes this data |

### 4.6 DCS Juvenile Probation System

| Attribute | Detail |
|---|---|
| **Function** | Department of Child Services juvenile probation tracking |
| **Data** | Juvenile case records, probation conditions, compliance |
| **Integration** | **Excluded** — juvenile records sealed; not appropriate for RAG pipeline |
| **Note** | Indiana juvenile records are confidential under IC § 31-39 |

### 4.7 Home Detention Reporting

| Attribute | Detail |
|---|---|
| **Function** | Monitoring individuals on home detention |
| **Integration** | **Future** — limited public data; relevant for criminal justice analytics |

### 4.8 Mental Health Adjudication

| Attribute | Detail |
|---|---|
| **Function** | Records of mental health commitments and adjudications |
| **Data** | Commitment orders, restoration hearings, treatment compliance |
| **Integration** | **Excluded** — protected health information under HIPAA and state law |
| **Note** | IC § 12-26 governs confidentiality of mental health commitments |

### 4.9 Electronic Tickets / E-Tickets

| Attribute | Detail |
|---|---|
| **Function** | Electronic traffic citation and infraction management |
| **Data** | Citations, violations, court dates, dispositions |
| **Integration** | **Future** — structured data for traffic law research |

### 4.10 Commercial Driver Convictions

| Attribute | Detail |
|---|---|
| **Function** | Reporting commercial driver violations to BMV and federal CDLIS |
| **Data** | CDL violations, convictions, disqualification actions |
| **Integration** | **Future** — cross-reference with BMV records for fraud detection |

---

## 5. Court Administration Tools

### 5.1 BMV (Bureau of Motor Vehicles) Integration

| Attribute | Detail |
|---|---|
| **Agency** | Indiana BMV (separate from courts, but data-linked) |
| **Data** | Driver records, license status, vehicle registrations, title history |
| **Integration** | **Planned** — relevant for traffic law research, deed fraud (title chain), and identity verification |
| **Access** | Requires authorized access agreement with BMV |
| **URL** | `https://www.in.gov/bmv/` |

**IndyLeg relevance**: BMV records are critical for:
- Verifying parties in traffic / DUI cases
- Cross-referencing vehicle title transfers for deed fraud patterns
- Confirming identity information across filings

### 5.2 ECRW — Electronic Court Record Warehouse

| Attribute | Detail |
|---|---|
| **Function** | Centralized warehouse for court records, case data, and reporting |
| **Data** | Aggregated case data across all 92 counties; historical records |
| **Integration** | **Planned** — bulk historical ingestion for training and evaluation |
| **Access** | Requires data-sharing agreement with Indiana OCT |

### 5.3 Marriage License E-File System

| Attribute | Detail |
|---|---|
| **Function** | Electronic marriage license applications and issuance |
| **Data** | License applications, issued licenses, officiant records |
| **Integration** | **Low priority** — limited RAG relevance |

### 5.4 Electronic Tax Warrants

| Attribute | Detail |
|---|---|
| **Function** | Electronic processing of tax warrants and tax liens |
| **Data** | Tax warrants, lien amounts, debtor information, satisfaction records |
| **Integration** | **Planned** — relevant for debt-related case research and fraud detection |

### 5.5 Public Defender System

| Attribute | Detail |
|---|---|
| **Function** | Case assignment and workload management for public defenders |
| **Data** | Case assignments, eligibility determinations, attorney workloads |
| **Integration** | **Future** — restricted access; relevant for justice system analytics |

### 5.6 Statewide Jury Pool Project / Jury Management System

| Attribute | Detail |
|---|---|
| **Function** | Jury selection, summoning, tracking, and payment |
| **Data** | Jury pool composition, service records, exemptions |
| **Integration** | Not applicable — no legal document content for RAG |

### 5.7 Statistics Reporting

| Attribute | Detail |
|---|---|
| **Function** | Statewide caseload statistics, performance metrics, annual reports |
| **Data** | Caseload by county, case type, disposition rates, age of pending cases |
| **Integration** | **Planned** — valuable for contextualizing case research (e.g., median time-to-disposition in Marion County) |
| **URL** | Published annually at `courts.in.gov/research/` |

### 5.8 LexisNexis Online Legal Research

| Attribute | Detail |
|---|---|
| **Function** | Licensed legal research database available to court staff |
| **Access** | Licensed — not available for IndyLeg ingestion |
| **Note** | IndyLeg uses open sources (CourtListener, law.resource.org) instead |

---

## 6. External Legal Data Sources

Beyond the Indiana Courts ecosystem, IndyLeg integrates with these public data sources:

| Source | URL | Data | Status |
|---|---|---|---|
| **CourtListener** (Free Law Project) | `courtlistener.com/api/rest/v4/` | Indiana opinions, dockets, RECAP | **Active** |
| **law.resource.org** | `law.resource.org/pub/us/case/reporter/` | Federal Reporter (7th Circuit) | **Active** |
| **Indiana General Assembly** | `iga.in.gov/api/` | Indiana Code (IC), bills, session laws | **Active** |
| **BMV Records** | `in.gov/bmv/` | Driver/vehicle records | **Planned** |
| **Indiana Register** | `in.gov/legislative/register/` | Administrative rules, executive orders | **Planned** |
| **Indiana Law Enforcement Academy** | `in.gov/ilea/` | Officer certification records | **Future** |

---

## 7. IndyLeg Integration Map

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                        IndyLeg DATA SOURCE STATUS                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ✅ ACTIVE (ingesting now)                                                  │
│  ├── public.courts.in.gov API ···· Odyssey case data, opinions, orders     │
│  ├── mycase.in.gov ·············· Case metadata, party search              │
│  ├── CourtListener API ·········· Indiana appellate opinions               │
│  ├── law.resource.org ··········· 7th Circuit Federal Reporter             │
│  └── Indiana General Assembly ··· Indiana Code (IC §), bills               │
│                                                                             │
│  🔶 PLANNED (architecture ready, pending access/agreement)                  │
│  ├── E-Filing accepted documents · New filings near-real-time              │
│  ├── Protection Order Registry ·· Family law, fraud detection              │
│  ├── Abstract of Judgment ······· Sentencing research                      │
│  ├── Electronic Tax Warrants ···· Debt/lien research, fraud               │
│  ├── BMV Records ················ Traffic law, identity verification       │
│  ├── ECRW ······················· Historical bulk case data                │
│  ├── Statistics Reporting ······· Caseload context / analytics            │
│  └── Indiana Register ··········· Administrative rules                    │
│                                                                             │
│  🟡 FUTURE (requires significant access or infrastructure)                  │
│  ├── Supervised Release System ·· Criminal justice research               │
│  ├── Risk Assessment Data ······· Pretrial / sentencing analytics         │
│  ├── Home Detention Reporting ··· Criminal justice analytics              │
│  ├── E-Tickets ·················· Traffic law research                    │
│  ├── Commercial Driver ·········· CDL violations, fraud cross-ref        │
│  └── Public Defender System ····· Justice system analytics               │
│                                                                             │
│  🚫 EXCLUDED (sealed, confidential, or licensed)                            │
│  ├── PSI Reports ················ Sealed under IC § 35-38-1-13           │
│  ├── Juvenile Records ··········· Confidential under IC § 31-39          │
│  ├── Mental Health Records ······ HIPAA + IC § 12-26 protected           │
│  ├── INcite Internal ············ Court-staff-only extranet              │
│  └── LexisNexis ················· Licensed third-party database          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Data Flow: Source → IndyLeg Pipeline

```text
                Public Portals                Internal Systems (future)
              ┌──────────────┐              ┌──────────────────────┐
              │ mycase.in.gov│              │  Odyssey (internal)  │
              │ public.courts│              │  E-Filing Engine     │
              │ iga.in.gov   │              │  ECRW Warehouse      │
              │ CourtListener│              │  BMV · Tax Warrants  │
              │ law.resource │              │  Protection Orders   │
              └──────┬───────┘              └──────────┬───────────┘
                     │                                 │
                     ▼                                 ▼
              ┌──────────────────────────────────────────────┐
              │         IndyLeg Ingestion Pipeline           │
              │                                              │
              │  1. Source Connector (API/scraper)            │
              │  2. SQS Queue → Worker Pool                  │
              │  3. Document Loader + Parser                 │
              │  4. Legal Chunker (512-char, IC § aware)     │
              │  5. Titan Embed v2 (1024-dim)                │
              │  6. Content-hash dedup                       │
              │  7. Store → pgvector + OpenSearch + S3       │
              └──────────────────────────────────────────────┘
```

---

## 9. Access & Licensing Notes

| Source Type | Access Model | IndyLeg Approach |
|---|---|---|
| Public portals (mycase, public.courts) | Open access | Direct API / scraping with rate limiting |
| Court APIs (Odyssey public layer) | API key required | Registered via Indiana OCT |
| State agency data (BMV, Tax Warrants) | Data-sharing agreement | Formal MOU with agency |
| Federal case law (CourtListener, LRO) | Open / public domain | Free API + bulk download |
| Sealed / confidential records | Not available | **Excluded from pipeline** — IndyLeg enforces a confidentiality allowlist |
| Licensed databases (LexisNexis) | Commercial license | Not used — open-source alternatives preferred |

**Important**: IndyLeg never ingests sealed juvenile records (IC § 31-39), PSI reports (IC § 35-38-1-13), mental health commitment records (IC § 12-26), or any data protected by HIPAA. The ingestion pipeline includes a **source allowlist filter** that rejects documents from excluded sources.

---

## 10. Contact & Governance

**Indiana Office of Court Technology (OCT)**
- **Director**: Mary DePrez
- **Address**: 251 N. Illinois Street, Suite 700, Indianapolis, IN 46204
- **Phone**: 317-234-2710
- **Email**: mary.deprez@courts.in.gov

**Technology Notices**: Subscribe at [courts.in.gov](https://www.in.gov/courts/) for planned/unplanned outage notifications for Odyssey, E-filing, INcite, mycase.in.gov, public.courts.in.gov, and portal.courts.in.gov.

**Title VI Compliance**: IndyLeg's use of public court data complies with Title VI program requirements. Public Notice of Title VI Program Rights is available from the Indiana Judicial Branch.

---

*This document maps the full Indiana Courts technology ecosystem to IndyLeg's data pipeline. For implementation details on each active source connector, see [ARCHITECTURE.md](ARCHITECTURE.md) and the `ingestion/sources/` module.*
