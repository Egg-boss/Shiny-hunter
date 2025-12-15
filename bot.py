import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta
import sqlite3

# -------- KEEP ALIVE (RENDER) --------
from flask import Flask
import threading

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
# ------------------------------------

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in the environment variables.")

POKETWO_ID = 716390085896962058

# Intents setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

lock_duration = 12

KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

blacklisted_channels = set()
lock_timers = {}

# -------- DATABASE --------
def get_db_connection():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute("CREATE TABLE IF NOT EXISTS blacklisted_channels (id INTEGER PRIMARY KEY, channel_id INTEGER UNIQUE)")
    conn.close()

def add_to_blacklist_db(channel_id):
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO blacklisted_channels (channel_id) VALUES (?)", (channel_id,))
    conn.commit()
    conn.close()

def remove_from_blacklist_db(channel_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM blacklisted_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def load_blacklisted_channels():
    conn = get_db_connection()
    rows = conn.execute("SELECT channel_id FROM blacklisted_channels").fetchall()
    conn.close()
    return {row["channel_id"] for row in rows}

init_db()

# -------- UNLOCK VIEW --------
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        unlock_role = discord.utils.get(interaction.guild.roles, name="unlock")
        if unlock_role and unlock_role in interaction.user.roles:
            await unlock_channel(self.channel, interaction.user)
            await interaction.response.send_message("Channel unlocked!", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message(
                "You don't have the 'unlock' role to unlock this channel. Use `.unlock` instead.",
                ephemeral=True
            )

# -------- EVENTS --------
@bot.event
async def on_ready():
    global blacklisted_channels
    blacklisted_channels = load_blacklisted_channels()
    logging.info(f"Bot online as {bot.user}")

    if not check_lock_timers.is_running():
        check_lock_timers.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.author.id == POKETWO_ID:
        if "These colors seem unusual... ✨" in message.content:
            embed = discord.Embed(
                title="🎉 Congratulations! 🎉",
                description=f"{message.author.mention} has found a shiny Pokémon!",
                color=discord.Color.gold()
            )
            embed.set_footer(text="Keep hunting for more rare Pokémon!")
            await message.channel.send(embed=embed)

    if message.author.bot and message.content:
        active_keywords = [k for k, v in KEYWORDS.items() if v]
        if any(keyword in message.content.lower() for keyword in active_keywords):
            if message.channel.id not in blacklisted_channels:
                await lock_channel(message.channel)
                embed = discord.Embed(
                    title="🔒 Channel Locked",
                    description=f"This channel has been locked for {lock_duration} hours.",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                embed.add_field(
                    name="Unlocks At",
                    value=(datetime.now() + timedelta(hours=lock_duration)).strftime("%Y-%m-%d %H:%M:%S"),
                    inline=False
                )
                embed.set_footer(text="Use the unlock button or `.unlock`.")
                await message.channel.send(embed=embed, view=UnlockView(message.channel))

    await bot.process_commands(message)

# -------- LOCK SYSTEM --------
async def set_channel_permissions(channel, view_channel=None, send_messages=None):
    guild = channel.guild
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        return

    overwrite = channel.overwrites_for(poketwo)
    overwrite.view_channel = view_channel if view_channel is not None else True
    overwrite.send_messages = send_messages if send_messages is not None else True
    await channel.set_permissions(poketwo, overwrite=overwrite)

async def lock_channel(channel):
    await set_channel_permissions(channel, False, False)
    lock_timers[channel.id] = datetime.now() + timedelta(hours=lock_duration)

async def unlock_channel(channel, user):
    await set_channel_permissions(channel, None, None)
    lock_timers.pop(channel.id, None)
    embed = discord.Embed(
        title="🔓 Channel Unlocked",
        description=f"Unlocked by {user.mention}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    await channel.send(embed=embed)

@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()
    for channel_id, end in list(lock_timers.items()):
        if now >= end:
            channel = bot.get_channel(channel_id)
            if channel:
                await unlock_channel(channel, bot.user)
            lock_timers.pop(channel_id, None)

# -------- COMMANDS --------
@bot.group(invoke_without_command=True)
async def blacklist(ctx):
    await ctx.send("Use `.blacklist add`, `.blacklist remove`, or `.blacklist list`.")

@blacklist.command()
@commands.has_permissions(manage_channels=True)
async def add(ctx, channel: discord.TextChannel):
    blacklisted_channels.add(channel.id)
    add_to_blacklist_db(channel.id)
    await ctx.send(f"{channel.mention} blacklisted.")

@blacklist.command()
@commands.has_permissions(manage_channels=True)
async def remove(ctx, channel: discord.TextChannel):
    blacklisted_channels.discard(channel.id)
    remove_from_blacklist_db(channel.id)
    await ctx.send(f"{channel.mention} removed from blacklist.")

@blacklist.command()
async def list(ctx):
    if not blacklisted_channels:
        await ctx.send("No blacklisted channels.")
        return
    msg = "\n".join(bot.get_channel(cid).mention for cid in blacklisted_channels if bot.get_channel(cid))
    await ctx.send(msg)

@bot.command()
async def check_timer(ctx):
    if ctx.channel.id in lock_timers:
        remaining = lock_timers[ctx.channel.id] - datetime.now()
        mins = int(remaining.total_seconds() // 60)
        await ctx.send(f"Unlocks in {mins} minutes.")
    else:
        await ctx.send("Channel not locked.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await lock_channel(ctx.channel)
    await ctx.send("🔒 Channel locked.", view=UnlockView(ctx.channel))

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await unlock_channel(ctx.channel, ctx.author)

@bot.command()
async def owner(ctx):
    await ctx.send("Made by 💨 Suk Ballz")

# -------- START --------
keep_alive()
bot.run(BOT_TOKEN)
