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

# ---------------- KEEP ALIVE ----------------
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
lock_duration = 12
startup_fallback_hours = 1

KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

blacklisted_channels = set()
blacklisted_categories = set()
lock_timers: dict[int, datetime] = {}

# ---------------- DATABASE ----------------
def db():
    c = sqlite3.connect("bot_database.db")
    c.row_factory = sqlite3.Row
    return c

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

def add_channel_bl(cid):
    c = db()
    c.execute("INSERT OR IGNORE INTO blacklisted_channels VALUES (?)", (cid,))
    c.commit()
    c.close()

def remove_channel_bl(cid):
    c = db()
    c.execute("DELETE FROM blacklisted_channels WHERE channel_id=?", (cid,))
    c.commit()
    c.close()

def add_category_bl(cid):
    c = db()
    c.execute("INSERT OR IGNORE INTO blacklisted_categories VALUES (?)", (cid,))
    c.commit()
    c.close()

def remove_category_bl(cid):
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
    await scan_existing_locks()

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

    # AUTO LOCK (respects blacklist)
    if message.author.bot and message.content:
        if message.channel.id in blacklisted_channels:
            await bot.process_commands(message)
            return

        cat = message.channel.category
        if cat and cat.id in blacklisted_categories:
            await bot.process_commands(message)
            return

        if any(k in message.content.lower() for k, v in KEYWORDS.items() if v):
            await lock_channel(message.channel)

    await bot.process_commands(message)

# ---------------- STARTUP SCAN ----------------
async def scan_existing_locks():
    now = datetime.utcnow()
    recovered = 0

    for guild in bot.guilds:
        try:
            poketwo = await guild.fetch_member(POKETWO_ID)
        except:
            continue

        for channel in guild.text_channels:
            ow = channel.overwrites_for(poketwo)
            if ow.view_channel is False or ow.send_messages is False:
                if channel.id not in lock_timers:
                    lock_timers[channel.id] = now + timedelta(hours=startup_fallback_hours)
                    recovered += 1

    logging.info(f"Recovered {recovered} locked channels")

# ---------------- PERMISSIONS ----------------
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

# ---------------- LOCK / UNLOCK ----------------
async def lock_channel(channel):
    if channel.id in lock_timers:
        return

    await set_perm(channel, False, False)
    lock_timers[channel.id] = datetime.utcnow() + timedelta(hours=lock_duration)

    embed = discord.Embed(
        title="🔒 Channel Locked",
        description=f"Locked for {lock_duration} hours.",
        color=discord.Color.red()
    )
    await channel.send(embed=embed, view=UnlockView(channel))

async def unlock_channel(channel, user):
    if channel.id not in lock_timers:
        return

    await set_perm(channel, None, None)
    lock_timers.pop(channel.id, None)

    embed = discord.Embed(
        title="🔓 Channel Unlocked",
        description=f"Unlocked by {user.mention}",
        color=discord.Color.green()
    )
    await channel.send(embed=embed)

# ---------------- AUTO UNLOCK ----------------
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
        await interaction.response.send_message("Channel unlocked.", ephemeral=True)

# ---------------- COMMANDS ----------------
@bot.command()
async def lock(ctx):
    await lock_channel(ctx.channel)
    await ctx.message.delete()

@bot.command()
async def unlock(ctx):
    await unlock_channel(ctx.channel, ctx.author)
    await ctx.message.delete()

# ---------------- VIEW LOCKED ----------------
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
    if not lock_timers:
        await ctx.send("No locked channels.")
        return

    items = list(lock_timers.items())
    pages = []

    for i in range(0, len(items), 10):
        embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
        for cid, end in items[i:i + 10]:
            ch = bot.get_channel(cid)
            if ch:
                embed.add_field(
                    name=ch.name,
                    value=f"Unlocks <t:{int(end.timestamp())}:R>",
                    inline=False
                )
        pages.append(embed)

    await ctx.send(embed=pages[0], view=LockedView(pages))

# ---------------- BLACKLIST COMMANDS ----------------
@bot.group(invoke_without_command=True)
async def blacklist(ctx):
    await ctx.send(
        "`.blacklist channel add/remove <channel>`\n"
        "`.blacklist category add/remove <category>`"
    )

@blacklist.group()
async def channel(ctx): ...

@channel.command(name="add")
@commands.has_permissions(manage_channels=True)
async def bl_channel_add(ctx, channel: discord.TextChannel):
    blacklisted_channels.add(channel.id)
    add_channel_bl(channel.id)
    await ctx.send(f"🚫 {channel.mention} blacklisted")

@channel.command(name="remove")
@commands.has_permissions(manage_channels=True)
async def bl_channel_remove(ctx, channel: discord.TextChannel):
    blacklisted_channels.discard(channel.id)
    remove_channel_bl(channel.id)
    await ctx.send(f"✅ {channel.mention} unblacklisted")

@blacklist.group()
async def category(ctx): ...

@category.command(name="add")
@commands.has_permissions(manage_channels=True)
async def bl_category_add(ctx, category: discord.CategoryChannel):
    blacklisted_categories.add(category.id)
    add_category_bl(category.id)
    await ctx.send(f"🚫 {category.name} blacklisted")

@category.command(name="remove")
@commands.has_permissions(manage_channels=True)
async def bl_category_remove(ctx, category: discord.CategoryChannel):
    blacklisted_categories.discard(category.id)
    remove_category_bl(category.id)
    await ctx.send(f"✅ {category.name} unblacklisted")

# ---------------- HELP ----------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="📘 Commands", color=discord.Color.blue())
    embed.add_field(name=".lock / .unlock", value="Lock or unlock channel", inline=False)
    embed.add_field(name=".vl", value="View locked channels", inline=False)
    embed.add_field(name=".blacklist", value="Manage blacklist", inline=False)
    await ctx.send(embed=embed)

# ---------------- RUN ----------------
bot.run(BOT_TOKEN)
