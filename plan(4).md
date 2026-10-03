# RESEARCH AI --- Complete Development Plan

## 1. Product Vision

**Research AI** is a professional Research Intelligence Assistant built
around the original PS23 requirement, **Faculty Research Discovery
Assistant**.

The product should help a researcher move from:

**Research Idea → Faculty Discovery → Literature → Paper Analysis →
Research Gaps → Research Direction → Research Plan → Paper → IEEE
Format**

It is **not** just a chatbot and not just basic RAG.

The core architecture is:

``` text
Research Data
    ↓
Cleaning + Normalization
    ↓
Hybrid Retrieval
    ↓
Evidence
    ↓
Research Intelligence
    ↓
LLM Reasoning
    ↓
Research Output
```

------------------------------------------------------------------------

# 2. UI Direction

Keep the UI **simple, clean and professional**.

Target feeling:

-   Modern research SaaS
-   Academic dashboard
-   Linear / Notion / Perplexity inspired
-   Light theme
-   White/off-white background
-   Dark text
-   Indigo/blue primary accent
-   Thin borders
-   Moderate rounded corners
-   Clear typography
-   Lots of whitespace

Avoid:

-   Neon AI themes
-   Huge gradients
-   Robot/brain graphics
-   Excessive animations
-   Fake statistics
-   Too many cards
-   ChatGPT-style UI as the entire product

Recommended font: **Inter or Geist**.

------------------------------------------------------------------------

# 3. Main Navigation

``` text
RESEARCH AI

Dashboard

Faculty Discovery       ← PS23 CORE

Literature Search
Research Analysis
Gaps & Novelty
Research Planner
Paper Studio

--------------------

My Research
  Projects
  Saved Papers
  Drafts
  Research History

--------------------

AI Model
Settings
```

**Faculty Discovery must be immediately below Dashboard.**

------------------------------------------------------------------------

# 4. Dashboard

Purpose: give the user a central research workspace.

Main sections:

### Header

``` text
Good evening, [User]

Your AI-powered research workspace
```

### Statistics

-   Research Projects
-   Saved Papers
-   Faculty Discovered
-   Paper Drafts

These must come from real user data.

### Research Input

``` text
What are you researching today?

[ Describe your research idea or question... ]

AI Model
[ Ollama — Llama 3.1 8B ▼ ]

[ Analyze Research ]
```

The model selector belongs inside this section.

### Quick Access

-   Faculty Discovery
-   Literature Search
-   Research Analysis
-   Gaps & Novelty
-   Research Planner
-   Paper Studio

### Continue Research

Show the user's existing research projects.

### Recent Searches

Show recent queries.

### Recent Faculty Discoveries

Show recently viewed researchers.

------------------------------------------------------------------------

# 5. Faculty Discovery --- PS23 Core

Purpose: discover faculty/researchers based on expertise and publication
evidence.

### Search

``` text
Search faculty by topic, keyword, researcher or research area

[ AI + Computer Vision + Medical Imaging ]
```

### Filters

-   Institution
-   Department
-   Research topic
-   Publication year
-   Publication count
-   Research area

### Faculty Result

``` text
Faculty Name
Institution
Department

Research Topics

Research Match: 91%

Why matched:
• Relevant publications
• Recent publications
• Semantic topic similarity

Evidence:
[Paper A] [Paper B] [Paper C]

[View Profile]
```

### Expertise Types

Every expertise result must be classified as:

1.  **Stated Expertise**
2.  **Publication-Supported Expertise**
3.  **Inferred Topic Similarity**

Do not present inferred similarity as confirmed expertise.

------------------------------------------------------------------------

# 6. Faculty Profile

Show:

-   Faculty name
-   Institution
-   Department
-   Research expertise
-   Research topics
-   Publications
-   Co-authors
-   Research timeline
-   Evidence
-   Why they match the user's query
-   Potential research overlap

Example timeline:

``` text
2022 → Computer Vision
2023 → Medical Imaging
2024 → Explainable AI
2025 → Lightweight Models
```

------------------------------------------------------------------------

# 7. Faculty Comparison

