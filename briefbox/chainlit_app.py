from __future__ import annotations

try:
    import chainlit as cl
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError("Chainlit is not installed. Install project dependencies before running the UI.") from exc

from briefbox.app.models import MessageAction
from briefbox.ui import (
    BriefBoxAPIClient,
    BriefBoxAPIError,
    UIState,
    parse_command,
    render_progress,
    render_result,
    render_shell,
)


def _get_state() -> UIState:
    state = cl.user_session.get("ui_state")
    if state is None:
        state = UIState()
        cl.user_session.set("ui_state", state)
    return state


@cl.on_chat_start
async def start() -> None:
    cl.user_session.set("api_client", BriefBoxAPIClient())
    cl.user_session.set("ui_state", UIState())
    await cl.Message(content=render_shell(_get_state())).send()


@cl.on_message
async def handle_message(message: cl.Message) -> None:
    state = _get_state()
    client: BriefBoxAPIClient = cl.user_session.get("api_client")
    command, argument = parse_command(message.content)

    try:
        if command == "fixture" and argument:
            await client.get_fixture_summary(argument)
            state.fixture_id = argument
            await cl.Message(content=render_shell(state)).send()
            return

        if command == "triage":
            run = await client.create_run(state.fixture_id)
            state.run_id = run["run_id"]
            status = await client.get_run_status(state.run_id)
            await cl.Message(content=render_progress(status)).send()
            result = await client.get_run_result(state.run_id)
            await cl.Message(content=render_result(result)).send()
            return

        if command == "refresh":
            if not state.run_id:
                raise BriefBoxAPIError("No active run. Start one with `triage`.")
            result = await client.get_run_result(state.run_id)
            await cl.Message(content=render_result(result)).send()
            return

        if command in {"pin", "archive", "snooze"} and argument:
            if not state.run_id:
                raise BriefBoxAPIError("No active run. Start one with `triage`.")
            await client.apply_action(state.run_id, argument, MessageAction(command))
            result = await client.get_run_result(state.run_id)
            await cl.Message(content=render_result(result)).send()
            return

        if command == "unsubscribe" and argument:
            if not state.run_id:
                raise BriefBoxAPIError("No active run. Start one with `triage`.")
            await client.unsubscribe(state.run_id, argument)
            result = await client.get_run_result(state.run_id)
            await cl.Message(content=render_result(result)).send()
            return

        await cl.Message(
            content=(
                "Unknown command. Use `triage`, `fixture <id>`, "
                "`pin/archive/snooze <message_id>`, `unsubscribe <message_id>`, "
                "or `refresh`."
            )
        ).send()
    except BriefBoxAPIError as exc:
        await cl.Message(content=f"Error: {exc}").send()
