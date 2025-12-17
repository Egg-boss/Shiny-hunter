import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
import logging
from datetime import datetime, timedelta
import threading
from flask import Flask

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
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

POKETWO_ID = 716390085896962058

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ---------------- CONFIG / IN-MEMORY ----------------
lock_duration = 12  # default hours

blacklisted_channels = set()
blacklisted_categories = set()
lock_timers = {}

KEYWORDS = [
    "shiny hunt pings",
    "collection pings",
    "rare ping"
]

# ---------------- UNLOCK VIEW ----------------
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction, button):
        await unlock_channel(self.channel, interaction.user)
        await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)

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

async def lock_channel(channel, duration=None):
    if channel.id in lock_timers:
        return
    await set_channel_permissions(channel, False, False)
    lock_timers[channel.id] = datetime.now() + timedelta(hours=duration or lock_duration)

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

# ---------------- STARTUP SCAN ----------------
async def startup_lock_scan():
    logging.info("🔎 Startup scan running...")
    for cid, end in lock_timers.items():
        channel = bot.get_channel(cid)
        if not channel:
            continue
        if channel.id in blacklisted_channels:
            continue
        if channel.category and channel.category.id in blacklisted_categories:
            continue
        await set_channel_permissions(channel, False, False)
        logging.info(f"🔒 Re-locked #{channel.name}")

async def startup_history_scan():
    logging.info("📜 Running history fallback scan...")
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
                    if "🔓 Channel Unlocked" in title:
                        break
                    if "🔒 Channel Locked" in title:
                        await lock_channel(channel)
                        logging.info(f"🔒 Restored lock from history: #{channel.name}")
                        break
            except Exception as e:
                logging.warning(f"Failed scanning #{channel.name}: {e}")
                continue

# ---------------- AUTO UNLOCK LOOP ----------------
@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()
    for cid, end in list(lock_timers.items()):
        if now >= end:
            channel = bot.get_channel(cid)
            if channel:
                await unlock_channel(channel, bot.user)
            lock_timers.pop(cid, None)

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    logging.info(f"✅ Bot online as {bot.user}")
    await startup_lock_scan()
    await startup_history_scan()
    await bot.tree.sync()
    if not check_lock_timers.is_running():
        check_lock_timers.start()

@bot.event
async def on_message(msg):
    if msg.guild and msg.author.bot:
        if msg.channel.id in blacklisted_channels:
            return
        if msg.channel.category and msg.channel.category.id in blacklisted_categories:
            return
        if any(k in msg.content.lower() for k in KEYWORDS):
            await lock_channel(msg.channel)
            embed = discord.Embed(title="🔒 Channel Locked", color=discord.Color.red())
            await msg.channel.send(embed=embed, view=UnlockView(msg.channel))
    await bot.process_commands(msg)
from discord import app_commands

# ---------------- CONFIG / SERVER ----------------
# per-guild config stored in memory
server_config = {}  # guild_id: {"lock_hours":12, "keywords_enabled":True}

def get_config(guild_id):
    if guild_id not in server_config:
        server_config[guild_id] = {"lock_hours": lock_duration, "keywords_enabled": True}
    return server_config[guild_id]

# ---------------- BLACKLIST COMMANDS ----------------
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
    await ctx.send(f"{channel.mention} blacklisted")

@blacklist.command()
async def remove(ctx, channel: discord.TextChannel):
    blacklisted_channels.discard(channel.id)
    await ctx.send(f"{channel.mention} removed")

@blacklist.command()
async def addcategory(ctx, *, name):
    cat = discord.utils.get(ctx.guild.categories, name=name)
    if not cat:
        return await ctx.send("Category not found")
    blacklisted_categories.add(cat.id)
    await ctx.send(f"Category **{cat.name}** blacklisted")

@blacklist.command()
async def removecategory(ctx, *, name):
    cat = discord.utils.get(ctx.guild.categories, name=name)
    if not cat:
        return await ctx.send("Category not found")
    blacklisted_categories.discard(cat.id)
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

# ---------------- LOCK COMMANDS ----------------
@bot.command()
async def lock(ctx):
    cfg = get_config(ctx.guild.id)
    await lock_channel(ctx.channel, cfg["lock_hours"])
    await ctx.send("🔒 Channel locked", view=UnlockView(ctx.channel))

