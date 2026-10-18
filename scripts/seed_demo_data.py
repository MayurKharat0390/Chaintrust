"""
scripts/seed_demo_data.py
Seeds realistic benchmark tasks, agents, and graded interaction logs into chaintrust.db,
computes reputation scores across all 5 algorithms, generates Merkle audit bundles, and anchors them.
This allows the dashboard and APIs to be instantly demo-ready for presentations.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from chaintrust.anchoring.bundle import create_epoch_bundle
from chaintrust.anchoring.chain_client import ChainClient
from chaintrust.db.models import Agent, Interaction, Reputation, Task, TaskSource
from chaintrust.db.session import get_session, init_db
from chaintrust.registry.agent_registry import AgentRegistry
from chaintrust.reputation.engine import ReputationEngine


def seed_database() -> None:
    print("1. Initialising database schema...")
    init_db()

    print("2. Registering enabled agents from config/agents.yaml...")
    registry = AgentRegistry()
    registry.register_all()

    with get_session() as session:
        agents = session.query(Agent).all()
        print(f"   Registered {len(agents)} agents.")

        print("3. Seeding benchmark tasks (HumanEval & MBPP)...")
        tasks = []
        # Seed 20 representative coding tasks
        sample_tasks = [
            ("humaneval/HumanEval_0", TaskSource.HUMANEVAL, "has_close_elements(numbers, threshold)", "has_close_elements"),
            ("humaneval/HumanEval_1", TaskSource.HUMANEVAL, "separate_paren_groups(paren_string)", "separate_paren_groups"),
            ("humaneval/HumanEval_2", TaskSource.HUMANEVAL, "truncate_number(number)", "truncate_number"),
            ("humaneval/HumanEval_3", TaskSource.HUMANEVAL, "below_zero(operations)", "below_zero"),
            ("humaneval/HumanEval_4", TaskSource.HUMANEVAL, "mean_absolute_deviation(numbers)", "mean_absolute_deviation"),
            ("humaneval/HumanEval_5", TaskSource.HUMANEVAL, "intersperse(numbers, delimiter)", "intersperse"),
            ("humaneval/HumanEval_6", TaskSource.HUMANEVAL, "parse_nested_parens(paren_string)", "parse_nested_parens"),
            ("humaneval/HumanEval_7", TaskSource.HUMANEVAL, "filter_by_substring(strings, substring)", "filter_by_substring"),
            ("humaneval/HumanEval_8", TaskSource.HUMANEVAL, "sum_product(numbers)", "sum_product"),
            ("humaneval/HumanEval_9", TaskSource.HUMANEVAL, "rolling_max(numbers)", "rolling_max"),
            ("mbpp/mbpp_1", TaskSource.MBPP, "min_cost_path(matrix)", "min_cost_path"),
            ("mbpp/mbpp_2", TaskSource.MBPP, "similar_elements(tuple1, tuple2)", "similar_elements"),
            ("mbpp/mbpp_3", TaskSource.MBPP, "is_not_prime(n)", "is_not_prime"),
            ("mbpp/mbpp_4", TaskSource.MBPP, "heap_queue_largest(numbers, n)", "heap_queue_largest"),
            ("mbpp/mbpp_5", TaskSource.MBPP, "count_ways_to_split(array)", "count_ways_to_split"),
            ("mbpp/mbpp_6", TaskSource.MBPP, "diff_even_odd(numbers)", "diff_even_odd"),
            ("mbpp/mbpp_7", TaskSource.MBPP, "find_char_long(text)", "find_char_long"),
            ("mbpp/mbpp_8", TaskSource.MBPP, "square_sum(n)", "square_sum"),
            ("mbpp/mbpp_9", TaskSource.MBPP, "minimum_rotations(string)", "minimum_rotations"),
            ("mbpp/mbpp_10", TaskSource.MBPP, "is_woodall(n)", "is_woodall"),
        ]

        for tid, src, prompt, ep in sample_tasks:
            existing_t = session.get(Task, tid)
            if not existing_t:
                t = Task(
                    task_id=tid,
                    source=src,
                    prompt=f"def {prompt}:\n    '''Implement the solution'''\n    pass",
                    entry_point=ep,
                    tests="def check(candidate):\n    assert candidate is not None",
                )
                session.add(t)
                tasks.append(t)
            else:
                tasks.append(existing_t)
        session.commit()
        print(f"   Tasks ready: {len(tasks)} tasks.")

        # Check existing interactions
        if session.query(Interaction).count() == 0:
            print("4. Generating realistic interaction logs...")
            now = datetime.now(timezone.utc)
            random.seed(42)

            # Assign skill levels to models
            skill_map = {
                "gemini-flash-default": 0.82,
                "gemini-flash-creative": 0.74,
                "llama3-groq-default": 0.78,
                "llama3-groq-conservative": 0.80,
                "mistral-openrouter": 0.65,
                "phi3-openrouter": 0.58,
                "llama3-local": 0.62,
                "qwen2.5-coder-local": 0.85,
            }

            for agent in agents:
                base_skill = skill_map.get(agent.name, 0.70)
                for task in tasks:
                    for attempt in range(1, 3):  # 2 attempts per task
                        # Task intrinsic difficulty factor
                        t_num = int(task.task_id.split("_")[-1])
                        task_hardness = 0.15 + 0.035 * t_num

                        p_pass = max(0.1, min(0.95, base_skill - task_hardness * 0.4 + random.uniform(-0.1, 0.1)))
                        passed = random.random() < p_pass
                        passed_tests = random.randint(8, 10) if passed else random.randint(2, 6)
                        total_tests = 10
                        quality = passed_tests / total_tests

                        inter = Interaction(
                            agent_id=agent.agent_id,
                            task_id=task.task_id,
                            attempt=attempt,
                            passed=passed,
                            tests_passed=passed_tests,
                            tests_total=total_tests,
                            quality_score=quality,
                            runtime_ms=random.randint(45, 280),
                            tokens_in=random.randint(120, 350),
                            tokens_out=random.randint(80, 240),
                            latency_ms=random.randint(300, 1200),
                            timestamp=now - timedelta(days=random.uniform(0.1, 14.0)),
                        )
                        session.add(inter)
            session.commit()
            print(f"   Created {session.query(Interaction).count()} interaction records.")

    print("5. Computing multi-algorithm reputation scores...")
    engine = ReputationEngine()
    with get_session() as session:
        res_epoch1 = engine.compute_epoch_scores(session, epoch=1)

    print("6. Generating audit bundles and anchoring on-chain...")
    with get_session() as session:
        top_agents = session.query(Agent).limit(3).all()
        client = ChainClient()

        for ag in top_agents:
            inters = session.query(Interaction).filter_by(agent_id=ag.agent_id).all()
            score = res_epoch1["tracerank"].get(ag.agent_id, 0.8)

            bundle, path = create_epoch_bundle(
                agent_id=ag.agent_id,
                epoch=1,
                interactions=inters,
                method="tracerank",
                score=score,
                stake=ag.stake,
            )

            client.anchor_root(
                agent_id=ag.agent_id,
                epoch=1,
                merkle_root=bundle["metadata"]["merkle_root"],
                score_hash=bundle["metadata"]["score_hash"],
                session=session,
            )
            print(f"   Anchored agent {ag.name} (root: {bundle['metadata']['merkle_root'][:16]}...)")

    print("\n[SUCCESS] Demo database successfully seeded and ready!")


if __name__ == "__main__":
    seed_database()
