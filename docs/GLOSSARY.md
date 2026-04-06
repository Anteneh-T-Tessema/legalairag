# Glossary

Quick reference for legal, AI/ML, and infrastructure terms used throughout the IndyLeg codebase and documentation.

---

## Legal Terms

| Term | Definition |
| --- | --- |
| **IC §** | Indiana Code section reference (e.g., `IC 32-31-1-6`). The standard citation format for Indiana statutes. |
| **Docket** | The official record of proceedings in a court case, listing all filings, motions, orders, and hearings. |
| **Holding** | The court's ruling or legal principle established in a case decision. |
| **Precedent** | A prior court decision that is authoritative for deciding similar future cases. |
| **Jurisdiction** | The geographic area or subject-matter authority of a court (e.g., Marion County, Indiana Supreme Court). |
| **Case type** | Classification of a case (CIVIL, CRIMINAL, FAMILY, PROBATE, etc.) used for filtering and metadata. |
| **Odyssey** | Tyler Technologies' case management system used by all 92 Indiana counties; the statewide CMS and primary upstream data source for IndyLeg. |
| **OCT** | **Office of Court Technology** — the Indiana Supreme Court division (led by Mary DePrez) that manages Odyssey, mycase.in.gov, INcite, E-Filing, and all statewide court technology systems. |
| **mycase.in.gov** | Indiana's public-facing case search portal. Provides party search, case lookup, and recent filings across all 92 counties. A read-only view of Odyssey data. |
| **INcite** | Indiana Court IT Extranet (mycourts.in.gov) — a restricted portal for court staff. Not accessible to IndyLeg (internal-only). |
| **E-Filing** | Indiana's mandatory electronic filing system at efile.incourts.gov, powered by Tyler Technologies. All civil filings and many criminal filings are submitted here. |
| **ECRW** | **Electronic Court Record Warehouse** — a statewide repository of electronic court records maintained by OCT. Access requires a data-sharing agreement with the Indiana Supreme Court. |
| **BMV** | **Bureau of Motor Vehicles** — Indiana agency providing driving records and license data. Relevant to traffic and criminal cases; access requires a Memorandum of Understanding (MOU). |
| **Protection Order Registry** | Statewide registry of protective orders maintained by Indiana courts, accessible for public safety purposes. |
| **Abstract of Judgment** | A court document summarizing the judgment in a case, used for transferring judgment liens and reporting to external agencies. |
| **PSI** | **Presentence Investigation** — confidential report prepared for sentencing. Protected by IC § 35-38-1-13; excluded from IndyLeg ingestion. |
| **CDL/CDLIS** | **Commercial Driver's License / Commercial Driver License Information System** — federal reporting system for commercial driver convictions, managed per 49 CFR Part 384. |
| **Tyler Technologies** | The private company that builds and maintains Odyssey CMS, E-Filing, and related court technology for Indiana (and many other states). |
| **Good law** | A legal ruling that has not been overturned, reversed, or superseded and is still valid authority. |
| **Citation chain** | A sequence of cases citing one another, forming a directed graph of legal authority. |

---

## AI / ML Terms