Allow multiple faculty to be compared.

Example:

  Attribute               Faculty A   Faculty B   Faculty C
  ----------------------- ----------- ----------- -----------
  Computer Vision         Yes         Yes         Yes
  Medical Imaging         Yes         Yes         No
  CNN                     Yes         No          Yes
  XAI                     No          Yes         Yes
  Relevant Publications   14          8           11

Do not call anyone "best". Show transparent evidence.

------------------------------------------------------------------------

# 8. Duplicate Name Resolution

Handle researchers with identical/similar names.

Use:

-   ORCID
-   Institution
-   Affiliations
-   Co-authors
-   Publication history
-   OpenAlex IDs

Example:

``` text
S. Kumar

Institution A → Computer Vision
Institution B → NLP
Institution C → Robotics
```

Never blindly merge researchers because their names match.

------------------------------------------------------------------------

# 9. Literature Search

Purpose: find relevant papers.

Search:

``` text
[ lightweight CNN diabetic retinopathy ]
```

Filters:

-   Year
-   Author
-   Topic
-   Dataset
-   Method
-   Open access
-   Citations

Paper cards should show:

-   Title
-   Authors
-   Year
-   Abstract snippet
-   Topics
-   Methods
-   Citations
-   Relevance
-   DOI/source

Actions:

-   View
-   Save
-   Compare
-   Add to Project

------------------------------------------------------------------------

# 10. Paper Intelligence

Purpose: understand one paper deeply.

Two-column layout:

``` text
Paper Information        AI Analysis

Title                    Key Findings
Authors                  Dataset
Year                     Method
DOI                      Results
Abstract                 Limitations
                         Research Opportunities
```

AI analysis must use extracted paper content.

Never invent paper details.

------------------------------------------------------------------------

# 11. Research Analysis

Purpose: compare selected papers.

Compare:

-   Dataset
-   Model
-   Method
-   Training
-   Metrics
-   Results
-   Validation strategy
-   Limitations
-   Publication year

Visualizations can include:

-   Model usage
-   Dataset usage
-   Publication timeline
-   Accuracy comparison
-   Citation trends
-   Topic frequency

All charts must use actual retrieved data.

------------------------------------------------------------------------

# 12. Gaps & Novelty

Purpose: identify possible research gaps from evidence.

Example:

``` text
Research Gap

Cross-dataset validation is underexplored.

Evidence:
8/12 papers use Dataset A
2/12 use Dataset B
0/12 perform cross-dataset evaluation

Confidence: High

Supporting papers:
[1] [4] [7] [9]
```

Potential research directions:

-   Different dataset
-   Different architecture
-   Cross-dataset evaluation
-   New evaluation method
-   Explainability
-   Efficiency
-   Reproducibility
-   Different experimental setting

These are **potential directions**, not guaranteed novel discoveries.

------------------------------------------------------------------------

# 13. Novelty Checker

If time permits:

``` text
User idea:
"Combine X and Y for Z."

System searches existing literature.

X → Paper A
Y → Paper B
X + Y → Paper C

Result:
Direct combination already appears.

Possible differentiation:
• Dataset
• Architecture
• Evaluation
• Application
```

Never tell users that an idea is definitely novel unless the evidence
supports the claim.

------------------------------------------------------------------------

# 14. Research Planner

Purpose: convert research into an executable plan.

Sections:

``` text
Research Question
Hypothesis
Research Objective
Dataset
Baseline
Proposed Method
Experiments
Ablation Study
Evaluation Metrics
Expected Contribution
Potential Risks
```

Flow:

``` text
Research Idea
    ↓
Retrieved Literature
    ↓
Research Gaps
    ↓
Evidence
    ↓
LLM
    ↓
Research Plan
```

------------------------------------------------------------------------

# 15. Experiment Advisor

Optional feature.

Recommend:

### Experiments

-   Baseline comparison
-   Ablation study
-   Cross-dataset validation
-   Robustness testing
-   Computational efficiency
-   Generalization testing

### Visualizations

-   Confusion matrix
-   ROC curve
-   Training curves
-   Model comparison
-   Dataset distribution
-   Error analysis

