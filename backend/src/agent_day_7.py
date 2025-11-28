import json
import logging
import time
import os
from typing import Annotated, List, Dict, Optional

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

# Configure logging
logger = logging.getLogger("grocery-agent")
logger.setLevel(logging.INFO)

# Load Catalog
CATALOG_PATH = "grocery_catalog.json"
try:
    # Try to find the catalog file
    if not os.path.exists(CATALOG_PATH):
        # Try looking in backend dir if running from root
        alt_path = os.path.join("backend", CATALOG_PATH)
        if os.path.exists(alt_path):
            CATALOG_PATH = alt_path
        
    with open(CATALOG_PATH, "r") as f:
        CATALOG_DATA = json.load(f)
        PRODUCTS = {p["id"]: p for p in CATALOG_DATA["products"]}
        # Create a name to ID mapping for easier lookup
        PRODUCT_NAME_MAP = {p["name"].lower(): p["id"] for p in CATALOG_DATA["products"]}
        RECIPES = CATALOG_DATA.get("recipes", {})
    logger.info(f"Loaded catalog from {CATALOG_PATH}")
except Exception as e:
    logger.error(f"Failed to load catalog: {e}")
    PRODUCTS = {}
    PRODUCT_NAME_MAP = {}
    RECIPES = {}

class Cart:
    def __init__(self):
        self.items: Dict[str, int] = {} # product_id -> quantity

    def add(self, product_id: str, quantity: int = 1):
        if product_id in self.items:
            self.items[product_id] += quantity
        else:
            self.items[product_id] = quantity

    def remove(self, product_id: str):
        if product_id in self.items:
            del self.items[product_id]

    def update(self, product_id: str, quantity: int):
        if quantity <= 0:
            self.remove(product_id)
        else:
            self.items[product_id] = quantity

    def clear(self):
        self.items = {}

    def get_summary(self) -> str:
        if not self.items:
            return "Your cart is empty."
        
        summary_lines = []
        total_price = 0.0
        
        for pid, qty in self.items.items():
            product = PRODUCTS.get(pid)
            if product:
                line_total = product["price"] * qty
                total_price += line_total
                summary_lines.append(f"- {qty} {product['unit']}(s) of {product['name']} (${line_total:.2f})")
        
        summary_lines.append(f"Total: ${total_price:.2f}")
        return "\n".join(summary_lines)

    def to_dict(self):
        return {
            "items": [
                {
                    "product_id": pid,
                    "name": PRODUCTS[pid]["name"],
                    "quantity": qty,
                    "price": PRODUCTS[pid]["price"],
                    "total": PRODUCTS[pid]["price"] * qty
                }
                for pid, qty in self.items.items() if pid in PRODUCTS
            ],
            "total": sum(PRODUCTS[pid]["price"] * qty for pid, qty in self.items.items() if pid in PRODUCTS)
        }

