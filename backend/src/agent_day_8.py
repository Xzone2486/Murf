import logging
import time
from typing import Annotated

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    function_tool,
    RunContext,
)
from livekit.plugins import deepgram, google, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")

logger = logging.getLogger("game-master-agent")
logger.setLevel(logging.INFO)

class GameMasterAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=(
                "You are a friendly Storyteller running a simple, interactive adventure. "
                "Your goal is to guide the player through an easy-to-follow story. "
                "Keep the language simple, clear, and engaging (standard English). "
                "Scenario: The player has just found a mysterious old map in their attic. "
                "Rule 1: Describe the scene simply (2-3 sentences). "
                "Rule 2: ALWAYS end your turn by asking 'What do you do?'. "
                "Rule 3: Maintain continuity. "
                "Rule 4: If the player asks to restart, use the 'restart_story' tool."
            )
        )

    @function_tool
    async def restart_story(self, context: RunContext):
        """Restart the story from the beginning."""
        logger.info("Restarting story")
        return "The page turns... A new story begins. (Please start a new scene)."

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    
    session = AgentSession(
        stt=deepgram.STT(model="nova-2"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=deepgram.TTS(),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
    )

    agent = GameMasterAgent()

    await session.start(agent=agent, room=ctx.room)
    await ctx.connect(auto_subscribe=True)

    # Initial greeting to kick off the story
    await session.say("Hello! You're cleaning out your dusty attic when you stumble upon an old, weathered map tucked inside a book. It looks like it leads to somewhere nearby. What do you do?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
