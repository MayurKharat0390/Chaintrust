# ChainTrust

> A real-agent reputation pipeline with blockchain anchoring.  
> Research prototype for a seminar and paper.

---

## What is it?

ChainTrust runs **real LLM agents** (free-tier APIs + local models) on **real coding benchmark tasks**, grades their outputs automatically in a Docker sandbox, stores every interaction in a database, computes a reputation score from that history, and anchors each agent's history on a blockchain via Merkle roots.

**Research question:** Can a reputation score computed from real AI agents' task history resist Sybil and collusion attacks and be independently verified by another platform using blockchain-anchored records?

---

## Quick-start (one-command setup)

```bash
# 1. Clone and enter the repo
git clone <your-repo-url>
cd chaintrust

# 2. Create and activate a Python 3.11+ virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .                   # install chaintrust as editable package

# 4. Copy and fill in your API keys
cp .env.example .env
# Edit .env with your GEMINI_API_KEY, GROQ_API_KEY, etc.

# 5. (Optional) For EvalPlus versions of HumanEval+ and MBPP+:
pip install evalplus

# 6. Ensure Docker is running (needed for the grader sandbox)
docker info
```

---

## Running Phase 1

### Step 1 — Initialise DB and run agents

```bash
# Run all enabled agents on 20 randomly sampled tasks (3 attempts each)
python -m chaintrust.runner --agents all --tasks 20

# Run specific agents
python -m chaintrust.runner --agents gemini-flash-default llama3-groq-default --tasks 50

# Run grader self-check first (verifies reference solutions all pass)
python -m chaintrust.runner --agents all --tasks 20 --self-check

# Resume an interrupted run (skips already-done jobs)
python -m chaintrust.runner --agents all --tasks 20 --no-init
```

The runner prints a **pass-rate summary table** when finished:

```
=================================================================
  ChainTrust — Pass Rate Summary
=================================================================
             agent_name  attempts  pass_count  pass_rate  avg_quality
    gemini-flash-default        60          42     0.7000       0.7234
   llama3-groq-default          60          38     0.6333       0.6521
        mistral-openrouter       60          31     0.5167       0.5342
=================================================================
```

### Step 2 — Inspect the database

```bash
# Quick DB inspection with sqlite3
sqlite3 chaintrust.db ".tables"
sqlite3 chaintrust.db "SELECT name, COUNT(*) FROM interactions JOIN agents USING(agent_id) GROUP BY name;"
```

---

## How to add a new agent

1. Open [`config/agents.yaml`](config/agents.yaml).
2. Add an entry under `agents:` with the required fields:
   ```yaml
   - name: "my-new-agent"
     provider: openrouter         # gemini | groq | openrouter | ollama
     model: "mistralai/mistral-7b-instruct:free"
     system_prompt: >
       You are an expert Python programmer. Output ONLY a Python code block.
     temperature: 0.2
     max_tokens: 1024
     stake: 5
     enabled: true
   ```
3. If using a new provider, also implement a client in [`chaintrust/runner/clients.py`](chaintrust/runner/clients.py) and register it in `PROVIDER_MAP`.
4. Re-run the runner — new agents are automatically registered.

---

## Running the tests

```bash
pytest                        # all tests
pytest tests/unit/            # unit tests only (no API or Docker needed)
pytest -v tests/unit/test_extractor.py   # specific test file
pytest --cov=chaintrust       # with coverage report
```

---

## Repository layout

```
chaintrust/
  config/
    config.yaml          ← all knobs (no secrets)
    agents.yaml          ← agent definitions
  chaintrust/
    config.py            ← config loader (YAML + .env merge)
    registry/            ← agent registration, config_hash computation
    tasks/               ← HumanEval + MBPP loaders, TaskBank
    runner/              ← provider clients, rate limiter, extractor, pipeline
    grader/              ← Docker sandbox grader
    db/                  ← SQLAlchemy models + session factory
    reputation/          ← scoring algorithms (Phase 2)
    anchoring/           ← Merkle tree + chain client (Phase 3)
    verifier/            ← standalone verifier (Phase 3)
    experiments/         ← Sybil/collusion + validation experiments (Phase 4)
    api/                 ← FastAPI app (Phase 5)
    dashboard/           ← Streamlit dashboard (Phase 5)
  contracts/             ← Solidity + Hardhat (Phase 3)
  tests/
    unit/                ← unit tests (no API or Docker)
    integration/         ← integration tests (require API keys + Docker)
  .env.example           ← copy to .env and fill in keys
  requirements.txt       ← pinned dependencies
  pyproject.toml         ← project metadata + tool configs
```