------------------------------------------------------------------------

# 16. Paper Studio

Purpose: prepare the actual manuscript.

Sections:

``` text
Title
Abstract
Introduction
Related Work
Methodology
Experiments
Results
Discussion
Limitations
Conclusion
References
```

Use a document-editor style UI.

AI actions:

-   Generate section
-   Improve
-   Summarize
-   Expand
-   Rewrite
-   Add citation
-   Check evidence
-   Generate outline

------------------------------------------------------------------------

# 17. IEEE Formatter

The existing DOCX → IEEE formatter should be reused.

Do not rebuild it.

Flow:

``` text
Paper Draft
    ↓
DOCX
    ↓
Existing IEEE Formatter
    ↓
IEEE-formatted DOCX
```

UI:

``` text
Upload DOCX
[ Format as IEEE ]
Preview
[ Download IEEE DOCX ]
```

------------------------------------------------------------------------

# 18. Research History

Each research project should retain its own context.

``` text
Project
├── Research Idea
├── Search History
├── Saved Papers
├── Selected Faculty
├── Paper Comparisons
├── Research Gaps
├── Novel Directions
├── Research Plan
├── Paper Draft
└── IEEE Document
```

The user should be able to return later and continue.

------------------------------------------------------------------------

# 19. Authentication

Use **Firebase Authentication**.

Support:

-   Google login
-   Email/password

Pages:

``` text
/login
/signup
```

After login:

``` text
User
 ↓
Firebase Auth
 ↓
User ID
 ↓
User-specific data
```

Never expose API keys in frontend code.

------------------------------------------------------------------------

# 20. Database

Use Firestore for user-specific application data.

Suggested structure:

``` text
users/{userId}
  profile
  preferences

  research_projects/{projectId}
  saved_papers/{paperId}
  research_history/{historyId}
  drafts/{draftId}
```

Do NOT store the entire OpenAlex corpus in Firestore.

------------------------------------------------------------------------

# 21. Research Corpus

Research data can come from:

-   OpenAlex
-   Faculty profiles
-   Publications
-   Abstracts
-   Topics
-   Authors
-   Co-authors
-   References
-   Related works

### Author fields

``` text
id
display_name
orcid
full_name
display_name_alternatives
affiliations
last_known_institutions
topics
topic_share
works_count
cited_by_count
works_api_url
counts_by_year
```

### Publication fields

``` text
id
title
doi
publication_year
publication_date
authorships
institutions
topics
keywords
concepts
abstract
cited_by_count
referenced_works
related_works
locations
open_access
```

------------------------------------------------------------------------

# 22. Data Pipeline

``` text
OpenAlex
   ↓
Raw JSON
   ↓
Cleaning
   ↓
Normalization
   ↓
Entity Resolution
   ↓
Faculty ↔ Publication Linking
   ↓
Research Corpus
   ↓
Chunking
   ↓
Embeddings
   ↓
Vector Index
   ↓
BM25 Index
```

If OpenAlex provides `abstract_inverted_index`, reconstruct it into a
normal abstract string during ingestion.

------------------------------------------------------------------------

# 23. Hybrid Retrieval

Never depend only on vector search.

``` text
User Query
   ↓
 ┌───────────────┬───────────────┐
 ↓               ↓
BM25          Vector Search
 ↓               ↓
 └───────────────┴───────────────┘
              ↓
        Hybrid Ranking
              ↓
           Reranker
              ↓
          Evidence
```

BM25 handles exact terminology.

Vector search handles semantic similarity.

------------------------------------------------------------------------

# 24. RAG

RAG provides evidence to the LLM.

``` text
Query
 ↓
Retriever
 ↓
Relevant Documents
 ↓
Relevant Passages
 ↓
Context
 ↓
LLM
 ↓
Answer + Evidence
```

Faculty Discovery is retrieval/RAG-heavy.

Research Planning and Paper Assistance are LLM-heavy but should still be
grounded in retrieved research evidence.

The principle is:

**RAG provides evidence → LLM reasons over the evidence.**

