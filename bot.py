import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta
import sqlite3
import threading
import time

# ---------------- KEEP ALIVE ----------------
try:
    from flask import Flask
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "Bot alive"

    def keep_alive():
        threading.Thread(
            target=lambda: app.run(host="0.0.0.0", port=8080),
            daemon=True
        ).start()
except:
    def keep_alive():
        pass

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------- ENV ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

START_TIME = time.time()
POKETWO_ID = 716390085896962058
LOCK_HOURS = 12

KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ---------------- DATABASE ----------------
def db():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db()
    c.execute("CREATE TABLE IF NOT EXISTS blacklisted_channels (channel_id INTEGER UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS blacklisted_categories (category_id INTEGER UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS locks (channel_id INTEGER UNIQUE, unlock_at TEXT)")
    c.commit()
    c.close()

init_db()

# ---------------- LOAD STATE ----------------
blacklisted_channels = set()
blacklisted_categories = set()
lock_timers = {}

def load_state():
    global blacklisted_channels, blacklisted_categories, lock_timers
    c = db()

    blacklisted_channels = {r["channel_id"] for r in c.execute("SELECT channel_id FROM blacklisted_channels")}
    blacklisted_categories = {r["category_id"] for r in c.execute("SELECT category_id FROM blacklisted_categories")}

    now = datetime.now()
    for r in c.execute("SELECT * FROM locks"):
        end = datetime.fromisoformat(r["unlock_at"])
        if end > now:
            lock_timers[r["channel_id"]] = end

    c.close()

# ---------------- LOCK HELPERS ----------------
async def set_permissions(channel, lock: bool):
    try:
        p2 = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return

    if lock:
        await channel.set_permissions(p2, view_channel=False, send_messages=False)
    else:
        await channel.set_permissions(p2, overwrite=None)

async def lock_channel(channel):
    if channel.id in lock_timers:
        return

    end = datetime.now() + timedelta(hours=LOCK_HOURS)
    lock_timers[channel.id] = end

    d = db()
    d.execute("INSERT OR REPLACE INTO locks VALUES (?,?)", (channel.id, end.isoformat()))
    d.commit()
    d.close()

    await set_permissions(channel, True)

async def unlock_channel(channel, user):
    await set_permissions(channel, False)
    lock_timers.pop(channel.id, None)

    d = db()
    d.execute("DELETE FROM locks WHERE channel_id=?", (channel.id,))
    d.commit()
    d.close()

    await channel.send(
        embed=discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"Unlocked by {user.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
    )

# ---------------- UNLOCK VIEW ----------------
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock(self, interaction: discord.Interaction, button: Button):
        await unlock_channel(self.channel, interaction.user)
        await interaction.response.send_message("Unlocked", ephemeral=True)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    load_state()
    logging.info(f"Online as {bot.user}")
    check_lock_timers.start()
    try:
        await bot.tree.sync()
    except:
        pass

@bot.event
async def on_message(msg):
    if msg.author.bot and msg.content:
        if msg.channel.id in blacklisted_channels:
            return
        if msg.channel.category and msg.channel.category.id in blacklisted_categories:
            return

        if any(k in msg.content.lower() for k, v in KEYWORDS.items() if v):
            await lock_channel(msg.channel)
            await msg.channel.send(
                embed=discord.Embed(
                    title="🔒 Channel Locked",
                    description=f"Locked for {LOCK_HOURS} hours",
                    color=discord.Color.red()
                ),
                view=UnlockView(msg.channel)
            )

    await bot.process_commands(msg)

# ---------------- TIMER ----------------
@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()

    for cid, end in list(lock_timers.items()):
        if now < end:
            continue

        channel = bot.get_channel(cid)
        if not channel:
            for g in bot.guilds:
                try:
                    channel = await g.fetch_channel(cid)
                    break
                except:
                    continue

        if channel:
            await unlock_channel(channel, bot.user)
        lock_timers.pop(cid, None)

# ---------------- COMMANDS ----------------
@bot.command()
async def lock(ctx):
    await lock_channel(ctx.channel)
    await ctx.send("🔒 Locked", view=UnlockView(ctx.channel))

@bot.command()
async def unlock(ctx):
    await unlock_channel(ctx.channel, ctx.author)

@bot.command()
async def locked(ctx):
    if not lock_timers:
        return await ctx.send("No locks")

    now = datetime.now()
    items = [(c, t) for c, t in lock_timers.items() if t > now]
    chunks = [items[i:i+25] for i in range(0, len(items), 25)]

    for i, chunk in enumerate(chunks, 1):
        embed = discord.Embed(title=f"🔒 Locked ({i}/{len(chunks)})", color=discord.Color.red())
        for cid, end in chunk:
            ch = bot.get_channel(cid)
            if not ch:
                continue
            mins = int((end-now).total_seconds()//60)
            embed.add_field(name=ch.name, value=f"{ch.mention} `{mins}m`", inline=True)
        await ctx.send(embed=embed)

@bot.command()
async def stats(ctx):
    uptime = int((time.time() - START_TIME) // 60)
    await ctx.send(
        embed=discord.Embed(
            title="📊 Bot Stats",
            description=f"Uptime: `{uptime}m`\nServers: `{len(bot.guilds)}`\nLocked: `{len(lock_timers)}`",
            color=discord.Color.blue()
        )
    )

@bot.command()
@commands.is_owner()
async def servers(ctx):
    embed = discord.Embed(title="🌐 Servers", color=discord.Color.blue())
    for g in bot.guilds:
        embed.add_field(name=g.name, value=f"ID `{g.id}` | {g.member_count} members", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.is_owner()
async def leave(ctx, server_id: int):
    g = bot.get_guild(server_id)
    if not g:
        return await ctx.send("Not found")
    await g.leave()
    await ctx.send(f"Left **{g.name}**")

@bot.command()
async def where(ctx):
    await ctx.send(f"Server: **{ctx.guild.name}**\nChannel: {ctx.channel.mention}")

@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Commands", color=discord.Color.blue())
    cmds = [
        ".lock", ".unlock", ".locked", ".stats", ".where",
        ".servers (owner)", ".leave <id> (owner)"
    ]
    for c in cmds:
        embed.add_field(name=c, value="\u200b", inline=False)
    await ctx.send(embed=embed)

# ---------------- SLASH ----------------
@bot.tree.command(name="lock")
async def slash_lock(interaction: discord.Interaction):
    await lock_channel(interaction.channel)
    await interaction.response.send_message("Locked", ephemeral=True)

@bot.tree.command(name="unlock")
async def slash_unlock(interaction: discord.Interaction):
    await unlock_channel(interaction.channel, interaction.user)
    await interaction.response.send_message("Unlocked", ephemeral=True)

@bot.tree.command(name="locked")
async def slash_locked(interaction: discord.Interaction):
    await interaction.response.send_message(f"Locked channels: {len(lock_timers)}", ephemeral=True)

# ---------------- START ----------------
keep_alive()
bot.run(BOT_TOKEN)
