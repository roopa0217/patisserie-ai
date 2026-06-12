# Pâtisserie AI — Chef Instructor Intelligence System

A RAG-powered assistant for pastry academy instructors. Upload any recipe PDF and ask questions,
scale yields, build indent sheets, and check ingredient ratios — all grounded in your uploaded curriculum with no hallucination.

---

## Architecture

### Dual-namespace RAG

Two independent Pinecone namespaces keep structured and semantic knowledge separate:

| Namespace | Purpose | Chunk type |
|---|---|---|
| `patisserie` | Precise recipe lookup — ingredients, ratios, method steps | One chunk per recipe component (structured JSON) |
| `patisserie-semantic` | General technique and knowledge questions | Page-level sliding window (~450 words, 90-word overlap) |

### Retrieval pipeline

Every query runs through a hybrid retriever:

```
User query
  → Pinecone dense search  (top-20, cosine, BAAI/bge-en-icl 4096-dim)
  → BM25 keyword search    (top-20, rank-bm25, local pkl index)
  → Score-weighted merge   (dedup by chunk_id, keep highest score)
  → Score-fusion reranker  (80% base score + 20% keyword overlap boost)
  → Confidence gate        (low score → hard refusal, never hallucination)
  → top-10 results
```

### LangGraph agent

```
classify_intent
  → route
  → find_recipe    | Hybrid retrieval + 3-pass name matching
    scale_recipe   | Deterministic arithmetic — no LLM
    build_indent   | Multi-recipe ingredient consolidation — no LLM
    check_anomaly  | Ratio validation against thresholds.json — no LLM
    general        | Semantic namespace retrieval + LLM answer
  → END
```

LLM (Qwen/Qwen2.5-72B-Instruct-fast via Nebius) is called only for:
- Ambiguous intent classification (keyword regex runs first)
- General knowledge answers with retrieved context

All arithmetic tools (scaling, indent, anomaly) are fully deterministic.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · LangChain · LangGraph |
| Agent | LangGraph StateGraph |
| Vector DB | Pinecone (dual namespace) |
| LLM | Qwen/Qwen2.5-72B-Instruct-fast via Nebius Token Factory |
| Embeddings | BAAI/bge-en-icl (4096-dim) via Nebius Token Factory |
| Reranking | Custom score-fusion (RRF + keyword overlap, no external service) |
| Keyword search | BM25Okapi (rank-bm25, rebuilt locally after every ingest) |
| PDF parsing | pdfplumber |
| Frontend | React · TypeScript · Vite · Tailwind CSS |
| Streaming | Server-Sent Events (status → result → token → meta → done) |

---

## Setup

### 1. Environment variables

```bash
cp .env.example .env
# Fill in: NEBIUS_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME
```

### 2. Pinecone index

Create a Pinecone index with:
- **Dimensions**: `4096` (matches `BAAI/bge-en-icl`)
- **Metric**: `cosine`
- **Name**: whatever you set in `PINECONE_INDEX_NAME`

The app uses two namespaces (`patisserie` and `patisserie-semantic`) within this single index — no extra setup needed.

### 3. Install backend dependencies

Requires **Python 3.12** (3.14 is not yet supported by pydantic-core).
On macOS: `brew install python@3.12`

```bash
cd backend
/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
```

---

## Running

### Start the backend

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Start the frontend

```bash
cd frontend
npm run dev
# Open http://localhost:5173
```

---

## Upload a PDF

### Via the UI

Drag and drop any recipe PDF onto the sidebar upload zone. The system:
1. Parses structured recipe components (ingredients, method steps, yield labels) with pdfplumber
2. Embeds each component chunk via Nebius → upserts to `patisserie` namespace
3. Creates page-level semantic chunks → upserts to `patisserie-semantic` namespace
4. Rebuilds the local BM25 index from all stored chunks

Idempotent — re-uploading the same PDF deletes existing vectors by `source_file` filter before re-upserting. No duplicates.

### Via curl

```bash
curl -X POST http://localhost:8000/ingest/upload \
  -F "file=@/path/to/your/recipe.pdf"
```

Response:
```json
{
  "file": "recipe.pdf",
  "chunks": 42,
  "semantic_chunks": 18,
  "recipes": 12,
  "status": "ok"
}
```

PDFs that don't follow the academy table format (notes, articles, handouts) are still ingested via page-level semantic chunking and remain searchable for general knowledge questions.

---

## What the agent can do

| Intent | Example query |
|---|---|
| Find recipes | "Show me all recipes that use gelatine" |
| Scale a yield | "Scale the croissant dough to 5000g" |
| Scale by portions | "Scale banana tart for 30 students" |
| Scale one component | "Double the praline paste in Berliner Doughnut" |
| Build an indent sheet | "Build an indent sheet for croissants and soft rolls" |
| Check for anomalies | "Check the dark chocolate tart for ratio errors" |
| General knowledge | "Why does lamination butter need the same consistency as the dough?" |

---

## Confidence-based refusal

When retrieval confidence is below the threshold, the app responds with a hard refusal instead of hallucinating:

> "This recipe is not in the uploaded curriculum. Upload the relevant PDF via **Upload Recipe Books** to add it to the knowledge base."

---

## Notes on non-linear scaling

When scaling yeast, gelatin, baking powder, baking soda, or salt, the system applies a dampening factor and shows a ⚠ warning. The instructor should always verify these quantities before production — the dampened values are starting points, not definitive figures.

## Notes on anomaly checking

The threshold database (`data/thresholds.json`) currently covers:
- **Gelatin** — 0.5–3.0% of liquid weight
- **Dark chocolate in ganache** — 100–250% of cream weight

Additional rules can be added directly to `data/thresholds.json` using the same schema.
