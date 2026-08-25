from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from langgraph_agent_lab.persistence import build_checkpointer


class CounterState(TypedDict):
    count: int


def increment(state: CounterState) -> dict[str, int]:
    return {"count": state["count"] + 1}


def test_sqlite_checkpoint_survives_reopen(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.db"
    config = {"configurable": {"thread_id": "durable-test"}}

    builder = StateGraph(CounterState)
    builder.add_node("increment", increment)
    builder.add_edge(START, "increment")
    builder.add_edge("increment", END)

    first_saver = build_checkpointer("sqlite", str(database))
    first_graph = builder.compile(checkpointer=first_saver)
    assert first_graph.invoke({"count": 0}, config=config)["count"] == 1
    first_saver.conn.close()

    reopened_saver = build_checkpointer("sqlite", str(database))
    reopened_graph = builder.compile(checkpointer=reopened_saver)
    snapshot = reopened_graph.get_state(config)
    assert snapshot.values["count"] == 1
    assert list(reopened_graph.get_state_history(config))
    reopened_saver.conn.close()