------------------------------------------------------------------------

# 25. LLM Architecture

Do not hard-code one model.

Create:

``` text
LLMProvider

generate()
stream()
structured_output()
```

Implement:

``` text
OllamaProvider
GroqProvider
GeminiProvider (optional/future)
```

The application must work with Ollama alone.

------------------------------------------------------------------------

# 26. Local AI

Use Ollama as the primary free/local provider.

Possible models:

-   Llama
-   Qwen
-   Gemma
-   Other Ollama-compatible models

The exact model must be configurable.

Detect installed Ollama models where possible.

------------------------------------------------------------------------

# 27. Groq

Groq is an optional cloud provider.

Users may configure a Groq API key.

Never expose the key in frontend code.

Optional fallback:

``` text
Groq unavailable
      ↓
Ollama
```

------------------------------------------------------------------------

# 28. Model Selector

The main dashboard research input should contain:

``` text
What are you researching today?

[ Describe your research idea... ]

AI Model
[ Ollama — Llama 3.1 8B ▼ ]

[ Analyze Research ]
```

The dropdown should show only configured/available models.

Example:

``` text
Ollama
  Llama 3.1 8B
  Qwen
  Gemma

Groq
  Configured models
```

------------------------------------------------------------------------

# 29. LLM Router

All research modules call:

``` text
llm.generate(...)
```

They must NOT directly call Ollama/Groq/Gemini.

Architecture:

``` text
Research Module
      ↓
Unified LLM Service
      ↓
Model Router
      ↓
Selected Provider
      ↓
Selected Model
```

This lets us change models without rewriting the research system.

------------------------------------------------------------------------

# 30. Evidence Verification

Important AI claims must have evidence.

Do not invent:

-   Faculty expertise
-   Publications
-   Results
-   Citations
-   Dataset properties
-   Research gaps

Example:

``` text
Claim:
Faculty X has research in medical imaging.

Evidence:
Paper A
Paper B
Paper C
```

For research gaps:

``` text
Claim
 ↓
Supporting papers
 ↓
Evidence count
 ↓
Confidence
```

------------------------------------------------------------------------

# 31. Faculty Ranking

Possible ranking factors:

``` text
Topic relevance
Publication relevance
Semantic similarity
Recency
Research consistency
Evidence strength
```

Calculate ranking with deterministic logic where possible.

Use the LLM to explain the result, not to invent the score.

------------------------------------------------------------------------

# 32. Backend

Use FastAPI.

Backend responsibilities:

-   Auth verification
-   User projects
-   OpenAlex ingestion
-   Research search
-   Hybrid retrieval
-   Faculty discovery
-   Paper analysis
-   Gap analysis
-   LLM routing
-   Evidence handling
-   IEEE formatter integration

Frontend must not contain research logic.

------------------------------------------------------------------------

# 33. Suggested API Routes

``` text
GET  /api/me

GET    /api/projects
POST   /api/projects
GET    /api/projects/{id}
PUT    /api/projects/{id}
DELETE /api/projects/{id}

GET /api/faculty/search
GET /api/faculty/{id}
GET /api/faculty/{id}/publications

GET  /api/papers/search
GET  /api/papers/{id}
POST /api/papers/save

POST /api/analysis/compare
POST /api/analysis/gaps
POST /api/analysis/novelty

POST /api/planner/generate
PUT  /api/planner/{projectId}

GET  /api/ai/providers
GET  /api/ai/models
POST /api/ai/test
```

------------------------------------------------------------------------

# 34. Frontend Routes

``` text
/auth/login
/auth/signup

/app/dashboard

/app/faculty
/app/faculty/:id

/app/literature
/app/literature/:id

/app/analysis
/app/gaps
/app/planner
/app/paper-studio

/app/my-research
/app/projects
/app/saved-papers
/app/drafts
/app/history

/app/settings
/app/ai-model
```

------------------------------------------------------------------------

# 35. Frontend Components

