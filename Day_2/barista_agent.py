import asyncio
import json
import logging
from typing import Annotated

from livekit import agents
from livekit.agents import JobContext, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import openai, silero, deepgram

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("barista-agent")

# 1. Define the Order State Structure
class OrderState:
    def __init__(self):
        self.data = {
            "drinkType": None,
            "size": None,
            "milk": None,
            "extras": [],
            "name": None
        }

    def is_complete(self):
        # Check if required fields are filled (extras can be empty)
        return all(self.data[k] is not None for k in ["drinkType", "size", "milk", "name"])

    def save_to_json(self):
        filename = f"order_{self.data['name']}.json"
        with open(filename, "w") as f:
            json.dump(self.data, f, indent=2)
        logger.info(f"Order saved to {filename}")
        return filename

# 2. Define the Agent Logic
async def entrypoint(ctx: JobContext):
    # Initialize the context for this specific user session
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=(
            "You are a friendly, energetic barista at 'NeuroBrew Coffee'. "
            "Your goal is to take a complete coffee order. "
            "You must fill in the following fields: Drink Type, Size, Milk preference, Extras (optional), and Customer Name. "
            "Do not make up information. If a user hasn't specified something (like size or milk), ask them clarifying questions. "
            "Once you have all the details, confirm the order with the user. "
            "When the order is confirmed and complete, call the 'finalize_order' function."
        ),
    )

    # Create an instance of the order state for this session
    current_order = OrderState()

    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    # 3. Define the Tools (Functions the AI can call)
    
    @llm.ai_callable(description="Update the current order with details provided by the customer.")
    def update_order(
        drink_type: Annotated[str, llm.TypeInfo(description="The type of drink (e.g., Latte, Cappuccino)")] = None,
        size: Annotated[str, llm.TypeInfo(description="Size of the drink (Small, Medium, Large)")] = None,
        milk: Annotated[str, llm.TypeInfo(description="Type of milk (Whole, Oat, Almond, Soy, None)")] = None,
        extra: Annotated[str, llm.TypeInfo(description="Add an extra item (e.g., Sugar, Whipped Cream)")] = None,
        name: Annotated[str, llm.TypeInfo(description="Customer's name")] = None,
    ):
        # Update the state if the AI provides new values
        if drink_type: current_order.data["drinkType"] = drink_type
        if size: current_order.data["size"] = size
        if milk: current_order.data["milk"] = milk
        if name: current_order.data["name"] = name
        if extra: current_order.data["extras"].append(extra)
        
        logger.info(f"Current Order State: {current_order.data}")
        return f"Order updated. Current state: {current_order.data}"

    @llm.ai_callable(description="Call this only when the order is complete and confirmed by the user.")
    def finalize_order():
        if current_order.is_complete():
            filename = current_order.save_to_json()
            return f"Order placed successfully! Saved to {filename}. Thank you for visiting NeuroBrew."
        else:
            return "The order is missing details. Please ask the user for the missing fields."

    # 4. Initialize the Voice Agent
    # Note: Ensure you have OPENAI_API_KEY in your environment variables
    agent = VoicePipelineAgent(
        vad=silero.VAD.load(),
        stt=deepgram.STT(), # Or openai.STT()
        llm=openai.LLM(),
        tts=openai.TTS(), # Or use Murf Falcon if you have the plugin
        chat_ctx=initial_ctx,
        fnc_ctx=llm.FunctionContext(
            # Register the functions we defined above
            [update_order, finalize_order]
        ),
    )

    agent.start(ctx.room)

    await agent.say("Hi there! Welcome to NeuroBrew. What can I get started for you today?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))