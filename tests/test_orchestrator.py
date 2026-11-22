import asyncio
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import AgentResult, LiteAgent, Orchestrator


def test_broadcast_backward_compatible_and_fault_isolated():
    async def _run():
        orc = Orchestrator()
        orc.register(LiteAgent("Alpha", "Researcher"))

        def failing_handler(_task: str) -> str:
            raise RuntimeError("upstream timeout")

        orc.register(LiteAgent("Beta", "Worker", handler=failing_handler))

        outputs = await orc.broadcast("audit logs")
        assert len(outputs) == 2
        assert outputs[0] == "Result from Alpha: Completed audit logs"
        assert outputs[1].startswith("Error from Beta: RuntimeError:")

        results = await orc.broadcast("audit logs", return_results=True)
        assert isinstance(results[0], AgentResult)
        assert results[0].ok is True
        assert results[1].ok is False

    asyncio.run(_run())


def test_agent_retry_and_timeout():
    async def _run():
        attempts = {"count": 0}

        async def flaky_handler(task: str) -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ConnectionError("transient error")
            return f"recovered:{task}"

        retrying = LiteAgent("Retrier", "Fetcher", handler=flaky_handler, max_retries=2, retry_delay_s=0.01)
        res = await retrying.execute_result("sync")
        assert res.ok is True
        assert res.output == "recovered:sync"
        assert attempts["count"] == 3

        async def slow_handler(_task: str) -> str:
            await asyncio.sleep(0.5)
            return "too_late"

        timed_out = LiteAgent("SlowAgent", "Runner", handler=slow_handler, timeout_s=0.02)
        res_timeout = await timed_out.execute_result("heavy")
        assert res_timeout.ok is False
        assert "TimeoutError" in (res_timeout.error or "")

    asyncio.run(_run())


def test_run_dag_parallel_waves_and_context_handoff():
    async def _run():
        orc = Orchestrator()
        orc.register(LiteAgent("Fetcher", "Collector", handler=lambda t: f"data({t})"))
        orc.register(LiteAgent("Critic", "Reviewer", handler=lambda t: f"critique({t})"))
        orc.register(LiteAgent("Writer", "Synthesizer", handler=lambda t: f"final[{t}]"))

        results = await orc.run_dag(
            {
                "fetch": {"agent": "Fetcher", "task": "papers"},
                "critique": {"agent": "Critic", "task": "methods"},
                "synthesize": {
                    "agent": "Writer",
                    "task": "{fetch} + {critique}",
                    "depends_on": ["fetch", "critique"],
                },
            }
        )
        assert results["fetch"].ok is True
        assert results["critique"].ok is True
        assert results["synthesize"].ok is True
        assert results["synthesize"].output == "final[data(papers) + critique(methods)]"

    asyncio.run(_run())


def test_run_dag_cycle_and_unknown_refs_raise():
    async def _run():
        orc = Orchestrator()
        orc.register(LiteAgent("A", "RoleA"))

        with pytest.raises(ValueError, match="Cycle detected"):
            await orc.run_dag(
                {
                    "n1": {"agent": "A", "task": "t1", "depends_on": ["n2"]},
                    "n2": {"agent": "A", "task": "t2", "depends_on": ["n1"]},
                }
            )

        with pytest.raises(ValueError, match="unknown agent"):
            await orc.run_dag({"n1": {"agent": "Missing", "task": "t1"}})

        with pytest.raises(ValueError, match="unknown task"):
            await orc.run_dag({"n1": {"agent": "A", "task": "t1", "depends_on": ["ghost"]}})

    asyncio.run(_run())


def test_consensus_majority_and_custom_reducer():
    async def _run():
        orc = Orchestrator()
        orc.register(LiteAgent("A1", "Judge", handler=lambda _: "APPROVE"))
        orc.register(LiteAgent("A2", "Judge", handler=lambda _: "APPROVE"))
        orc.register(LiteAgent("A3", "Judge", handler=lambda _: "REJECT"))

        verdict = await orc.consensus("proposal_42")
        assert verdict["winner"] == "APPROVE"
        assert verdict["votes"] == 2
        assert verdict["successful_agents"] == 3

        custom = await orc.consensus(
            "proposal_42",
            reducer=lambda res: sorted(r.agent_name for r in res if r.ok and r.output == "APPROVE"),
        )
        assert custom == ["A1", "A2"]

    asyncio.run(_run())