``` text
components/
  layout/
    Sidebar
    Topbar
    PageHeader

  faculty/
    FacultySearch
    FacultyCard
    FacultyProfile
    ExpertiseBadge
    EvidencePanel
    FacultyComparison
    ResearchTimeline

  literature/
    SearchBar
    PaperCard
    PaperFilters
    PaperViewer

  analysis/
    ComparisonTable
    ResearchChart
    MethodAnalysis

  gaps/
    GapCard
    EvidenceList
    NoveltyPanel

  planner/
    ResearchQuestion
    Hypothesis
    DatasetRecommendation
    ExperimentPlan

  paper/
    PaperEditor
    SectionOutline
    CitationPanel
    IEEEExport

  ai/
    ModelSelector
    ProviderStatus
```

------------------------------------------------------------------------

# 36. Backend Folder Structure

``` text
backend/
  app/
    main.py

    api/routes/
      auth.py
      projects.py
      faculty.py
      literature.py
      analysis.py
      planner.py
      papers.py
      ai.py

    services/
      openalex_service.py
      faculty_service.py
      paper_service.py
      retrieval_service.py
      embedding_service.py
      reranker_service.py
      rag_service.py
      gap_service.py
      novelty_service.py
      planner_service.py
      llm_service.py
      citation_service.py

    providers/
      ollama_provider.py
      groq_provider.py
      gemini_provider.py

    models/
      faculty.py
      publication.py
      project.py

    core/
      config.py
      security.py
```

------------------------------------------------------------------------

# 37. Team Responsibilities

## You --- AI / Research Intelligence

Own:

-   OpenAlex ingestion
-   Normalization
-   Entity resolution
-   Research corpus
-   Embeddings
-   BM25
-   Vector search
-   Hybrid retrieval
-   Reranking
-   Faculty ranking
-   Expertise classification
-   RAG
-   Evidence system
-   Gap detection
-   Novelty analysis
-   LLM router
-   Research planner logic

Do not spend your time building basic UI.

------------------------------------------------------------------------

## Junior 1 --- Frontend

Own:

-   Layout
-   Sidebar
-   Dashboard
-   Faculty Discovery
-   Literature Search
-   Research Analysis
-   Gaps & Novelty
-   Responsive UI

Use mock JSON initially.

Do not wait for the backend.

------------------------------------------------------------------------

## Junior 2 --- Frontend / Paper

Own:

-   Research Planner
-   Paper Studio
-   Document editor
-   Citation UI
-   IEEE formatter integration
-   Project pages
-   Research history

------------------------------------------------------------------------

## Junior 3 --- Backend / Firebase

Own:

-   Firebase Auth
-   Firestore
-   User profiles
-   Research projects
-   Saved papers
-   Research history
-   Draft storage
-   FastAPI integration
-   API routes
-   Security

------------------------------------------------------------------------

# 38. Frontend/Backend Contract

Agree on JSON structures before integration.

Example:

``` json
{
  "id": "A123",
  "name": "Dr. Example",
  "institution": "Example University",
  "match_score": 0.91,
  "expertise": [
    {
      "topic": "Computer Vision",
      "type": "publication_supported",
      "confidence": 0.94
    }
  ],
  "evidence": [
    {
      "title": "Example Paper",
      "year": 2025,
      "doi": "..."
    }
  ]
}
```

Frontend builds against this structure.

------------------------------------------------------------------------

# 39. Security

Never put secrets in frontend code.

Bad:

``` text
NEXT_PUBLIC_GROQ_API_KEY
NEXT_PUBLIC_OPENAI_API_KEY
```

Correct:

``` text
GROQ_API_KEY=...
```

Store secrets in backend environment variables.

Firebase rules must prevent:

``` text
User A → User B's research data
```

------------------------------------------------------------------------

# 40. Error States

Every feature needs:

``` text
Loading...
```

``` text
No relevant research found.
```

``` text
Model unavailable.
```

``` text
No supporting evidence found.
```

Do not silently fabricate output when retrieval fails.

------------------------------------------------------------------------

# 41. Evaluation

Create approximately 10 research topic queries.

Evaluate:

### Retrieval

-   Precision@K
-   Recall@K
-   MRR/NDCG where useful

