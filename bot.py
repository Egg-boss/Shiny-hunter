import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
POKETWO_ID = 716390085896962058  # Pokétwo's default ID

# Optional: Replace with a role ID for pings (or set to None to disable pings)
PING_ROLE_ID = None  # Replace with your role ID or None

# Phrases that trigger the lock (case-insensitive)
SHINY_HUNT_PHRASES = ["shiny hunt pings", "rare ping"]

# Intents setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")


@bot.event
async def on_message(message):
    """Detect Shiny hunt pings or rare ping and lock the channel."""
    if message.author.id == POKETWO_ID and any(phrase in message.content.lower() for phrase in SHINY_HUNT_PHRASES):
        # Send ping message if configured
        await send_custom_ping(message.channel)

        # Lock the channel
        await lock_channel(message.channel)

        # Send unlock button
        await send_unlock_button(message.channel)
    await bot.process_commands(message)


async def send_custom_ping(channel):
    """Send a ping message to a specific role or users."""
    if PING_ROLE_ID:
        role = channel.guild.get_role(PING_ROLE_ID)
        if role:
            await channel.send(f"{role.mention} A shiny or rare hunt has appeared! React quickly!")
        else:
            print("Ping role not found.")
    else:
        await channel.send("A shiny or rare hunt has appeared! React quickly!")


async def lock_channel(channel):
    """Locks the channel by denying permissions for Pokétwo."""
    guild = channel.guild
    poketwo = guild.get_member(POKETWO_ID)

    if poketwo:
        # Modify channel permissions for Pokétwo
        overwrite = channel.overwrites_for(poketwo)
        overwrite.view_channel = False
        overwrite.send_messages = False
        await channel.set_permissions(poketwo, overwrite=overwrite)
        print(f"Locked channel: {channel.name}")
        await channel.send(f"The channel has been locked to prevent Pokétwo from accessing it.")
    else:
        print("Pokétwo bot not found in this server.")


async def send_unlock_button(channel):
    """Sends an unlock button in the channel."""
    cl
