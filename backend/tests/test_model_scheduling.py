import asyncio

from app.services.ai.models import ModelGate


def test_interactive_work_precedes_queued_background_and_cancellation_releases_waiter():
    async def exercise():
        gate = ModelGate()
        order = []

        async def run(name, interactive=False):
            async with gate.slot(interactive):
                order.append(name)

        async with gate.slot():
            background = asyncio.create_task(run("background"))
            cancelled = asyncio.create_task(run("cancelled", True))
            interactive = asyncio.create_task(run("question", True))
            await asyncio.sleep(0)
            cancelled.cancel()
            await asyncio.gather(cancelled, return_exceptions=True)
        await asyncio.wait_for(asyncio.gather(background, interactive), 2)
        assert order == ["question", "background"]
        assert not gate.waiters and not gate.busy

    asyncio.run(exercise())