### Faculty Discovery

-   Relevance
-   Expertise classification
-   Evidence correctness

### RAG

-   Citation correctness
-   Evidence relevance
-   Unsupported claim rate

Document the evaluation methodology.

------------------------------------------------------------------------

# 42. Hackathon Demo

Use one complete story:

``` text
1. Login

2. Dashboard

3. Enter:
   "I want to research lightweight CNNs
    for medical image classification."

4. Faculty Discovery
   → Find relevant researchers

5. Literature Search
   → Retrieve papers

6. Select papers

7. Research Analysis
   → Compare methods/datasets/results

8. Gaps & Novelty
   → Find evidence-backed gaps

9. Research Planner
   → Generate research plan

10. Paper Studio
    → Prepare paper

11. IEEE Formatter
    → Export IEEE document
```

------------------------------------------------------------------------

# 43. Priority

## P0 --- MUST WORK

-   Authentication
-   Dashboard
-   Faculty Discovery
-   OpenAlex corpus
-   Hybrid retrieval
-   Evidence
-   Literature Search
-   Paper Analysis
-   Gap Detection
-   Research Planner
-   LLM provider abstraction
-   Research history

## P1 --- SHOULD WORK

-   Faculty comparison
-   Faculty timeline
-   Novelty checker
-   Paper Studio
-   IEEE formatter integration
-   Citation verification

## P2 --- IF TIME

-   Research graph
-   Collaboration discovery
-   Experiment advisor
-   Visualization advisor
-   Research trends
-   Automatic fallback
-   Paper quality checker

------------------------------------------------------------------------

# 44. What NOT to Build First

Do not start with:

-   Fancy animations
-   Dark mode
-   3D graphs
-   Huge knowledge graphs
-   Multiple paid AI APIs
-   Mobile app
-   Custom model training
-   Full automatic paper generation

First make:

``` text
Faculty Discovery
      ↓
Literature
      ↓
Evidence
      ↓
Analysis
```

work reliably.

------------------------------------------------------------------------

# 45. Definition of Done

### Faculty

-   [ ] Search works
-   [ ] Relevant faculty retrieved
-   [ ] Ranking explainable
-   [ ] Evidence shown
-   [ ] Expertise types distinguished
-   [ ] Duplicate names handled

### Literature

-   [ ] Search works
-   [ ] Papers can be saved
-   [ ] Papers can be compared
-   [ ] Paper information is grounded

### Research Intelligence

-   [ ] Gaps identified
-   [ ] Gap evidence shown
-   [ ] Research directions generated
-   [ ] Research plans generated

### AI

-   [ ] Ollama works
-   [ ] Model selector works
-   [ ] Provider abstraction exists
-   [ ] API keys are server-side
-   [ ] Paid APIs are optional

### User System

-   [ ] Login works
-   [ ] Projects persist
-   [ ] History persists
-   [ ] Saved papers persist
-   [ ] Drafts persist

### Paper

-   [ ] Outline works
-   [ ] Draft editable
-   [ ] Evidence/citations attached
-   [ ] IEEE formatter integrated
-   [ ] Final DOCX generated

### Demo

-   [ ] End-to-end flow works
-   [ ] No important screen depends on fake hardcoded data
-   [ ] Loading/error/empty states work
-   [ ] UI is professional
-   [ ] Demo works without manual backend fixes

------------------------------------------------------------------------

# 46. Golden Rule

Build the system as:

``` text
DATA
 ↓
RETRIEVAL
 ↓
EVIDENCE
 ↓
RESEARCH INTELLIGENCE
 ↓
LLM
 ↓
OUTPUT
```

Not:

``` text
USER → CHATBOT → RANDOM AI ANSWER
```

The LLM is the reasoning/generation layer.

The research corpus, retrieval system, evidence system, ranking logic,
and research-intelligence algorithms are the actual core.

**Faculty Discovery remains the PS23 core module.**

The broader research workflow makes the project more ambitious:

> **Discover people and literature → understand existing work → identify
> evidence-backed gaps → plan research → prepare a paper → export it in
> IEEE format.**