@bot.command()
async def unlock(ctx):
    await unlock_channel(ctx.channel, ctx.author)

@bot.command()
async def locked(ctx):
    if not lock_timers:
        return await ctx.send("🔓 No channels are locked.")
    pages = []
    items = list(lock_timers.items())
    for i in range(0, len(items), 5):
        embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
        for cid, end in items[i:i+5]:
            ch = bot.get_channel(cid)
            if not ch:
                continue
            mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
            embed.add_field(name=ch.name, value=f"{ch.mention}\nUnlocks in {mins} min", inline=False)
        pages.append(embed)
    if len(pages) == 1:
        await ctx.send(embed=pages[0])
    else:
        await ctx.send(embed=pages[0], view=LockedPaginator(pages))

@bot.command()
async def check_timer(ctx):
    if ctx.channel.id in lock_timers:
        mins = int((lock_timers[ctx.channel.id] - datetime.now()).total_seconds() // 60)
        await ctx.send(f"Unlocks in {mins} minutes")
    else:
        await ctx.send("Channel not locked")

# ---------------- CONFIG COMMANDS ----------------
@bot.command()
@commands.has_permissions(manage_guild=True)
async def setlockhours(ctx, hours: int):
    if hours < 1 or hours > 72:
        return await ctx.send("Lock hours must be between 1 and 72")
    cfg = get_config(ctx.guild.id)
    cfg["lock_hours"] = hours
    await ctx.send(f"🔧 Lock duration set to **{hours} hours**")

@bot.command()
@commands.has_permissions(manage_guild=True)
async def keywords(ctx, state: str):
    state = state.lower()
    if state not in ("on","off"):
        return await ctx.send("Use: `.keywords on` or `.keywords off`")
    cfg = get_config(ctx.guild.id)
    cfg["keywords_enabled"] = True if state == "on" else False
    await ctx.send(f"🔑 Keyword detection **{state.upper()}**")

@bot.command()
async def config(ctx):
    cfg = get_config(ctx.guild.id)
    embed = discord.Embed(title="Server Config", color=discord.Color.blue())
    embed.add_field(name="Lock Hours", value=cfg["lock_hours"], inline=False)
    embed.add_field(name="Keywords", value="ON" if cfg["keywords_enabled"] else "OFF", inline=False)
    await ctx.send(embed=embed)

# ---------------- OWNER COMMANDS ----------------
@bot.command()
async def owner(ctx):
    await ctx.send(f"Made by Buddy! ID: {OWNER_ID}")

@bot.command()
async def servers(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the bot owner can use this.")
    lines = [f"{guild.name} ({guild.id})" for guild in bot.guilds]
    await ctx.send("\n".join(lines) if lines else "Not in any servers")

@bot.command()
async def shutdown(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("Only the bot owner can use this.")
    await ctx.send("Shutting down...")
    await bot.close()

# ---------------- HELP COMMAND ----------------
@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())
    cmds = {
        ".help": "Show this menu",
        ".lock": "Lock channel",
        ".unlock": "Unlock channel (anyone)",
        ".locked": "List locked channels",
        ".check_timer": "Check lock timer",
        ".blacklist": "Manage blacklists",
        ".setlockhours": "Set lock duration per server",
        ".keywords": "Enable/disable keyword detection",
        ".config": "View server config",
        ".owner": "Bot creator",
        ".servers": "List servers (owner only)",
        ".shutdown": "Shutdown bot (owner only)",
    }
    for c,d in cmds.items():
        embed.add_field(name=c, value=d, inline=False)
    await ctx.send(embed=embed)

# ---------------- PAGINATOR ----------------
class LockedPaginator(View):
    def __init__(self, pages):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0

    async def update(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction, _):
        if self.index > 0:
            self.index -= 1
        await self.update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, _):
        if self.index < len(self.pages)-1:
            self.index += 1
        await self.update(interaction)

# ---------------- SLASH COMMANDS ----------------
@bot.tree.command(name="lock", description="Lock the current channel")
async def slash_lock(interaction: discord.Interaction):
    cfg = get_config(interaction.guild.id)
    await lock_channel(interaction.channel, cfg["lock_hours"])
    await interaction.response.send_message("🔒 Channel locked", ephemeral=True)

@bot.tree.command(name="unlock", description="Unlock the current channel")
async def slash_unlock(interaction: discord.Interaction):
    await unlock_channel(interaction.channel, interaction.user)
    await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)

