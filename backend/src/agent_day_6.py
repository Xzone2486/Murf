import os
import logging
import sqlite3
import asyncio
from typing import Annotated

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    function_tool,
)
from livekit.plugins import deepgram, google, murf, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")

# Configure logging
logger = logging.getLogger("fraud-agent")
logger.setLevel(logging.INFO)

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fraud_cases.db")

class FraudDB:
    def __init__(self, db_path):
        self.db_path = db_path
        print(f"DEBUG: Initializing FraudDB with path: {self.db_path}")
        if os.path.exists(self.db_path):
            print("DEBUG: DB file exists.")
        else:
            print("DEBUG: DB FILE DOES NOT EXIST AT THIS PATH!")

    def get_case_by_username(self, username):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fraud_cases WHERE userName = ? COLLATE NOCASE", (username,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "userName": row[1],
                "securityIdentifier": row[2],
                "cardEnding": row[3],
                "case_status": row[4],
                "transactionName": row[5],
                "transactionTime": row[6],
                "transactionCategory": row[7],
                "transactionSource": row[8],
                "transactionAmount": row[9],
                "securityQuestion": row[10],
                "securityAnswer": row[11],
                "outcome_note": row[12]
            }
        return None

    def get_active_case(self):
        try:
            print(f"DEBUG: Attempting to connect to {self.db_path}")
            if not os.path.exists(self.db_path):
                return None, f"DB file not found at {self.db_path}"
                
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM fraud_cases ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row:
                print(f"DEBUG: Found case: {row}")
                return {
                    "id": row[0],
                    "userName": row[1],
                    "securityIdentifier": row[2],
                    "cardEnding": row[3],
                    "case_status": row[4],
                    "transactionName": row[5],
                    "transactionTime": row[6],
                    "transactionCategory": row[7],
                    "transactionSource": row[8],
                    "transactionAmount": row[9],
                    "securityQuestion": row[10],
                    "securityAnswer": row[11],
                    "outcome_note": row[12]
                }, None
            print("DEBUG: No rows found in fraud_cases table.")
            return None, "No rows found in table"
        except Exception as e:
            print(f"DEBUG: Error in get_active_case: {e}")
            return None, str(e)

    def update_case_status(self, case_id, status, note):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE fraud_cases SET case_status = ?, outcome_note = ? WHERE id = ?", (status, note, case_id))
        conn.commit()
        conn.close()

db = FraudDB(DB_FILE)

@function_tool
async def get_active_fraud_case() -> str:
    """Retrieve the most recent fraud case to investigate."""
    print("DEBUG: get_active_fraud_case TOOL CALLED!")
    case, error = db.get_active_case()
    if case:
        return f"Found active case: {case}"
    return f"Error retrieving case: {error}. Path used: {db.db_path}"

@function_tool
async def update_case_status(
    case_id: Annotated[int, "The ID of the fraud case"],
    status: Annotated[str, "The new status: 'confirmed_safe' or 'confirmed_fraud'"],
    note: Annotated[str, "A short note about the outcome"]
) -> str:
    """Update the status of the fraud case in the database."""
    logger.info(f"Updating case {case_id} to {status}: {note}")
    db.update_case_status(case_id, status, note)
    return "Case updated successfully."

class FraudAgent(Agent):
    def __init__(self):
        super().__init__(
            instructions=(
                "You are a fraud detection representative for Murf Bank. "
                "Your PRIORITY is to retrieve the case details immediately. "
                "1. Call `get_active_fraud_case` NOW to get the customer's name and transaction. "
                "2. Once you have the case, ask: 'Am I speaking with {userName}?' "
                "3. If confirmed, ask the security question. "
                "4. Then read the transaction details and ask if they made it. "
                "Do not make up data. If the tool fails, say 'System Error'. "
            ),
            tools=[get_active_fraud_case, update_case_status]
        )

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")

    # tts = murf.TTS(voice="en-US-matthew", style="Conversational", speed=1.0)
    # tts = google.TTS()
    tts = deepgram.TTS()

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=tts,
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
    )

    agent = FraudAgent()

    await session.start(agent=agent, room=ctx.room)
    await ctx.connect(auto_subscribe=True)

    async def greet():
        await asyncio.sleep(1)
        await session.say("Hello, this is the Fraud Department at Murf Bank. I'm calling about some suspicious activity on your account.", allow_interruptions=True)

    # Greet immediately
    asyncio.create_task(greet())

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
