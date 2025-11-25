import logging
import json
import os
import asyncio
from typing import Annotated, List, Literal
from dataclasses import dataclass, field

from dotenv import load_dotenv
from pydantic import Field

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
    llm,
    function_tool,
    RunContext,
)

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("tutor-agent")
load_dotenv(".env.local")

# ======================================================
# CONTENT LOADING
# ======================================================
CONTENT_FILE = "../day4_tutor_content.json"

def load_content():
    try:
        # Adjust path if running from src or backend
        path = CONTENT_FILE
        if not os.path.exists(path):
            path = "backend/day4_tutor_content.json"
        if not os.path.exists(path):
             path = "day4_tutor_content.json"
        
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Could not load content: {e}")
        return []

CONCEPTS = load_content()

# ======================================================
# SHARED STATE
# ======================================================
@dataclass
class TutorState:
    current_concept_index: int = 0
    mode: Literal["selection", "learn", "quiz", "teach_back"] = "selection"
    session: AgentSession | None = None
    agent: Agent | None = None

    @property
    def current_concept(self):
        if 0 <= self.current_concept_index < len(CONCEPTS):
            return CONCEPTS[self.current_concept_index]
        return None

# ======================================================
# HELPER FUNCTIONS
# ======================================================
def update_persona(state: TutorState):
    if not state.session or not state.agent:
        return

    concept = state.current_concept
    mode = state.mode
    
    if mode == "selection":
        topic_list = ", ".join([c['title'] for c in CONCEPTS])
        instructions = f"You are a helpful tutor. List the available topics: {topic_list}. Ask the user which one they want to learn about."
        state.session.tts.voice = "en-US-matthew"

    elif mode == "learn":
        instructions = f"""
            You are Matthew, a helpful tutor.
            Explain the concept: {concept['title']}.
            Summary: {concept['summary']}.
            If user wants to quiz or teach back, call the switch tools.
        """
        state.session.tts.voice = "en-US-matthew"
        
    elif mode == "quiz":
        instructions = f"""
            You are Alicia, a quiz master.
            Ask about: {concept['title']}.
            Question: {concept['sample_question']}.
            Evaluate answer.
            If user wants to learn or teach back, call the switch tools.
        """
        state.session.tts.voice = "en-US-alicia"
        
    elif mode == "teach_back":
        instructions = f"""
            You are Ken, a curious student.
            Ask user to explain: {concept['title']}.
            Listen and give feedback based on: {concept['summary']}.
            If user wants to learn or quiz, call the switch tools.
        """
        state.session.tts.voice = "en-US-ken"

    # Update agent instructions
    # Since we can't set instructions directly on base Agent easily if it's read-only,
    # we rely on the fact that we are using a custom agent class or just updating the property we defined.
    # But here we are moving tools outside.
    # Let's assume state.agent is our TutorAgent which has the setter.
    state.agent.instructions = instructions

# ======================================================
# FUNCTION TOOLS
# ======================================================

@function_tool
async def switch_mode(
    ctx: RunContext[TutorState], 
    mode: Annotated[Literal["learn", "quiz", "teach_back"], Field(description="Mode to switch to")]
) -> str:
    ctx.userdata.mode = mode
    update_persona(ctx.userdata)
    return f"Switching to {mode} mode."

@function_tool
async def next_concept(ctx: RunContext[TutorState]) -> str:
    ctx.userdata.current_concept_index = (ctx.userdata.current_concept_index + 1) % len(CONCEPTS)
    update_persona(ctx.userdata)
    return f"Moving to next concept: {ctx.userdata.current_concept['title']}"

@function_tool
async def select_topic(
    ctx: RunContext[TutorState],
    topic_name: Annotated[str, Field(description="The name of the topic to select (e.g. Variables, Loops)")]
) -> str:
    # Find topic index
    found_index = -1
    for i, concept in enumerate(CONCEPTS):
        if concept['title'].lower() in topic_name.lower():
            found_index = i
            break
    
    if found_index == -1:
        return "Topic not found. Please ask the user to choose from the available topics."

    ctx.userdata.current_concept_index = found_index
    ctx.userdata.mode = "learn" # Default to learn mode after selection
    update_persona(ctx.userdata)
    return f"Selected topic: {CONCEPTS[found_index]['title']}. Switching to Learn mode."

# ======================================================
# AGENT DEFINITION
# ======================================================

class TutorAgent(Agent):
    def __init__(self):
        self._instructions = ""
        super().__init__(instructions="", tools=[switch_mode, next_concept, select_topic])

    @property
    def instructions(self):
        return self._instructions

    @instructions.setter
    def instructions(self, value):
        self._instructions = value

# ======================================================
# ENTRYPOINT
# ======================================================
async def entrypoint(ctx: JobContext):
    print("\nSTARTING DAY 4 TUTOR AGENT")
    
    state = TutorState()
    
    # We need to initialize TTS with a default, but it will be updated.
    tts = murf.TTS(voice="en-US-matthew", style="Conversational", speed=1.0)
    
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=tts,
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        userdata=state,
    )

    # Create agent instance
    agent = TutorAgent()
    
    # Link state to session and agent
    state.session = session
    state.agent = agent
    
    # Initial persona update
    update_persona(state)

    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    )

    await ctx.connect(auto_subscribe=True)

    await asyncio.sleep(1)
    await session.say(f"Hello! I am your active recall coach. Please choose a topic to start: {', '.join([c['title'] for c in CONCEPTS])}.", allow_interruptions=True)

# ======================================================
# PREWARM & LAUNCH
# ======================================================
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
