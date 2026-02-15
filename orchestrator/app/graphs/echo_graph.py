from typing import TypedDict
from langgraph.graph import StateGraph, END


class AgentState(TypedDict):
    """State for the echo graph."""
    user_id: str
    input: str
    output: str


def node_echo(state: AgentState) -> AgentState:
    """Echo node that formats output with user_id and input."""
    return {
        "user_id": state["user_id"],
        "input": state["input"],
        "output": f"{state['user_id']}: {state['input']}"
    }


def create_echo_graph() -> StateGraph:
    """Create and compile the echo graph."""
    # Create the graph
    graph = StateGraph(AgentState)
    
    # Add the echo node
    graph.add_node("echo", node_echo)
    
    # Set entry point
    graph.set_entry_point("echo")
    
    # Add edge from echo to END
    graph.add_edge("echo", END)
    
    # Compile and return
    return graph.compile()


# Create the compiled graph instance
echo_graph = create_echo_graph()

