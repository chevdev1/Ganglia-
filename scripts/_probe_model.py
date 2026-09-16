import asyncio
from backend.config import get_settings
from backend.services.neural import SoftwareNeuralProvider
from backend.services.writer import ModelWriter

settings = get_settings()
writer = ModelWriter(settings)
# temporarily disable soft fallback to see the real error
settings.allow_software_writer = False
writer._settings = settings


async def main() -> None:
    features = SoftwareNeuralProvider().observe("test")
    try:
        draft = await writer.write(
            trigger="scenario",
            scenario="Why do harbours keep returning in quiet rooms?",
            node_id=4,
            summary="quiet rooms and harbours",
            recent=["the shared room is mostly air"],
            node_memory=["scenario: harbour light"],
            curiosity=7,
            intensity=4,
            warmth=6,
            focus=5,
            restlessness=4,
            unresolved_thought="",
            features=features,
        )
        print("OK", draft.writer)
        print(draft.text)
        print(draft.summary)
        print(draft.curiosity, draft.focus, draft.unresolved_thought)
    except Exception as exc:
        print("FAIL", type(exc).__name__, exc)


asyncio.run(main())
