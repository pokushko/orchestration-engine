# Orchestration Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Architecture: AsyncIO](https://img.shields.io/badge/Architecture-AsyncIO%20MAS-emerald.svg)](https://github.com/pokushko/orchestration-engine)

A lightweight, zero-dependency Python `asyncio` orchestration engine for Multi-Agent Systems (MAS). Supports concurrent scatter-gather broadcast, fault-isolated agent execution with timeouts and retries, topologically validated DAG pipelines, and consensus reducers. Part of the [EvoNova Labs](https://github.com/pokushko) open-source resilience stack.

```mermaid
graph TD
    User([Task Ingestion]) --> Orchestrator[Orchestration Engine]
    Orchestrator --> AgentA[Agent: Scholar]
    Orchestrator --> AgentB[Agent: Coder]
    Orchestrator --> AgentC[Agent: Critic]
    AgentA --> DAG[DAG / Consensus Reducer]
    AgentB --> DAG
    AgentC --> DAG
    DAG --> Out([Verified Result])
```

---

## Key Features

- **Broadcast with Fault Isolation:** Concurrent task dispatch via `asyncio.gather` returning structured `AgentResult` records so one failing agent never crashes the fleet.
- **DAG Workflow Execution (`run_dag`):** Kahn's topological sort validates dependency graphs upfront (catching cycles and missing references before execution), runs independent waves concurrently, and passes upstream outputs into downstream tasks.
- **Timeouts & Exponential Backoff Retries:** Configurable `timeout_s`, `max_retries`, and `retry_delay_s` per `LiteAgent`.
- **Consensus Reducers:** Built-in majority vote or custom sync/async reducer callbacks across agent outputs.
- **Zero External Runtime Dependencies:** Uses Python 3.10+ standard library only.

---

## Quickstart

### Installation

```bash
git clone https://github.com/pokushko/orchestration-engine.git
cd orchestration-engine
pip install -e .
```

### Usage Examples

```python
import asyncio
from orchestrator import LiteAgent, Orchestrator


async def run_workflows() -> None:
    engine = Orchestrator()
    engine.register(LiteAgent("Scholar", "Literature Search", handler=lambda t: f"papers:{t}"))
    engine.register(LiteAgent("Coder", "Implementation", handler=lambda t: f"code:{t}"))
    engine.register(LiteAgent("Critic", "Verifier", handler=lambda t: f"audit({t})"))

    # 1. Parallel broadcast
    broadcast_outputs = await engine.broadcast("agent resilience")
    print("Broadcast:", broadcast_outputs)

    # 2. DAG pipeline (Scholar and Coder run concurrently, Critic consumes both)
    dag_results = await engine.run_dag(
        {
            "research": {"agent": "Scholar", "task": "memory bounds"},
            "implement": {"agent": "Coder", "task": "wal_journal"},
            "verify": {
                "agent": "Critic",
                "task": "{research} | {implement}",
                "depends_on": ["research", "implement"],
            },
        }
    )
    print("DAG final:", dag_results["verify"].output)

    # 3. Majority consensus
    verdict = await engine.consensus("approve release")
    print("Consensus:", verdict["winner"])


if __name__ == "__main__":
    asyncio.run(run_workflows())
```

---

## Running Tests

```bash
pip install pytest
pytest -v
```

---

## Author & Ecosystem

**Roman Pokushko** — Founder & Lead AI Architect @ EvoNova Labs  
Contact: [pokusko.roman@gmail.com](mailto:pokusko.roman@gmail.com) | GitHub: [@pokushko](https://github.com/pokushko)  
Related Projects: [Awesome Autonomous Agent Resilience](https://github.com/pokushko/awesome-autonomous-agent-resilience) | [AgentBunker](https://github.com/pokushko/agent-bunker) | [Agent Security Sandbox](https://github.com/pokushko/agent-security-sandbox) | [Agentic Vector Memory](https://github.com/pokushko/agentic-vector-memory)

## License

MIT License. See [LICENSE](LICENSE).
