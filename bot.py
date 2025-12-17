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

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------- ENV ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

POKETWO_ID = 716390085896962058

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ---------------- CONFIG ----------------
lock_duration = 12  # hours

KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

blacklisted_channels = set()
blacklisted_categories = set()
lock_timers = {}

# ---------------- DATABASE ----------------
def db():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db()
    c.execute("CREATE TABLE IF NOT EXISTS blacklisted_channels (channel_id INTEGER UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS blacklisted_categories (category_id INTEGER UNIQUE)")
    c.close()

def load_blacklists():
    c = db()
    channels = {r["channel_id"] for r in c.execute("SELECT channel_id FROM blacklisted_channels")}
    categories = {r["category_id"] for r in c.execute("SELECT category_id FROM blacklisted_categories")}
    c.close()
    return channels, categories

def add_blacklist_channel(cid):
    d = db()
    d.execute("INSERT OR IGNORE INTO blacklisted_channels VALUES (?)", (cid,))
    d.commit()
    d.close()

def remove_blacklist_channel(cid):
    d = db()
    d.execute("DELETE FROM blacklisted_channels WHERE channel_id=?", (cid,))
    d.commit()
    d.close()

def add_blacklist_category(cid):
    d = db()
    d.execute("INSERT OR IGNORE INTO blacklisted_categories VALUES (?)", (cid,))
    d.commit()
    d.close()

def remove_blacklist_category(cid):
    d = db()
    d.execute("DELETE FROM blacklisted_categories WHERE category_id=?", (cid,))
    d.commit()
    d.close()

init_db()

# ---------------- UNLOCK VIEW ----------------
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction, button):
        await unlock_channel(self.channel, interaction.user)
        await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    global blacklisted_channels, blacklisted_categories
    blacklisted_channels, blacklisted_categories = load_blacklists()
    logging.info(f"Bot online as {bot.user}")

    await scan_existing_locks()

    if not check_lock_timers.is_running():
        check_lock_timers.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.author.bot and message.content:
        if message.channel.id in blacklisted_channels:
            return
        if message.channel.category and message.channel.category.id in blacklisted_categories:
            return

        active_keywords = [k for k, v in KEYWORDS.items() if v]
        if any(k in message.content.lower() for k in active_keywords):
            await lock_channel(message.channel)

            embed = discord.Embed(
                title="🔒 Channel Locked",
                description=f"Locked for {lock_duration} hours due to keyword detection.",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.add_field(
                name="Unlocks At",
                value=(datetime.now() + timedelta(hours=lock_duration)).strftime("%Y-%m-%d %H:%M:%S"),
                inline=False
            )
            await message.channel.send(embed=embed, view=UnlockView(message.channel))

    await bot.process_commands(message)

# ---------------- LOCK SYSTEM ----------------
async def set_channel_permissions(channel, view=None, send=None):
    try:
        poketwo = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return

    ow = channel.overwrites_for(poketwo)
    ow.view_channel = view if view is not None else True
    ow.send_messages = send if send is not None else True
    await channel.set_permissions(poketwo, overwrite=ow)

async def lock_channel(channel):
    if channel.id in lock_timers:
        return
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
    for cid, end in list(lock_timers.items()):
        if now >= end:
            channel = bot.get_channel(cid)
            if channel:
                await unlock_channel(channel, bot.user)
            lock_timers.pop(cid, None)

# ---------------- STARTUP SCAN (SAFE) ----------------
async def scan_existing_locks():
    await bot.wait_until_ready()

    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.id in blacklisted_channels:
                continue
            if channel.category and channel.category.id in blacklisted_categories:
                continue

            try:
                async for msg in channel.history(limit=30):
                    if not msg.embeds:
                        continue

                    title = msg.embeds[0].title or ""

                    # Stop if unlocked found
                    if "🔓 Channel Unlocked" in title:
                        break

                    # Restore lock if found first
                    if "🔒 Channel Locked" in title:
                        lock_timers[channel.id] = datetime.now() + timedelta(hours=lock_duration)
                        logging.info(f"Restored lock in #{channel.name}")
                        break
            except:
                continue

# ---------------- COMMANDS ----------------
@bot.group(invoke_without_command=True)
async def blacklist(ctx):
    await ctx.send(
        "**Blacklist Commands**\n"
        ".blacklist add #channel\n"
        ".blacklist remove #channel\n"
        ".blacklist addcategory <category name>\n"
        ".blacklist removecategory <category name>\n"
        ".blacklist list"
    )

@blacklist.command()
async def add(ctx, channel: discord.TextChannel):
    blacklisted_channels.add(channel.id)
    add_blacklist_channel(channel.id)
    await ctx.send(f"{channel.mention} blacklisted")

@blacklist.command()
async def remove(ctx, channel: discord.TextChannel):
    blacklisted_channels.discard(channel.id)
    remove_blacklist_channel(channel.id)
    await ctx.send(f"{channel.mention} removed")

@blacklist.command()
async def addcategory(ctx, *, name):
    cat = discord.utils.get(ctx.guild.categories, name=name)
    if not cat:
        return await ctx.send("Category not found")
    blacklisted_categories.add(cat.id)
    add_blacklist_category(cat.id)
    await ctx.send(f"Category **{cat.name}** blacklisted")

@blacklist.command()
async def removecategory(ctx, *, name):
    cat = discord.utils.get(ctx.guild.categories, name=name)
    if not cat:
        return await ctx.send("Category not found")
    blacklisted_categories.discard(cat.id)
    remove_blacklist_category(cat.id)
    await ctx.send(f"Category **{cat.name}** removed")

@blacklist.command()
async def list(ctx):
    lines = []
    for cid in blacklisted_channels:
        ch = bot.get_channel(cid)
        if ch:
            lines.append(f"Channel: {ch.mention}")
    for cid in blacklisted_categories:
        cat = discord.utils.get(ctx.guild.categories, id=cid)
        if cat:
            lines.append(f"Category: **{cat.name}**")

    await ctx.send("\n".join(lines) if lines else "No blacklists set")

@bot.command()
async def locked(ctx):
    if not lock_timers:
        return await ctx.send("🔓 No channels are locked.")

    embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
    for cid, end in lock_timers.items():
        ch = bot.get_channel(cid)
        if not ch:
            continue
        mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
        embed.add_field(name=ch.name, value=f"{ch.mention}\nUnlocks in {mins} min", inline=False)

    await ctx.send(embed=embed)

@bot.command()
async def lock(ctx):
    await lock_channel(ctx.channel)
    await ctx.send("🔒 Channel locked", view=UnlockView(ctx.channel))

@bot.command()
async def unlock(ctx):
    await unlock_channel(ctx.channel, ctx.author)

@bot.command()
async def check_timer(ctx):
    if ctx.channel.id in lock_timers:
        mins = int((lock_timers[ctx.channel.id] - datetime.now()).total_seconds() // 60)
        await ctx.send(f"Unlocks in {mins} minutes")
    else:
        await ctx.send("Channel not locked")

@bot.command()
async def owner(ctx):
    await ctx.send("Made by Buddy maybe say thanks")

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())
    cmds = {
        ".help": "Show this menu",
        ".lock": "Lock channel",
        ".unlock": "Unlock channel (anyone)",
        ".locked": "List locked channels",
        ".blacklist": "Manage blacklists",
        ".check_timer": "Check lock timer",
        ".owner": "Bot creator",
    }
    for c, d in cmds.items():
        embed.add_field(name=c, value=d, inline=False)
    await ctx.send(embed=embed)

# ---------------- START ----------------
keep_alive()
bot.run(BOT_TOKEN)
