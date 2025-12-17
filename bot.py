from discord import app_commands
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta
import threading
from flask import Flask

# ---------------- ENV ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
POKETWO_ID = 716390085896962058

if not BOT_TOKEN or not OWNER_ID:
    raise RuntimeError("BOT_TOKEN or OWNER_ID missing in environment")

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------- KEEP ALIVE ----------------
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot is alive"

def keep_alive():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True).start()

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ---------------- GLOBALS ----------------
lock_duration = 12  # default lock duration
KEYWORDS = ["shiny hunt pings", "collection pings", "rare ping"]

blacklisted_channels = set()
blacklisted_categories = set()
lock_timers = {}  # channel_id: unlock_datetime

server_config = {}  # guild_id: {"lock_hours":12, "keywords_enabled":True}

# ---------------- CONFIG HELPERS ----------------
def get_config(guild_id):
    if guild_id not in server_config:
        server_config[guild_id] = {"lock_hours": lock_duration, "keywords_enabled": True}
    return server_config[guild_id]

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
    """Adjust PokeTwo bot permissions in the channel"""
    try:
        poketwo = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return

    ow = channel.overwrites_for(poketwo)
    ow.view_channel = view if view is not None else True
    ow.send_messages = send if send is not None else True
    await channel.set_permissions(poketwo, overwrite=ow)

async def lock_channel(channel, hours=None):
    """Lock a channel for X hours"""
    if channel.id in lock_timers:
        return

    cfg = get_config(channel.guild.id)
    duration = hours or cfg["lock_hours"]
    await set_channel_permissions(channel, view=False, send=False)
    lock_timers[channel.id] = datetime.now() + timedelta(hours=duration)

