import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta
import sqlite3
from flask import Flask
import threading

# ---------------- KEEP ALIVE (RENDER) ----------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive"

def keep_alive():
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=8080),
        daemon=True
    ).start()

keep_alive()

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO)

# ---------------- ENV ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

POKETWO_ID = 716390085896962058

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ---------------- SETTINGS ----------------
lock_duration = 12  # hours

KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

blacklisted_channels = set()
blacklisted_categories = set()

# IMPORTANT: MUST BE A NORMAL DICT
lock_timers: dict[int, datetime] = {}

# ---------------- DATABASE ----------------
def db():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db()
    c.execute("CREATE TABLE IF NOT EXISTS blacklisted_channels (channel_id INTEGER PRIMARY KEY)")
    c.execute("CREATE TABLE IF NOT EXISTS blacklisted_categories (category_id INTEGER PRIMARY KEY)")
    c.commit()
    c.close()

def load_blacklists():
    c = db()
    ch = {r["channel_id"] for r in c.execute("SELECT channel_id FROM blacklisted_channels")}
    cat = {r["category_id"] for r in c.execute("SELECT category_id FROM blacklisted_categories")}
    c.close()
    return ch, cat

def add_category(cid):
    c = db()
    c.execute("INSERT OR IGNORE INTO blacklisted_categories VALUES (?)", (cid,))
    c.commit()
    c.close()

def remove_category(cid):
    c = db()
    c.execute("DELETE FROM blacklisted_categories WHERE category_id=?", (cid,))
    c.commit()
    c.close()

init_db()

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    global blacklisted_channels, blacklisted_categories
    blacklisted_channels, blacklisted_categories = load_blacklists()
    if not unlock_task.is_running():
        unlock_task.start()
    logging.info(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Pokétwo shiny message
    if message.author.bot and message.author.id == POKETWO_ID:
        if "These colors seem unusual" in message.content:
            embed = discord.Embed(
                title="✨ SHINY FOUND ✨",
                description="Pokétwo detected a shiny Pokémon!",
                color=discord.Color.gold()
            )
            await message.channel.send(embed=embed)

    # Auto lock logic
    if message.author.bot and message.content:
        if message.channel.id not in blacklisted_channels:
            cat = message.channel.category
            if not cat or cat.id not in blacklisted_categories:
                text = message.content.lower()
                if any(k in text for k, v in KEYWORDS.items() if v):
                    await lock_channel(message.channel)

    await bot.process_commands(message)

# ---------------- LOCKING ----------------
async def set_perm(channel, view=None, send=None):
    try:
        poketwo = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return
    ow = channel.overwrites_for(poketwo)
    if view is not None:
        ow.view_channel = view
    if send is not None:
        ow.send_messages = send
    await channel.set_permissions(poketwo, overwrite=ow)

async def lock_channel(channel):
    if channel.id in lock_timers:
        return
    await set_perm(channel, False, False)
    lock_timers[channel.id] = datetime.utcnow() + timedelta(hours=lock_duration)
    await channel.send(
        embed=discord.Embed(
            title="🔒 Channel Locked",
            description=f"Locked for {lock_duration} hours",
            color=discord.Color.red()
        ),
        view=UnlockView(channel)
    )

async def unlock_channel(channel, user):
    await set_perm(channel, None, None)
    lock_timers.pop(channel.id, None)
    await channel.send(
        embed=discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"Unlocked by {user.mention}",
            color=discord.Color.green()
        )
    )

# ---------------- AUTO UNLOCK TASK ----------------
@tasks.loop(seconds=60)
async def unlock_task():
    now = datetime.utcnow()
    for cid, end in list(lock_timers.items()):
        if now >= end:
            ch = bot.get_channel(cid)
            if ch:
                await unlock_channel(ch, bot.user)

# ---------------- UNLOCK BUTTON ----------------
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock(self, interaction: discord.Interaction, _):
        await unlock_channel(self.channel, interaction.user)
        await interaction.response.send_message("Unlocked.", ephemeral=True)

# ---------------- VIEW LOCKED (.vl) ----------------
class LockedView(View):
    def __init__(self, pages):
        super().__init__(timeout=120)
        self.pages = pages
        self.i = 0

    async def update(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.i], view=self)

    @discord.ui.button(label="⬅", style=discord.ButtonStyle.gray)
    async def back(self, interaction, _):
        if self.i > 0:
            self.i -= 1
        await self.update(interaction)

    @discord.ui.button(label="➡", style=discord.ButtonStyle.gray)
    async def next(self, interaction, _):
        if self.i < len(self.pages) - 1:
            self.i += 1
        await self.update(interaction)

@bot.command()
async def vl(ctx):
    if not isinstance(lock_timers, dict) or not lock_timers:
        await ctx.send("No locked channels.")
        return

    items = list(lock_timers.items())  # FORCE LIST
    pages = []

    for i in range(0, len(items), 10):
        embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
        for cid, end in items[i:i+10]:
            ch = bot.get_channel(cid)
            if ch:
                embed.add_field(
                    name=ch.name,
                    value=f"Unlocks <t:{int(end.timestamp())}:R>",
                    inline=False
                )
        pages.append(embed)

    await ctx.send(embed=pages[0], view=LockedView(pages))

# ---------------- CATEGORY BLACKLIST ----------------
@bot.group(invoke_without_command=True)
async def blacklist(ctx):
    await ctx.send("`.blacklist category add/remove <category>`")

@blacklist.group()
async def category(ctx): ...

@category.command()
@commands.has_permissions(manage_channels=True)
async def add(ctx, category: discord.CategoryChannel):
    blacklisted_categories.add(category.id)
    add_category(category.id)
    await ctx.send(f"🚫 {category.name} blacklisted")

@category.command()
@commands.has_permissions(manage_channels=True)
async def remove(ctx, category: discord.CategoryChannel):
    blacklisted_categories.discard(category.id)
    remove_category(category.id)
    await ctx.send(f"✅ {category.name} unblacklisted")

# ---------------- HELP COMMAND ----------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📘 Bot Commands", color=discord.Color.blue())
    embed.add_field(name=".help", value="Show this menu", inline=False)
    embed.add_field(name=".vl", value="View locked channels", inline=False)
    embed.add_field(name=".blacklist category add <category>", value="Blacklist category", inline=False)
    embed.add_field(name=".blacklist category remove <category>", value="Unblacklist category", inline=False)
    await ctx.send(embed=embed)

# ---------------- RUN ----------------
bot.run(BOT_TOKEN)
