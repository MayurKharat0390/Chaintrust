"""
chaintrust/dashboard/app.py
Interactive Streamlit Dashboard for ChainTrust.
Provides real-time visibility into AI agent reputation rankings, multi-algorithm comparisons,
Sybil & collusion resilience metrics, blockchain Merkle anchors, and independent audit verification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

from chaintrust.config import get_config
from chaintrust.db.models import Agent, Anchor, Interaction, Reputation, Task
from chaintrust.db.session import get_session
from chaintrust.experiments.runner import run_sybil_experiments
from chaintrust.reputation.engine import ReputationEngine
from chaintrust.verifier.verifier import StandaloneVerifier

# ---------------------------------------------------------------------------
# Streamlit Page Config & Custom Styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ChainTrust — Agent Reputation & Anchoring",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #1e2638 0%, #111827 100%);
        border: 1px solid #374151;
        border-radius: 12px;
        padding: 20px;
        color: #f3f4f6;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }
    .metric-val {
        font-size: 2.2rem;
        font-weight: 700;
        color: #38bdf8;
    }
    .metric-lbl {
        font-size: 0.9rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .badge-tracerank {
        background-color: #0284c7;
        color: white;
        padding: 4px 8px;
        border-radius: 6px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data Loading Helpers
# ---------------------------------------------------------------------------
@st.cache_data(ttl=5)
def load_db_stats() -> Dict[str, Any]:
    try:
        with get_session() as s:
            agents = s.query(Agent).all()
            tasks = s.query(Task).all()
            interactions = s.query(Interaction).all()
            anchors = s.query(Anchor).all()
            reps = s.query(Reputation).all()

            agent_list = [
                {"agent_id": a.agent_id, "name": a.name, "provider": a.provider, "model": a.model, "stake": a.stake}
                for a in agents
            ]
            task_list = [
                {"task_id": t.task_id, "source": str(t.source), "difficulty_weight": t.difficulty_weight or 0.5}
                for t in tasks
            ]
            anchor_list = [
                {
                    "agent_id": a.agent_id,
                    "epoch": a.epoch,
                    "merkle_root": a.merkle_root,
                    "score_hash": a.score_hash,
                    "tx_hash": a.tx_hash,
                    "block_number": a.block_number,
                    "anchored_at": a.anchored_at.isoformat() if a.anchored_at else None,
                }
                for a in anchors
            ]
            rep_list = [
                {"agent_id": r.agent_id, "epoch": r.epoch, "method": r.method, "score": r.score}
                for r in reps
            ]
            return {
                "agents": agent_list,
                "tasks": task_list,
                "interactions_count": len(interactions),
                "anchors": anchor_list,
                "reputations": rep_list,
            }
    except Exception:
        return {"agents": [], "tasks": [], "interactions_count": 0, "anchors": [], "reputations": []}


data = load_db_stats()

# ---------------------------------------------------------------------------
# Sidebar Controls
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image("https://raw.githubusercontent.com/feathericons/feather/master/icons/shield.svg", width=48)
    st.title("ChainTrust")
    st.caption("AI Agent Reputation & Merkle Anchoring Pipeline")
    st.divider()

    st.subheader("⚙️ Engine Controls")
    if st.button("🔄 Recalculate Reputations", use_container_width=True):
        with st.spinner("Computing reputation scores across all algorithms..."):
            with get_session() as s:
                engine = ReputationEngine()
                engine.compute_latest(s)
            st.success("Reputation scores updated!")
            st.rerun()

    st.divider()
    st.caption("Environment: Local Research Node")
    st.caption("Contract: ChainTrustAnchor (Hardhat / Sepolia)")


# ---------------------------------------------------------------------------
# Top KPI Header
# ---------------------------------------------------------------------------
st.title("🛡️ ChainTrust Reputation & Audit Center")
st.markdown("Cryptographically anchored, Sybil-resilient reputation for autonomous LLM agents.")

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">Registered Agents</div>
        <div class="metric-val">{len(data['agents'])}</div>
    </div>
    """, unsafe_allow_html=True)
with kpi2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">Benchmark Tasks</div>
        <div class="metric-val">{len(data['tasks'])}</div>
    </div>
    """, unsafe_allow_html=True)
with kpi3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">Total Interactions</div>
        <div class="metric-val">{data['interactions_count']}</div>
    </div>
    """, unsafe_allow_html=True)
with kpi4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-lbl">On-Chain Anchors</div>
        <div class="metric-val">{len(data['anchors'])}</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# ---------------------------------------------------------------------------
# Navigation Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏆 Leaderboard",
    "⚔️ Algorithm Comparison",
    "🛡️ Sybil Resilience Benchmark",
    "⛓️ Blockchain & Merkle Audit",
    "📊 Task Bank & Difficulty",
])