async def unlock_channel(channel, user):
    """Unlock a channel and remove from lock timers"""
    await set_channel_permissions(channel, view=None, send=None)
    lock_timers.pop(channel.id, None)
    embed = discord.Embed(
        title="🔓 Channel Unlocked",
        description=f"Unlocked by {user.mention}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    await channel.send(embed=embed)

# ================= STARTUP SCAN =================
async def startup_lock_scan():
    """Restore locks from memory (in-memory only)"""
    logging.info("🔎 Startup scan running...")
    for cid, end in lock_timers.copy().items():
        channel = bot.get_channel(cid)
        if not channel:
            continue
        if channel.id in blacklisted_channels:
            continue
        if channel.category and channel.category.id in blacklisted_categories:
            continue

        await set_channel_permissions(channel, view=False, send=False)
        logging.info(f"🔒 Re-locked #{channel.name}")

async def startup_history_scan():
    """Scan recent messages to restore old locked channels based on embeds"""
    await bot.wait_until_ready()
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

# ================= AUTO UNLOCK TASK =================
@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()
    for cid, end in list(lock_timers.items()):
        if now >= end:
            channel = bot.get_channel(cid)
            if channel:
                await unlock_channel(channel, bot.user)
            lock_timers.pop(cid, None)
# ================= EVENTS =================
@bot.event
async def on_ready():
    logging.info(f"✅ Bot online as {bot.user}")

    # Restore any locks already in memory
    await startup_lock_scan()

    # Scan channel history to catch old locked channels not in memory
    await startup_history_scan()

    if not check_lock_timers.is_running():
        check_lock_timers.start()


@bot.event
async def on_message(msg):
    if msg.guild and msg.author.bot:
        if msg.channel.id in blacklisted_channels:
            return
        if msg.channel.category and msg.channel.category.id in blacklisted_categories:
            return

        cfg = get_config(msg.guild.id)
        if cfg["keywords_enabled"] and any(k in msg.content.lower() for k in KEYWORDS):
            await lock_channel(msg.channel)
            embed = discord.Embed(
                title="🔒 Channel Locked",
                description=f"Locked for {cfg['lock_hours']} hours due to keyword detection",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            await msg.channel.send(embed=embed, view=UnlockView(msg.channel))

    await bot.process_commands(msg)

# ================= BLACKLIST COMMANDS =================
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
    await ctx.send(f"{channel.mention} removed from blacklist")

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
    await ctx.send(f"Category **{cat.name}** removed from blacklist")

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

# ================= LOCK/UNLOCK COMMANDS =================
@bot.command()
async def lock(ctx):
    await lock_channel(ctx.channel)
    await ctx.send("🔒 Channel locked", view=UnlockView(ctx.channel))

@bot.command()
async def unlock(ctx):
    await unlock_channel(ctx.channel, ctx.author)

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
async def check_timer(ctx):
    if ctx.channel.id in lock_timers:
        mins = int((lock_timers[ctx.channel.id] - datetime.now()).total_seconds() // 60)
        await ctx.send(f"Unlocks in {mins} minutes")
    else:
        await ctx.send("Channel not locked")

# ================= SERVER CONFIG =================
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
    if state not in ("on", "off"):
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

# ================= HELP COMMAND =================
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
        if self.index < len(self.pages) - 1:
            self.index += 1
        await self.update(interaction)

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
        ".setlockhours": "Set lock duration (manage server)",
        ".keywords": "Toggle keyword detection (manage server)",
        ".config": "View server config",
        ".owner": "Bot creator",
    }
    for c, d in cmds.items():
        embed.add_field(name=c, value=d, inline=False)
    await ctx.send(embed=embed)
# ================= OWNER COMMANDS =================
@bot.command()
async def owner(ctx):
    await ctx.send(f"Made by Buddy | <@{OWNER_ID}>")

@bot.command()
async def servers(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ You cannot use this command.")
    lines = [f"{guild.name} | ID: {guild.id} | Members: {guild.member_count}" for guild in bot.guilds]
    await ctx.send("\n".join(lines) or "No servers found.")

@bot.command()
async def shutdown(ctx):
    if ctx.author.id != OWNER_ID:
        return await ctx.send("❌ You cannot use this command.")
    await ctx.send("⚡ Shutting down...")
    await bot.close()

# ---------------- SLASH LOCK COMMANDS ----------------
@bot.tree.command(name="lock", description="Lock the current channel")
async def slash_lock(interaction: discord.Interaction):
    await lock_channel(interaction.channel)
    await interaction.response.send_message("🔒 Channel locked", ephemeral=True)

@bot.tree.command(name="unlock", description="Unlock the current channel")
async def slash_unlock(interaction: discord.Interaction):
    await unlock_channel(interaction.channel, interaction.user)
    await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)

@bot.tree.command(name="locked", description="Show all locked channels")
async def slash_locked(interaction: discord.Interaction):
    if not lock_timers:
        return await interaction.response.send_message("🔓 No channels are locked.", ephemeral=True)
    embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
    for cid, end in lock_timers.items():
        ch = bot.get_channel(cid)
        if not ch:
            continue
        mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
        embed.add_field(name=ch.name, value=f"{ch.mention}\nUnlocks in {mins} min", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="check_timer", description="Check this channel's lock timer")
async def slash_check_timer(interaction: discord.Interaction):
    if interaction.channel.id in lock_timers:
        mins = int((lock_timers[interaction.channel.id] - datetime.now()).total_seconds() // 60)
        await interaction.response.send_message(f"Unlocks in {mins} minutes", ephemeral=True)
    else:
        await interaction.response.send_message("Channel not locked", ephemeral=True)

# ---------------- SLASH BLACKLIST COMMANDS ----------------
@bot.tree.command(name="blacklist_add", description="Add a channel to the blacklist")
@app_commands.describe(channel="Select a channel")
async def slash_blacklist_add(interaction: discord.Interaction, channel: discord.TextChannel):
    blacklisted_channels.add(channel.id)
    await interaction.response.send_message(f"{channel.mention} added to blacklist", ephemeral=True)

@bot.tree.command(name="blacklist_remove", description="Remove a channel from the blacklist")
@app_commands.describe(channel="Select a channel")
async def slash_blacklist_remove(interaction: discord.Interaction, channel: discord.TextChannel):
    blacklisted_channels.discard(channel.id)
    await interaction.response.send_message(f"{channel.mention} removed from blacklist", ephemeral=True)

@bot.tree.command(name="blacklist_addcategory", description="Add a category to the blacklist")
@app_commands.describe(category="Select a category")
async def slash_blacklist_addcategory(interaction: discord.Interaction, category: discord.CategoryChannel):
    blacklisted_categories.add(category.id)
    await interaction.response.send_message(f"Category **{category.name}** added to blacklist", ephemeral=True)

@bot.tree.command(name="blacklist_removecategory", description="Remove a category from the blacklist")
@app_commands.describe(category="Select a category")
async def slash_blacklist_removecategory(interaction: discord.Interaction, category: discord.CategoryChannel):
    blacklisted_categories.discard(category.id)
    await interaction.response.send_message(f"Category **{category.name}** removed from blacklist", ephemeral=True)

@bot.tree.command(name="blacklist_list", description="List all blacklisted channels and categories")
async def slash_blacklist_list(interaction: discord.Interaction):
    lines = []
    for cid in blacklisted_channels:
        ch = bot.get_channel(cid)
        if ch:
            lines.append(f"Channel: {ch.mention}")
    for cid in blacklisted_categories:
        cat = discord.utils.get(interaction.guild.categories, id=cid)
        if cat:
            lines.append(f"Category: **{cat.name}**")
    await interaction.response.send_message("\n".join(lines) if lines else "No blacklists set", ephemeral=True)

# ---------------- SLASH OWNER COMMANDS ----------------
@bot.tree.command(name="servers", description="List all servers the bot is in (Owner only)")
async def slash_servers(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
    lines = [f"{guild.name} | ID: {guild.id} | Members: {guild.member_count}" for guild in bot.guilds]
    await interaction.response.send_message("\n".join(lines) or "No servers found.", ephemeral=True)

@bot.tree.command(name="shutdown", description="Shut down the bot (Owner only)")
async def slash_shutdown(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ You cannot use this command.", ephemeral=True)
    await interaction.response.send_message("⚡ Shutting down...", ephemeral=True)
    await bot.close()

# ================= KEEP ALIVE & RUN =================
keep_alive()
bot.run(BOT_TOKEN)
