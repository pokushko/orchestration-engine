"""Lightweight asynchronous multi-agent orchestration engine with DAG workflows, retries, and consensus."""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass
import inspect
import time
from typing import Any, Optional


@dataclass(frozen=True)
class AgentResult:
    """Structured execution outcome returned by an agent invocation."""

    agent_name: str
    role: str
    output: Any
    ok: bool
    error: Optional[str] = None
    latency_ms: float = 0.0


class LiteAgent:
    """Asynchronous agent wrapper supporting custom handlers, timeouts, and retries."""

    def __init__(
        self,
        name: str,
        role: str,
        handler: Optional[Callable[[str], Any]] = None,
        timeout_s: float = 30.0,
        max_retries: int = 0,
        retry_delay_s: float = 0.05,
    ) -> None:
        self.name = name
        self.role = role
        self.handler = handler
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.retry_delay_s = retry_delay_s

    async def _invoke_once(self, task: str) -> Any:
        if self.handler is None:
            return f"Result from {self.name}: Completed {task}"
        outcome = self.handler(task)
        if inspect.isawaitable(outcome):
            return await outcome
        return outcome

    async def execute(self, task: str) -> Any:
        """Execute a task with bounded timeout and retry backoff."""
        last_exc: Optional[BaseException] = None
        for attempt in range(self.max_retries + 1):
            try:
                return await asyncio.wait_for(self._invoke_once(task), timeout=self.timeout_s)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay_s * (2**attempt))
        assert last_exc is not None
        raise last_exc

    async def execute_result(self, task: str) -> AgentResult:
        """Execute a task and capture output or error inside an AgentResult."""
        started = time.perf_counter()
        try:
            output = await self.execute(task)
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            return AgentResult(
                agent_name=self.name,
                role=self.role,
                output=output,
                ok=True,
                error=None,
                latency_ms=elapsed_ms,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
            return AgentResult(
                agent_name=self.name,
                role=self.role,
                output=None,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=elapsed_ms,
            )


class Orchestrator:
    """Asynchronous multi-agent dispatcher supporting broadcast, DAG pipelines, and consensus."""

    def __init__(self) -> None:
        self.agents: list[LiteAgent] = []

    def register(self, agent: LiteAgent) -> None:
        """Register an agent with unique name check."""
        if self.get_agent(agent.name) is not None:
            raise ValueError(f"Agent '{agent.name}' is already registered.")
        self.agents.append(agent)

    def get_agent(self, name: str) -> Optional[LiteAgent]:
        """Look up a registered agent by name."""
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None

    async def broadcast(
        self,
        task: str,
        *,
        isolate_errors: bool = True,
        return_results: bool = False,
    ) -> list[Any]:
        """Dispatch a task to all registered agents concurrently."""
        if not self.agents:
            return []

        if isolate_errors:
            results = list(await asyncio.gather(*(a.execute_result(task) for a in self.agents)))
            if return_results:
                return results
            return [
                r.output if r.ok else f"Error from {r.agent_name}: {r.error}"
                for r in results
            ]

        outputs = list(await asyncio.gather(*(a.execute(task) for a in self.agents)))
        if return_results:
            return [
                AgentResult(agent_name=a.name, role=a.role, output=out, ok=True)
                for a, out in zip(self.agents, outputs)
            ]
        return outputs

    async def run_dag(self, tasks: dict[str, dict[str, Any]]) -> dict[str, AgentResult]:
        """Validate dependencies via topological sort and execute independent DAG waves concurrently."""
        if not tasks:
            return {}

        indegree: dict[str, int] = {}
        dependents: dict[str, list[str]] = {node_id: [] for node_id in tasks}

        for node_id, spec in tasks.items():
            agent_name = str(spec.get("agent", ""))
            if self.get_agent(agent_name) is None:
                raise ValueError(f"Task '{node_id}' references unknown agent '{agent_name}'.")
            if "task" not in spec:
                raise ValueError(f"Task '{node_id}' is missing required 'task' prompt.")

            deps = list(spec.get("depends_on", []))
            indegree[node_id] = len(deps)
            for dep in deps:
                if dep not in tasks:
                    raise ValueError(f"Task '{node_id}' depends on unknown task '{dep}'.")
                if dep == node_id:
                    raise ValueError(f"Task '{node_id}' cannot depend on itself.")
                dependents[dep].append(node_id)

        # Kahn's algorithm validates acyclicity and computes parallel execution waves.
        ready: deque[str] = deque(nid for nid, deg in indegree.items() if deg == 0)
        waves: list[list[str]] = []
        visited = 0

        while ready:
            wave = list(ready)
            ready.clear()
            waves.append(wave)
            for nid in wave:
                visited += 1
                for child in dependents[nid]:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        ready.append(child)

        if visited != len(tasks):
            raise ValueError("Cycle detected in task DAG.")

        completed: dict[str, AgentResult] = {}

        async def _run_node(node_id: str) -> tuple[str, AgentResult]:
            spec = tasks[node_id]
            deps = list(spec.get("depends_on", []))
            failed_deps = [d for d in deps if not completed[d].ok]
            agent = self.get_agent(str(spec["agent"]))
            assert agent is not None

            if failed_deps:
                return node_id, AgentResult(
                    agent_name=agent.name,
                    role=agent.role,
                    output=None,
                    ok=False,
                    error=f"Skipped due to failed upstream dependencies: {', '.join(failed_deps)}",
                    latency_ms=0.0,
                )

            prompt = str(spec["task"])
            if deps:
                dep_context = {d: completed[d].output for d in deps}
                try:
                    prompt = prompt.format(**dep_context)
                except (KeyError, IndexError, ValueError):
                    summary = "; ".join(f"{d}={dep_context[d]}" for d in deps)
                    prompt = f"{prompt}\n\n[Upstream Context]: {summary}"

            result = await agent.execute_result(prompt)
            return node_id, result

        for wave in waves:
            wave_outcomes = await asyncio.gather(*(_run_node(nid) for nid in wave))
            for node_id, result in wave_outcomes:
                completed[node_id] = result

        return completed

    async def consensus(
        self,
        task: str,
        reducer: Optional[Callable[[list[AgentResult]], Any]] = None,
    ) -> Any:
        """Broadcast task to all agents and synthesize consensus via custom reducer or majority vote."""
        results: list[AgentResult] = await self.broadcast(
            task,
            isolate_errors=True,
            return_results=True,
        )
        if reducer is not None:
            reduced = reducer(results)
            if inspect.isawaitable(reduced):
                return await reduced
            return reduced

        successful = [r.output for r in results if r.ok]
        if not successful:
            return {
                "winner": None,
                "votes": 0,
                "total_agents": len(results),
                "successful_agents": 0,
                "results": results,
            }

        counts = Counter(successful)
        winner, votes = counts.most_common(1)[0]
        return {
            "winner": winner,
            "votes": votes,
            "total_agents": len(results),
            "successful_agents": len(successful),
            "results": results,
        }


async def main() -> None:
    orc = Orchestrator()
    orc.register(LiteAgent("Scholar", "Literature Search"))
    orc.register(LiteAgent("Coder", "Implementation"))
    for res in await orc.broadcast("Researching resilient multi-agent coordination"):
        print(res)


if __name__ == "__main__":
    asyncio.run(main())
