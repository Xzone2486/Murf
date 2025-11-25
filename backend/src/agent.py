import logging
import asyncio
from dotenv import load_dotenv

from livekit.agents import (
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    tokenize,
    function_tool,
    RunContext,
    RoomInputOptions,
)
from livekit.agents import llm as lk_llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")
logger = logging.getLogger("tutor-coach")

# --- 1. EMBEDDED CONTENT ---
COURSE_CONTENT = [
    {
        "id": "variables",
        "title": "Variables",
        "summary": "A variable is a labeled box for storing data. In Python, you assign values like 'x = 5'. This lets you reuse data without typing it again.",
        "question": "In your own words, why do we use variables?"
    },
    {
        "id": "loops",
        "title": "Loops",
        "summary": "Loops repeat actions. A 'For Loop' runs through a list. A 'While Loop' runs as long as a condition is true.",
        "question": "What is the difference between a For loop and a While loop?"
    }
]

# Voice IDs (Murf Falcon)
VOICE_LEARN = "en-US-matthew"
VOICE_QUIZ = "en-US-alicia"
VOICE_TEACH = "en-US-ken"

def get_topic_summary():
    topics = [f"- {item['id']}: {item['title']}" for item in COURSE_CONTENT]
    return "\n".join(topics)

# --- 2. THE TOOLS (Context Class) ---
class TutorTools(lk_llm.FunctionContext):
    def __init__(self, tts_plugin):
        super().__init__()
        self.tts = tts_plugin # Store reference to TTS so we can change it

    @function_tool
    async def switch_learning_mode(
        self, 
        context: RunContext, 
        mode: str, 
        topic_id: str
    ) -> str:
        """
        Switch the learning mode and voice.
        Args:
            mode: Must be 'learn', 'quiz', or 'teach_back'.
            topic_id: The id of the topic (e.g., 'variables', 'loops').
        """
        logger.info(f"🔄 Requesting switch to mode: {mode} for topic: {topic_id}")

        # Find topic
        topic_data = next((item for item in COURSE_CONTENT if item["id"] == topic_id), None)
        if not topic_data:
            return "Topic not found. Ask user to pick 'variables' or 'loops'."

        # Update Voice and Instructions
        system_update = ""
        voice_name = "Unknown"

        if mode == "learn":
            self.tts.voice = VOICE_LEARN
            voice_name = "Matthew (Teacher)"
            system_update = (
                f"ROLE: Professor Matthew. "
                f"TASK: Explain '{topic_data['title']}' using this summary: '{topic_data['summary']}'. "
                f"Keep it clear and simple."
            )
            
        elif mode == "quiz":
            self.tts.voice = VOICE_QUIZ
            voice_name = "Alicia (Examiner)"
            system_update = (
                f"ROLE: Examiner Alicia. "
                f"TASK: Ask this question: '{topic_data['question']}'. Wait for answer. Grade it."
            )

        elif mode == "teach_back":
            self.tts.voice = VOICE_TEACH
            voice_name = "Ken (Student)"
            system_update = (
                f"ROLE: Student Ken. "
                f"TASK: Say 'I don't understand {topic_data['title']}. Can you explain it?' "
                f"If they miss details from: '{topic_data['summary']}', ask follow-up questions."
            )

        logger.info(f"✅ Switched Voice to: {voice_name}")
        
        # Return instruction to the LLM
        return (
            f"SYSTEM_UPDATE: Voice successfully changed to {voice_name}. "
            f"NEW INSTRUCTIONS: {system_update} "
            f"ACTION: Start speaking immediately in your new persona."
        )

# --- 3. STARTUP ---
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    
    # 1. Setup Instructions
    topics_text = get_topic_summary()
    instructions = f"""
    You are an Active Recall Coach.
    AVAILABLE TOPICS:
    {topics_text}

    MODES:
    1. Learn (Professor Matthew explains)
    2. Quiz (Examiner Alicia tests)
    3. Teach-Back (Student Ken asks you to explain)

    GOAL: Greet user. Ask for Topic AND Mode.
    Once chosen, CALL 'switch_learning_mode' IMMEDIATELY.
    """

    # 2. Chat Context (The fixed way)
    chat_ctx = lk_llm.ChatContext()
    chat_ctx.append(text=instructions, role="system")

    # 3. Configure TTS
    murf_tts = murf.TTS(
        voice=VOICE_LEARN, 
        style="Conversation",
        tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
        text_pacing=True
    )

    # 4. Build Pipeline
    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata.get("vad") or silero.VAD.load(),
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-1.5-flash-002"),
        tts=murf_tts,
        noise_cancellation=noise_cancellation.BVC(),
        turn_detector=MultilingualModel(),
        chat_ctx=chat_ctx,
        fnc_ctx=TutorTools(tts_plugin=murf_tts), # Pass TTS to tools
        preemptive_synthesis=True,
    )
    
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    agent.start(ctx.room, participant=participant)
    
    # 5. Greeting
    await agent.say("Hello! I am your Tutor. We can study Variables or Loops. Do you want to Learn, Quiz, or Teach-Back?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))