# ---------------------------------------------------------------------------
# Tab 1: Leaderboard
# ---------------------------------------------------------------------------
with tab1:
    st.subheader("Agent Reputation Leaderboard")
    c1, c2 = st.columns([1, 2])
    with c1:
        selected_method = st.selectbox(
            "Scoring Algorithm",
            ["chs", "tracerank", "elo", "beta", "pagerank", "simple_avg"],
            index=0,
            help="CHS combines dynamic difficulty, empirical Bayes shrinkage, trust propagation, and collusion defenses.",
        )

    # Filter reputations
    rep_df = pd.DataFrame(data["reputations"])
    agent_df = pd.DataFrame(data["agents"])

    if not rep_df.empty and not agent_df.empty:
        merged = rep_df[rep_df["method"] == selected_method].merge(agent_df, on="agent_id", how="left")
        if not merged.empty:
            merged = merged.sort_values(by="score", ascending=False).reset_index(drop=True)
            merged["Rank"] = merged.index + 1
            display_cols = ["Rank", "name", "score", "provider", "model", "stake", "agent_id"]
            st.dataframe(
                merged[display_cols].rename(columns={
                    "name": "Agent Label",
                    "score": f"{selected_method.capitalize()} Score",
                    "provider": "Provider",
                    "model": "Model",
                    "stake": "Stake",
                    "agent_id": "Agent ID",
                }),
                use_container_width=True,
            )

            # Chart
            fig, ax = plt.subplots(figsize=(10, 3.5))
            ax.barh(merged["name"], merged["score"], color="#38bdf8")
            ax.set_xlabel("Reputation Score")
            ax.set_xlim(0, 1.05)
            ax.invert_yaxis()
            ax.grid(axis="x", linestyle="--", alpha=0.5)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info(f"No reputation scores calculated yet for '{selected_method}'. Click 'Recalculate Reputations' in the sidebar.")
    else:
        st.info("No agents or reputation records in the database. Run the pipeline runner to generate data.")

# ---------------------------------------------------------------------------
# Tab 2: Algorithm Comparison
# ---------------------------------------------------------------------------
with tab2:
    st.subheader("Cross-Algorithm Scoring Comparison")
    st.markdown("Compare how different algorithms score agents. Notice how **TraceRank** suppresses high-variance or easy-task-farmed performance.")

    if not rep_df.empty and not agent_df.empty:
        pivot = rep_df.pivot(index="agent_id", columns="method", values="score").reset_index()
        pivot = pivot.merge(agent_df[["agent_id", "name", "stake"]], on="agent_id")

        st.dataframe(pivot, use_container_width=True)

        # Plot grouped comparison
        methods = [m for m in ["tracerank", "eigentrust", "pagerank", "weighted", "simple_avg"] if m in pivot.columns]
        if methods:
            chart_df = pivot.set_index("name")[methods]
            st.bar_chart(chart_df)
    else:
        st.info("Insufficient reputation data for comparison.")

