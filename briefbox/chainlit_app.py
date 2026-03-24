from __future__ import annotations

try:
    import chainlit as cl
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError("Chainlit is not installed. Install project dependencies before running the UI.") from exc


@cl.on_chat_start
async def start() -> None:
    await cl.Message(
        content=(
            "# BriefBox\n\n"
            "Scaffold is running.\n\n"
            "- Fixture selector: pending\n"
            "- Triage Inbox button: pending wiring\n"
            "- Board + trace layout: pending implementation\n"
        )
    ).send()
