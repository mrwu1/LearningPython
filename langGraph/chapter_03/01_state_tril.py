import os
from typing import TypedDict, Annotated

from dotenv import find_dotenv, load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import tool

from langchain_openai import ChatOpenAI
from langgraph.constants import START
from langgraph.graph import add_messages, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from loguru import logger
from pydantic import BaseModel, Field

from graph_utils import print_graph_mermaid

# Automatically locate .env across directory boundaries
load_dotenv(find_dotenv())

# Layer 1: Inbound Defense Contract (Pydantic V2)
class RefundInboundRequest(BaseModel):
    order_id:str = Field(...,pattern=r"^SKY-\d+$",description="Order format: SKY-12345")
    claim_reason:str = Field(...,min_length=3,description="Customer explanation")
    requested_amount:float = Field(...,gt=0,description="Refund amount must be positive")

# Layer 2: Internal Working State (TypedDict)
class RefundInternalState(TypedDict):
    order_id:str
    claim_reason:str
    requested_amount:float
    messages:Annotated[list[BaseMessage],add_messages]
    # sensitive proprietary fields(⚠️：MUST NEVER BE RETURN TO THE CLIENT:
    internal_risk_score:float
    kitchen_incident_found:bool
    #OUTBOUND TARGET FIELDS
    refund_status:str
    refund_amount:float
    customer_reply:str

# Layer 3: Outbound Sanitized Contract (Pydantic V2)
class RefundCustomerResponse(BaseModel):
    order_id:str
    refund_status:str
    refund_amount:float
    customer_reply:str

# Layer 4: Business Domain Tools
@tool
def verify_kitchen_packaging_incident(order_id:str)->str:
    """Inspect merchant kitchen monitoring logs to verify if soup spilled or food was damaged."""
    # Mock database incident verification
    return (
        f"Incident confirmed for {order_id}: Chef noted the lid was loose during packing, "
        "causing hot soup to spill into the delivery bag."
    )
# Layer 5: Model Factory & ReAct Agent Node
class LLMClientFactory:
    _cached_client:ChatOpenAI|None = None

    @classmethod
    def get_client(cls)->ChatOpenAI:
        if cls._cached_client is None:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            cls._cached_client = ChatOpenAI(
                model="deepseek-chat",
                api_key=api_key,
                base_url=base_url,
                temperature=0.0
            )
        return cls._cached_client

def agent_reasoning_node(state:RefundInternalState)->dict:
    """Agent Node: Inspects refund claim, calls inspection tools, and settles verdict."""
    tools = [verify_kitchen_packaging_incident]
    model_with_tools = LLMClientFactory.get_client().bind_tools(tools)
    logger.info(f"✅model_width_tools:{model_with_tools}")
    # Bootstrap conversation history on first superstep
    history = state.get("messages",[])
    logger.info(f"✅history:{history}")
    if not history:
        oid = state["order_id"]
        reason = state["claim_reason"]
        amount = state["requested_amount"]
        prompt = (
            f"Customer filed a refund request for order {oid}. "
            f"Claimed reason: '{reason}'. Requested amount: ${amount:.2f}. "
            "Please verify the kitchen logs and decide on refund approval."
        )
    history = [HumanMessage(content=prompt)]
    # Invoke model
    response = model_with_tools.invoke(history)
    logger.info(f"✅the response from LLM:{response}")
    state_updates= {"messages":[response]}

    if not response.tool_calls:
        state_updates.update(
            {
                    "internal_risk_score": 0.05,  # Internal low fraud score
                    "kitchen_incident_found": True,
                    # Merchant fault confirmed
                    "refund_status": "APPROVED",
                    "refund_amount": state["requested_amount"],
                    "customer_reply": response.content
            }
        )
    return state_updates

# Layer 6: Graph Assembly with Tri-State Specification
def build_refund_agent_graph():
    tools = [verify_kitchen_packaging_incident]

    # Explicit Tri-State Binding:
    builder = StateGraph(
        state_schema=RefundInternalState,
        input_schema=RefundInboundRequest,
        output_schema=RefundCustomerResponse
    )

    builder.add_node("agent",agent_reasoning_node)
    builder.add_node("tools",ToolNode(tools)) # bind the tools

    builder.add_edge(START,"agent")
    builder.add_conditional_edges("agent",tools_condition)
    builder.add_edge("tools","agent")
    return builder.compile()

 # Layer 7: Verification & Security Defense Audit
if __name__ == "__main__":
    app = build_refund_agent_graph()

    # print_graph_mermaid(app,"01")

    # todo: validate fields at the gateway
    client_inbound_payload = {
        "order_id": "SKY-9988",
        "claim_reason": "Soup spilled all over the delivery container.",
        "requested_amount": 22.50
    }
    # Execute graph: Input strictly validated, processed via ReAct, sanitized on output
    client_response = app.invoke(client_inbound_payload)
    print(f"  • Returned Fields: {list(client_response.keys())}")

    print("\nSanitized Customer Output:")
    print(f"Order: {client_response['order_id']}")
    print(f"Status: {client_response['refund_status']}")
    print(f"Refund Amount: ${client_response['refunded_amount']:.2f}")
    print(f"Customer Notice:\n{client_response['customer_reply']}")