# ---------------------------------------------------------------------------
# Tab 3: Sybil Resilience Benchmark
# ---------------------------------------------------------------------------
with tab3:
    st.subheader("Adversarial Sybil & Collusion Resilience")
    st.markdown("Empirical comparison of Top-K preservation and ranking stability under Sybil attacks ($N = 0, 5, 10, 20$ clones).")

    if st.button("⚡ Run Full Sybil Benchmark Suite"):
        with st.spinner("Simulating Sybil clones and evaluating resilience..."):
            exp_results = run_sybil_experiments()
            st.success("Benchmark completed and saved to `data/experiments/`!")

    exp_csv = Path("data/experiments/sybil_resilience.csv")
    if exp_csv.exists():
        exp_df = pd.read_csv(exp_csv)
        st.dataframe(exp_df, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Top-K Preservation vs Sybil Clones**")
            fig1, ax1 = plt.subplots(figsize=(6, 4))
            for m in exp_df["method"].unique():
                m_data = exp_df[exp_df["method"] == m]
                ax1.plot(m_data["clone_count"], m_data["top_k_preserved"], marker="o", label=m)
            ax1.set_xlabel("Number of Sybil Clones")
            ax1.set_ylabel("Top-K Preserved (1.0 = Intact)")
            ax1.set_ylim(-0.1, 1.1)
            ax1.legend()
            ax1.grid(True, linestyle="--", alpha=0.5)
            st.pyplot(fig1)

        with c2:
            st.markdown("**Kendall's Tau Ranking Stability**")
            fig2, ax2 = plt.subplots(figsize=(6, 4))
            for m in exp_df["method"].unique():
                m_data = exp_df[exp_df["method"] == m]
                ax2.plot(m_data["clone_count"], m_data["kendall_tau"], marker="s", label=m)
            ax2.set_xlabel("Number of Sybil Clones")
            ax2.set_ylabel("Kendall's Tau (Rank Correlation)")
            ax2.set_ylim(-0.1, 1.1)
            ax2.legend()
            ax2.grid(True, linestyle="--", alpha=0.5)
            st.pyplot(fig2)
    else:
        st.info("No benchmark results found. Click 'Run Full Sybil Benchmark Suite' above to run the experiment.")

# ---------------------------------------------------------------------------
# Tab 4: Blockchain & Merkle Audit Trail
# ---------------------------------------------------------------------------
with tab4:
    st.subheader("Cryptographic Audit & Merkle Verification")

    st.markdown("### On-Chain Anchor Commitments")
    if data["anchors"]:
        st.dataframe(pd.DataFrame(data["anchors"]), use_container_width=True)
    else:
        st.info("No anchors recorded in the ledger yet.")

    st.divider()
    st.markdown("### Independent Audit Bundle Verification")
    st.write("Upload or select an audit bundle JSON to mathematically verify Merkle proofs, score recomputation, and hash commitments.")

    bundles_dir = Path("data/bundles")
    bundle_files = list(bundles_dir.glob("*.json")) if bundles_dir.exists() else []

    selected_bundle_file = st.selectbox(
        "Available Audit Bundles on Disk",
        [str(f.name) for f in bundle_files] if bundle_files else ["No bundles found"],
    )

    uploaded_file = st.file_uploader("Or Upload Audit Bundle JSON", type=["json"])

    if st.button("🔍 Run Independent Verification"):
        target_bundle = None
        if uploaded_file is not None:
            target_bundle = json.load(uploaded_file)
        elif bundle_files and selected_bundle_file != "No bundles found":
            with open(bundles_dir / selected_bundle_file, "r", encoding="utf-8") as f:
                target_bundle = json.load(f)

        if target_bundle:
            verifier = StandaloneVerifier()
            res = verifier.verify_bundle(target_bundle, check_on_chain=False)
            st.markdown("#### Verification Results")
            if res.valid:
                st.success("✅ AUDIT PASSED: The bundle is cryptographically authentic and mathematically reproducible!")
            else:
                st.error("❌ AUDIT FAILED: Cryptographic tampering or calculation mismatch detected!")

            r_col1, r_col2 = st.columns(2)
            with r_col1:
                st.write(f"**Canonical Record Leaves**: {'✅ Valid' if res.leaves_valid else '❌ Invalid'}")
                st.write(f"**Merkle Root Integrity**: {'✅ Valid' if res.merkle_root_valid else '❌ Invalid'}")
                st.write(f"**Inclusion Proofs**: {'✅ Valid' if res.proofs_valid else '❌ Invalid'}")
                if res.difficulty_root_valid is not None:
                    st.write(f"**Difficulty Root**: {'✅ Valid' if res.difficulty_root_valid else '❌ Invalid'}")
                if res.params_hash_valid is not None:
                    st.write(f"**Params Hash**: {'✅ Valid' if res.params_hash_valid else '❌ Invalid'}")
                if res.ratings_root_valid is not None:
                    st.write(f"**Peer Ratings Root (Level B)**: {'✅ Valid' if res.ratings_root_valid else '❌ Invalid'}")
            with r_col2:
                st.write(f"**Claimed Score**: `{res.claimed_score:.6f}`")
                st.write(f"**Recomputed Score**: `{res.recomputed_score:.6f}`")
                st.write(f"**Score Hash Commitment**: {'✅ Valid' if res.score_hash_valid else '❌ Invalid'}")
                if res.level_a_valid is not None:
                    st.write(f"**Level A Verification**: {'✅ Valid' if res.level_a_valid else '❌ Invalid'}")
                if res.level_b_valid is not None:
                    st.write(f"**Level B Verification**: {'✅ Valid' if res.level_b_valid else '❌ Invalid'}")

            if res.direct_score > 0 or res.confidence > 0:
                st.info(f"**Recomputed Components**: Direct Evidence $D'$ = {res.direct_score:.4f} | Confidence $C_a$ = {res.confidence:.4f} | Trust $\\tilde{{T}}$ = {res.t_tilde:.4f} | Defense $\\pi$ = {res.defense_penalty:.4f}")

            if res.errors:
                st.error("Errors found:\n" + "\n".join(f"- {e}" for e in res.errors))
        else:
            st.warning("Please select or upload a valid audit bundle JSON.")

# ---------------------------------------------------------------------------
# Tab 5: Task Bank & Difficulty
# ---------------------------------------------------------------------------
with tab5:
    st.subheader("Benchmark Task Bank & Dynamic Difficulty")
    if data["tasks"]:
        tdf = pd.DataFrame(data["tasks"])
        st.dataframe(tdf, use_container_width=True)

        fig3, ax3 = plt.subplots(figsize=(8, 3.5))
        ax3.hist(tdf["difficulty_weight"], bins=15, color="#818cf8", edgecolor="#1e1b4b")
        ax3.set_xlabel("Empirical Difficulty Weight d_t (0.1 = Easy, 1.0 = Hard)")
        ax3.set_ylabel("Task Count")
        ax3.set_title("Distribution of Empirical Task Difficulties")
        ax3.grid(axis="y", linestyle="--", alpha=0.5)
        st.pyplot(fig3)
    else:
        st.info("No tasks loaded in the database.")

