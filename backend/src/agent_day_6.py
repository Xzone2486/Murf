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

DB_FILE = "fraud_cases.db"

class FraudDB:
    def __init__(self, db_path):
        self.db_path = db_path

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

    def update_case_status(self, case_id, status, note):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("UPDATE fraud_cases SET case_status = ?, outcome_note = ? WHERE id = ?", (status, note, case_id))
        conn.commit()
        conn.close()

db = FraudDB(DB_FILE)

@function_tool
def get_fraud_case(username: Annotated[str, "The username of the customer"]) -> str:
    """Retrieve the fraud case details for a given username."""
    logger.info(f"Looking up case for user: {username}")
    case = db.get_case_by_username(username)
    if case:
        return f"Found case: {case}"
    return "No case found for that username."

@function_tool
def update_case_status(
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
                "Your goal is to verify a suspicious transaction with the customer. "
                "You must be professional, calm, and reassuring. "
                "Do NOT ask for real PII (passwords, full card numbers, PINs). "
                "You have access to a database of fraud cases. "
                "Start by asking for the customer's username to look up their file. "
                "Once you have the username, use the `get_fraud_case` tool to retrieve details. "
                "Then, verify the user by asking their security question (found in the case details). "
                "If they answer correctly, read the transaction details (Merchant, Amount, Date) and ask if they made it. "
                "If they say YES: Mark case as 'confirmed_safe' using `update_case_status`. "
                "If they say NO: Mark case as 'confirmed_fraud' using `update_case_status` and explain that the card is blocked. "
                "If verification fails: End the call politely. "
                "Always be concise."
            ),
            tools=[get_fraud_case, update_case_status]
        )

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")

    tts = murf.TTS(voice="en-US-matthew", style="Conversational", speed=1.0)

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
        await session.say("Hello, this is the Fraud Department at Murf Bank. I'm calling about some suspicious activity on your account. Could you please confirm your username so I can pull up your file?", allow_interruptions=True)

    # Greet immediately
    asyncio.create_task(greet())

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
