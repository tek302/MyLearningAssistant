from typing import Annotated
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.graphs.echo_graph import echo_graph, AgentState
from app.utils.deps import get_user_id

router = APIRouter(prefix="/graph", tags=["graph"])


class EchoRequest(BaseModel):
    input: str


class EchoResponse(BaseModel):
    output: str


@router.post("/echo", response_model=EchoResponse)
async def echo(
    request: EchoRequest,
    user_id: Annotated[str, Depends(get_user_id)]
):
    """
    Echo endpoint that runs the echo graph.
    
    Args:
        request: Request body with input text
        user_id: User ID from authentication token
        
    Returns:
        EchoResponse with formatted output
    """
    # Prepare initial state
    initial_state: AgentState = {
        "user_id": user_id,
        "input": request.input,
        "output": ""
    }
    
    # Run the graph
    result = echo_graph.invoke(initial_state)
    
    # Return the output
    return EchoResponse(output=result["output"])

