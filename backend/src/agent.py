import logging
import json
from typing import Annotated, List

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    tokenize,
    function_tool,
    RunContext
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# --- 1. Define the Order State Helper ---
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
        # Check if required fields are filled
        return all(self.data[k] is not None for k in ["drinkType", "size", "milk", "name"])

    def save_to_json(self):
        # Create a safe filename
        safe_name = "".join(x for x in self.data['name'] if x.isalnum())
        filename = f"order_{safe_name}.json"
        
        with open(filename, "w") as f:
            json.dump(self.data, f, indent=2)
        logger.info(f"Order saved to {filename}")
        return filename

# --- 2. Define the Agent Class ---
class Assistant(Agent):
    def __init__(self) -> None:
        # Initialize the order state for this specific session
        self.order_state = OrderState()
        
        super().__init__(
            instructions="""You are a friendly, energetic barista at 'NeuroBrew Coffee'. 
            Your goal is to take a complete coffee order. 
            You must fill in the following fields: Drink Type, Size, Milk preference, Extras (optional), and Customer Name. 
            
            Do not make up information. If a user hasn't specified something (like size or milk), ask them clarifying questions. 
            Once you have all the details, confirm the order with the user. 
            When the order is confirmed and complete, call the 'finalize_order' function.""",
        )

    # --- 3. Add the Tools ---
    
    @function_tool
    async def update_order(
        self, 
        ctx: RunContext, 
        drink_type: Annotated[str, "The type of drink (e.g., Latte, Cappuccino)"] = None,
        size: Annotated[str, "Size of the drink (Small, Medium, Large)"] = None,
        milk: Annotated[str, "Type of milk (Whole, Oat, Almond, Soy, None)"] = None,
        extra: Annotated[str, "Add an extra item (e.g., Sugar, Whipped Cream)"] = None,
        name: Annotated[str, "Customer's name"] = None,
    ):
        """
        Update the current order with details provided by the customer. 
        Call this whenever the user provides new information about their drink.
        """
        if drink_type: self.order_state.data["drinkType"] = drink_type
        if size: self.order_state.data["size"] = size
        if milk: self.order_state.data["milk"] = milk
        if name: self.order_state.data["name"] = name
        if extra: self.order_state.data["extras"].append(extra)
        
        logger.info(f"Updated State: {self.order_state.data}")
        return f"Order updated. Current state: {self.order_state.data}"

    @function_tool
    async def finalize_order(self, ctx: RunContext):
        """
        Call this ONLY when the order is complete and confirmed by the user.
        """
        if self.order_state.is_complete():
            filename = self.order_state.save_to_json()
            return f"Order placed successfully! Saved to {filename}. Thank you for visiting NeuroBrew."
        else:
            return "The order is missing details. Please ask the user for the missing fields."

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    # Logging setup
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    session = AgentSession(
        # STT: Deepgram Nova-3
        stt=deepgram.STT(model="nova-3"),
        
        # LLM: Google Gemini
        llm=google.LLM(
            model="gemini-2.5-flash",
        ),
        
        # TTS: Murf
        tts=murf.TTS(
            voice="en-US-matthew", 
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True
        ),
        
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # Start the session
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))