| Term | Definition |
| --- | --- |
| **RAG** | **Retrieval-Augmented Generation** — architecture that retrieves relevant documents before generating an LLM answer, ensuring responses are grounded in actual sources. |
| **Embedding** | A dense numeric vector (1024-dim in IndyLeg) that captures the semantic meaning of a text chunk, enabling similarity search. |
| **Bi-encoder** | A model that independently encodes queries and documents into vectors. Used for fast approximate retrieval (Titan Embed v2). |
| **Cross-encoder** | A model that jointly encodes a (query, document) pair and scores relevance directly. Slower but more accurate than bi-encoders. Used for re-ranking (`ms-marco-MiniLM-L-6-v2`). |
| **BM25** | Best Match 25 — a sparse keyword-based ranking function. IndyLeg uses BM25 via OpenSearch alongside dense vector search. |
| **HNSW** | Hierarchical Navigable Small World — an approximate nearest-neighbor graph algorithm for fast vector similarity search. IndyLeg uses **IVFFlat** (Inverted File with Flat quantization) for its pgvector index. |
| **RRF** | **Reciprocal Rank Fusion** — a score fusion method that combines ranked lists from multiple retrievers. Formula: `score = Σ 1/(k + rank)` where `k = 60`. |
| **Cosine similarity** | A similarity metric measuring the angle between two vectors. Value range: −1 to 1 (1 = identical direction). Used by pgvector for vector search. |
| **Temperature** | An LLM sampling parameter controlling randomness. IndyLeg uses `temperature=0.0` for deterministic, factual responses. |
| **Hallucination** | When an LLM generates claims not supported by the provided context. IndyLeg's CitationValidator blocks these. |
| **Faithfulness** | The degree to which a generated answer is supported by the retrieved source documents. Measured in the evaluation framework. |
| **Recall@K** | The fraction of relevant documents found in the top-K retrieved results. A core retrieval quality metric. |
| **MRR** | **Mean Reciprocal Rank** — the average of `1/rank` of the first relevant result across queries. |
| **NDCG** | **Normalised Discounted Cumulative Gain** — a ranking metric that rewards relevant results appearing earlier. |
| **Converse API** | AWS Bedrock's unified API for invoking LLMs (Claude, Titan, etc.) with a standardised message format. |

---

## IndyLeg-Specific Terms

| Term | Definition |
| --- | --- |
| **run_id** | A UUID assigned to each agent execution. Threads through all pipeline steps for end-to-end audit tracing. |
| **ParsedQuery** | The structured output of `QueryParser` — contains `jurisdiction`, `case_type`, `citations`, and `bm25_keywords`. |
| **CitationValidator** | The post-generation guard that verifies every `[SOURCE: id]` tag in the LLM response maps to an actually-retrieved chunk. Blocks hallucinated citations. |
| **AuthorityRanker** | Scores documents based on Indiana court hierarchy (Supreme Court > Court of Appeals > Tax Court > Circuit > Superior). |
| **CitationGraph** | A directed graph of case-to-case citations with PageRank-based importance scoring and good-law validation. |
| **LegalChunker** | A domain-aware text splitter that preserves `IC §` citations, section headings, and legal structure across chunk boundaries. |
| **HybridSearch** | The retrieval module combining pgvector (dense) and OpenSearch (sparse/BM25) results via RRF fusion. |
| **Confidence score** | Derived from cross-encoder scores of the top-5 chunks: HIGH (> 0.8), MEDIUM (0.5–0.8), LOW (< 0.5). |
| **DLQ** | **Dead-Letter Queue** — an SQS queue that captures messages that fail processing after 3 retries. Used for debugging ingestion failures. |

---

## Infrastructure Terms

| Term | Definition |
| --- | --- |
| **pgvector** | A PostgreSQL extension that adds vector data types and similarity search operators. IndyLeg stores 1024-dim embeddings in an IVFFlat-indexed column (`lists=100, vector_cosine_ops`). |
| **Aurora** | Amazon Aurora PostgreSQL — the managed database service running PostgreSQL 16 with pgvector in production. |
| **OpenSearch** | AWS-managed search engine (Elasticsearch-compatible) used for BM25 keyword indexing and full-text search. |
| **ECS Fargate** | AWS Elastic Container Service with Fargate launch type — serverless container orchestration for the API and worker services. |
| **CDK** | **AWS Cloud Development Kit** — infrastructure-as-code framework used by IndyLeg (3 stacks: ingestion, retrieval, API). |
| **SQS** | **Amazon Simple Queue Service** — message queue used for decoupling document ingestion from processing. |
| **ALB** | **Application Load Balancer** — distributes incoming traffic across ECS API tasks with health checks. |
| **LocalStack** | A local AWS emulator used for development. IndyLeg's `docker-compose.yml` runs LocalStack for S3 and SQS. |
| **JWT** | **JSON Web Token** — the authentication token format used by IndyLeg. Signed with HS256, contains `sub`, `role`, and `jti` claims. |
| **RBAC** | **Role-Based Access Control** — IndyLeg's permission model with 4 roles: ADMIN > ATTORNEY > CLERK > VIEWER. |