---

## Design notes

### Config hash (`agent_id`)
Each agent is identified by `agent_id = SHA-256(canonical_JSON(config))[:32]`.  The canonical JSON excludes runtime fields (`enabled`, `rate_limits`) and sorts all keys, so the ID is determined solely by the agent's *behaviour-affecting* configuration.  Two agents with the same model but different `system_prompt` or `temperature` get different IDs.

### Difficulty weight (`d_t`)
Computed by the reputation engine as `1 − pass_fraction(task_t)`, with Laplace smoothing and clipped to `[0.1, 1.0]`.  A task that no agent has passed gets difficulty ≈ 1.0; a task everyone passes gets ≈ 0.1.  This is computed from observed data, never hand-set.

### CHS (ChainTrust Hybrid Score)
```
CHS_a = round( C_a^omega * [ (1 - w) * D'_a + w * T~_a ] * (1 - pi_a), 6 )
```
Where:
- $D'_a$: Direct evidence with Bayesian shrinkage ($m = 5.0$) against family-deduplicated task hardness ($d_t$).
- $C_a$: Output consistency confidence factor ($1 - \sigma_a$).
- $\tilde{T}_a$: Peer-review trust propagation under capped stake ($S_{\text{cap}} = 1000$).
- $\pi_a$: Collusion ring defense penalty detecting mutual reviews and rater concentration (cap $\pi_{\max} = 0.8$).
- All parameters loaded from versioned `config/chs_params.yaml`.

### Known Limitations
1. **Family Rule Trade-off**: Deduping by model family prefix penalizes legitimate variants of one architecture (e.g. `llama-3-8b` and `llama-3-70b`).
2. **Cross-Model Sybil Attack**: Attackers deploying distinct models per identity bypass family splitting, but incur real compute/API costs.
3. **Sample Size**: Requires $n_a \ge 5$ tasks to overcome shrinkage dampening.
4. **Level B Graph Requirement**: Level B verification requires the epoch's peer ratings table to reconstruct trust propagation.

### Merkle Anchoring & Offline Verification
Each interaction is serialised to canonical JSON (sorted keys, keccak256 hashed) to produce a Merkle leaf (`leaf_version=2`). Standalone offline verification supports two tiers:
- **Level A**: Validates execution records, inclusion proofs, task difficulty root, parameters hash, and direct score recomputation.
- **Level B**: Reconstructs peer ratings Merkle tree, trust propagation $\tilde{T}_a$, defense penalty $\pi_a$, and exact composite score recomputation.

### Grader safety
Generated code **never runs on the host**.  The grader:
- spawns a `docker run --network none --read-only --memory 256m` container
- writes the test script via a read-only volume mount
- kills the container if it exceeds the timeout (default 10 s)

---

## Phase Roadmap & Running the Pipeline

### 1. Compute CHS & Multi-Algorithm Reputations
```bash
# Compute scores across all algorithms (CHS, TraceRank, Elo, Beta, PageRank, Simple Avg)
python -m chaintrust.reputation --epoch 1

# Display CLI Leaderboard with side-by-side comparison
python -m chaintrust.reputation --leaderboard
```

### 2. Anonymous Peer Review Pipeline
```bash
# Execute peer review evaluations with anonymous prompt masking
python -m chaintrust.runner.peer_review --epoch 1 --reviews-per-agent 3
```

### 3. Standalone Cryptographic & Mathematical Verifier
```bash
# Verify Level A & Level B audit bundle without database or network access
python -m chaintrust.verifier experiments/results/bundle_epoch_1_<agent_id>.audit.json

# Optional: verify on-chain anchor commitment against Ethereum contract
python -m chaintrust.verifier experiments/results/bundle_epoch_1_<agent_id>.audit.json --on-chain
```

### 4. Run Empirical Evaluation Suite (Experiments A–F)
```bash
# Run full suite: validity, Sybil clones, collusion rings, ablations, sensitivity, tamper detection
python -m chaintrust.experiments
```
Outputs generated in `experiments/results/` (`.csv` and `.png` for Experiments A through F).

### 5. Launch API & Visualization Dashboard
```bash
# Start FastAPI backend service (port 8000)
uvicorn chaintrust.api.main:app --host 0.0.0.0 --port 8000 --reload

# Launch Streamlit interactive dashboard (port 8501)
streamlit run chaintrust/dashboard/app.py
```
Open `http://localhost:8000` to view the full WebGL/Three.js Cyber Holo-Chamber, live leaderboard with CHS breakdown, bundle verifier, and empirical evaluation suite.
