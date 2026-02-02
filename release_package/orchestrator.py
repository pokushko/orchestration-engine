
import asyncio
from typing import List, Callable

class LiteAgent:
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role

    async def execute(self, task: str) -> str:
        print(f"[{self.name} - {self.role}] Processing: {task}")
        await asyncio.sleep(0.5)
        return f"Result from {self.name}: Completed {task}"

class Orchestrator:
    def __init__(self):
        self.agents: List[LiteAgent] = []

    def register(self, agent: LiteAgent):
        self.agents.append(agent)

    async def broadcast(self, task: str):
        results = await asyncio.gather(*(a.execute(task) for a in self.agents))
        return results

async def main():
    orc = Orchestrator()
    orc.register(LiteAgent("Scholar", "Literature Search"))
    orc.register(LiteAgent("Coder", "Implementation"))
    
    results = await orc.broadcast("Researching protein synthesis optimization")
    for res in results:
        print(res)

if __name__ == "__main__":
    asyncio.run(main())