@bot.tree.command(name="locked", description="Show locked channels")
async def slash_locked(interaction: discord.Interaction):
    if not lock_timers:
        return await interaction.response.send_message("🔓 No channels locked", ephemeral=True)
    pages = []
    items = list(lock_timers.items())
    for i in range(0, len(items), 5):
        embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
        for cid, end in items[i:i+5]:
            ch = bot.get_channel(cid)
            if not ch:
                continue
            mins = max(int((end - datetime.now()).total_seconds() // 60),0)
            embed.add_field(name=ch.name, value=f"{ch.mention}\nUnlocks in {mins} min", inline=False)
        pages.append(embed)
    await interaction.response.send_message(embed=pages[0], view=LockedPaginator(pages), ephemeral=True)
# ---------------- SLASH COMMANDS (CONTINUED) ----------------
@bot.tree.command(name="check_timer", description="Check lock timer for this channel")
async def slash_check_timer(interaction: discord.Interaction):
    if interaction.channel.id in lock_timers:
        mins = int((lock_timers[interaction.channel.id] - datetime.now()).total_seconds() // 60)
        await interaction.response.send_message(f"Unlocks in {mins} minutes", ephemeral=True)
    else:
        await interaction.response.send_message("Channel not locked", ephemeral=True)

@bot.tree.command(name="config", description="View server config")
async def slash_config(interaction: discord.Interaction):
    cfg = get_config(interaction.guild.id)
    embed = discord.Embed(title="Server Config", color=discord.Color.blue())
    embed.add_field(name="Lock Hours", value=cfg["lock_hours"], inline=False)
    embed.add_field(name="Keywords", value="ON" if cfg["keywords_enabled"] else "OFF", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="keywords", description="Enable or disable keyword detection")
@app_commands.describe(state="on/off")
async def slash_keywords(interaction: discord.Interaction, state: str):
    state = state.lower()
    if state not in ("on","off"):
        return await interaction.response.send_message("Use `/keywords on` or `/keywords off`", ephemeral=True)
    cfg = get_config(interaction.guild.id)
    cfg["keywords_enabled"] = True if state == "on" else False
    await interaction.response.send_message(f"🔑 Keyword detection **{state.upper()}**", ephemeral=True)

@bot.tree.command(name="setlockhours", description="Set lock duration in hours")
@app_commands.describe(hours="Lock duration between 1-72 hours")
async def slash_setlockhours(interaction: discord.Interaction, hours: int):
    if interaction.user.guild_permissions.manage_guild is False:
        return await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
    if hours < 1 or hours > 72:
        return await interaction.response.send_message("Lock hours must be between 1 and 72", ephemeral=True)
    cfg = get_config(interaction.guild.id)
    cfg["lock_hours"] = hours
    await interaction.response.send_message(f"🔧 Lock duration set to **{hours} hours**", ephemeral=True)

@bot.tree.command(name="owner", description="Show bot owner")
async def slash_owner(interaction: discord.Interaction):
    await interaction.response.send_message(f"Made by Buddy! ID: {OWNER_ID}", ephemeral=True)

@bot.tree.command(name="servers", description="List all servers the bot is in (owner only)")
async def slash_servers(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Only the bot owner can use this.", ephemeral=True)
    lines = [f"{guild.name} ({guild.id})" for guild in bot.guilds]
    await interaction.response.send_message("\n".join(lines) if lines else "Not in any servers", ephemeral=True)

@bot.tree.command(name="shutdown", description="Shutdown the bot (owner only)")
async def slash_shutdown(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Only the bot owner can use this.", ephemeral=True)
    await interaction.response.send_message("Shutting down...", ephemeral=True)
    await bot.close()

# ---------------- START ----------------
keep_alive()
bot.run(BOT_TOKEN)