class GroceryAgent(Agent):
    def __init__(self):
        self.cart = Cart()
        super().__init__(
            instructions=(
                "You are a friendly and helpful grocery shopping assistant for 'FreshMart'. "
                "You can help users browse the catalog, add items to their cart, and place orders. "
                "You can also help with ingredients for simple meals like sandwiches or pasta. "
                "Always confirm actions like adding items or placing orders. "
                "When the user asks for 'ingredients for X', check if you have a recipe for it. "
                "If the user says they are done or wants to place the order, use the place_order tool. "
                "Keep your responses concise and natural for voice interaction."
            )
        )

    @function_tool
    async def add_to_cart(
        self,
        context: RunContext,
        item_name: Annotated[str, "The name of the item to add"],
        quantity: Annotated[int, "The quantity to add"] = 1,
    ):
        """Add an item to the cart."""
        logger.info(f"Adding to cart: {item_name}, qty: {quantity}")
        item_key = item_name.lower()
        product_id = PRODUCT_NAME_MAP.get(item_key)
        
        if not product_id:
            for name, pid in PRODUCT_NAME_MAP.items():
                if item_key in name:
                    product_id = pid
                    break
        
        if product_id:
            self.cart.add(product_id, quantity)
            product_name = PRODUCTS[product_id]["name"]
            return f"Added {quantity} {PRODUCTS[product_id]['unit']}(s) of {product_name} to your cart."
        else:
            return f"Sorry, I couldn't find {item_name} in the catalog."

    @function_tool
    async def remove_from_cart(
        self,
        context: RunContext,
        item_name: Annotated[str, "The name of the item to remove"]
    ):
        """Remove an item from the cart."""
        logger.info(f"Removing from cart: {item_name}")
        item_key = item_name.lower()
        product_id = PRODUCT_NAME_MAP.get(item_key)
        
        if not product_id:
             for name, pid in PRODUCT_NAME_MAP.items():
                if item_key in name:
                    product_id = pid
                    break
        
        if product_id:
            if product_id in self.cart.items:
                self.cart.remove(product_id)
                return f"Removed {PRODUCTS[product_id]['name']} from your cart."
            else:
                return f"{PRODUCTS[product_id]['name']} is not in your cart."
        else:
            return f"Sorry, I couldn't find {item_name} to remove."

    @function_tool
    async def update_quantity(
        self,
        context: RunContext,
        item_name: Annotated[str, "The name of the item to update"],
        quantity: Annotated[int, "The new quantity"]
    ):
        """Update the quantity of an item in the cart."""
        logger.info(f"Updating quantity: {item_name} to {quantity}")
        item_key = item_name.lower()
        product_id = PRODUCT_NAME_MAP.get(item_key)
        
        if not product_id:
             for name, pid in PRODUCT_NAME_MAP.items():
                if item_key in name:
                    product_id = pid
                    break

        if product_id:
            self.cart.update(product_id, quantity)
            return f"Updated {PRODUCTS[product_id]['name']} quantity to {quantity}."
        else:
            return f"Sorry, I couldn't find {item_name}."

    @function_tool
    async def get_cart_contents(self, context: RunContext):
        """Get the current contents of the cart."""
        logger.info("Getting cart contents")
        return self.cart.get_summary()

    @function_tool
    async def add_ingredients_for_recipe(
        self,
        context: RunContext,
        recipe_name: Annotated[str, "The name of the recipe or meal (e.g. 'peanut butter sandwich', 'pasta')"]
    ):
        """Add ingredients for a specific recipe or meal."""
        logger.info(f"Adding ingredients for recipe: {recipe_name}")
        recipe_key = recipe_name.lower()
        
        ingredients = RECIPES.get(recipe_key)
        
        if not ingredients:
            for name, items in RECIPES.items():
                if recipe_key in name:
                    ingredients = items
                    break
        
        if ingredients:
            added_items = []
            for pid in ingredients:
                self.cart.add(pid, 1)
                added_items.append(PRODUCTS[pid]["name"])
            return f"Added ingredients for {recipe_name}: {', '.join(added_items)}."
        else:
            return f"Sorry, I don't have a recipe for {recipe_name}."

    @function_tool
    async def place_order(self, context: RunContext):
        """Place the order and save it."""
        logger.info("Placing order")
        if not self.cart.items:
            return "Your cart is empty. Please add items before placing an order."
        
        order_data = {
            "timestamp": time.time(),
            "order_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "cart": self.cart.to_dict(),
            "status": "placed"
        }
        
        filename = f"order_{int(time.time())}.json"
        try:
            with open(filename, "w") as f:
                json.dump(order_data, f, indent=2)
            
            summary = self.cart.get_summary()
            self.cart.clear() 
            return f"Order placed successfully! Saved to {filename}. \nOrder Summary:\n{summary}"
        except Exception as e:
            logger.error(f"Failed to save order: {e}")
            return "Sorry, there was an error placing your order."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    
    # Initialize AgentSession with plugins
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=deepgram.TTS(),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
    )

    agent = GroceryAgent()

    await session.start(agent=agent, room=ctx.room)
    await ctx.connect(auto_subscribe=True)

    # Initial greeting
    await session.say("Hi there! Welcome to FreshMart. I can help you order groceries or ingredients for meals. What would you like to get today?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )
