import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
from discord import app_commands
import os
from dotenv import load_dotenv
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
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True).start()

# ---------------- LOGGING ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ---------------- ENV ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
POKETWO_ID = 716390085896962058

# ---------------- DISCORD ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ---------------- CONFIG ----------------
lock_duration_default = 12  # default lock hours
KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}
blacklisted_channels = set()
blacklisted_categories = set()

# ---------------- LOCK TIMERS ----------------
lock_timers = {}  # {channel_id: unlock_datetime}

# ---------------- STARTUP SCAN ----------------
async def startup_lock_scan():
    """Restore any locks currently in memory (lock_timers)"""
    logging.info("🔎 Startup scan running...")
    for cid, end in lock_timers.items():
        channel = bot.get_channel(cid)
        if channel:
            await set_channel_permissions(channel, view=False, send=False)
            logging.info(f"🔒 Re-locked #{channel.name}")

async def startup_history_scan():
    """Scan recent messages to restore old locked channels"""
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
# ---------------- LOCK SYSTEM ----------------
lock_timers = {}  # global dict for tracking locks

async def set_channel_permissions(channel, view=None, send=None):
    """Set Pokétwo permissions for channel"""
    try:
        poketwo = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return
    ow = channel.overwrites_for(poketwo)
    ow.view_channel = view if view is not None else True
    ow.send_messages = send if send is not None else True
    await channel.set_permissions(poketwo, overwrite=ow)

async def lock_channel(channel):
    """Lock a channel and set timer"""
    if channel.id in lock_timers:
        return
    await set_channel_permissions(channel, False, False)
    lock_timers[channel.id] = datetime.now() + timedelta(hours=lock_duration)

async def unlock_channel(channel, user):
    """Unlock channel and remove from lock_timers"""
    await set_channel_permissions(channel, True, True)
    lock_timers.pop(channel.id, None)

    embed = discord.Embed(
        title="🔓 Channel Unlocked",
        description=f"Unlocked by {user.mention}",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    await channel.send(embed=embed)

# ---------------- AUTO UNLOCK LOOP ----------------
@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()
    # lock_timers is always a dict
    for cid, end_time in list(lock_timers.items()):
        if now >= end_time:
            channel = bot.get_channel(cid)
            if channel:
                await unlock_channel(channel, bot.user)
            lock_timers.pop(cid, None)

# ---------------- UNLOCK BUTTON ----------------
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction, button):
        await unlock_channel(self.channel, interaction.user)
        await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)

# ---------------- LOCKED CHANNEL PAGINATOR ----------------
class LockedPaginator(View):
    def __init__(self, pages):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0

    async def update(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _):
        if self.index > 0:
            self.index -= 1
        await self.update(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _):
        if self.index < len(self.pages) - 1:
            self.index += 1
        await self.update(interaction)
# ---------------- PREFIX COMMANDS ----------------
@bot.command()
async def lock(ctx):
    """Lock the current channel"""
    await lock_channel(ctx.channel)
    await ctx.send("🔒 Channel locked", view=UnlockView(ctx.channel))

@bot.command()
async def unlock(ctx):
    """Unlock the current channel"""
    await unlock_channel(ctx.channel, ctx.author)

@bot.command()
async def locked(ctx):
    """Show locked channels with pagination if >25"""
    if not lock_timers:
        return await ctx.send("🔓 No channels are locked.")

    # Get locked channels as a list of tuples (channel_id, unlock_time)
    channels_list = list(lock_timers.items())  # dict items are fine, no coroutine

    pages = []
    # Discord embeds support max 25 fields per embed
    for i in range(0, len(channels_list), 25):
        embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
        chunk = channels_list[i:i + 25]
        for cid, end in chunk:
            ch = bot.get_channel(cid)
            if not ch:
                continue
            mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
            embed.add_field(name=ch.name, value=f"{ch.mention}\nUnlocks in {mins} min", inline=False)
        pages.append(embed)

    if len(pages) == 1:
        await ctx.send(embed=pages[0])
    else:
        view = LockedPaginator(pages)
        await ctx.send(embed=pages[0], view=view)

@bot.command()
async def check_timer(ctx):
    """Check remaining lock time for current channel"""
    if ctx.channel.id in lock_timers:
        mins = int((lock_timers[ctx.channel.id] - datetime.now()).total_seconds() // 60)
        await ctx.send(f"Unlocks in {mins} minutes")
    else:
        await ctx.send("Channel not locked")

@bot.command()
async def owner(ctx):
    await ctx.send("Made by Buddy, maybe say thanks!")

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

# ---------------- SLASH COMMANDS ----------------
@bot.tree.command(name="locked", description="Show all locked channels with pagination")
async def slash_locked(interaction: discord.Interaction):
    """Show locked channels with pagination for slash command"""
    if not lock_timers:
        return await interaction.response.send_message("🔓 No channels are locked.", ephemeral=True)

    channels_list = list(lock_timers.items())  # safe list of tuples (channel_id, unlock_time)
    pages = []

    for i in range(0, len(channels_list), 25):
        embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
        chunk = channels_list[i:i + 25]
        for cid, end in chunk:
            ch = bot.get_channel(cid)
            if not ch:
                continue
            mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
            embed.add_field(name=ch.name, value=f"{ch.mention}\nUnlocks in {mins} min", inline=False)
        pages.append(embed)

    if len(pages) == 1:
        await interaction.response.send_message(embed=pages[0], ephemeral=True)
    else:
        view = LockedPaginator(pages)
        await interaction.response.send_message(embed=pages[0], view=view, ephemeral=True)
# ---------------- OWNER-ONLY SLASH ----------------
@bot.tree.command(name="servers", description="List all servers the bot is in")
async def slash_servers(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
    lines = [f"{guild.name} (ID: {guild.id})" for guild in bot.guilds]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@bot.tree.command(name="shutdown", description="Shutdown the bot (owner only)")
async def slash_shutdown(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Only the owner can use this.", ephemeral=True)
    await interaction.response.send_message("Shutting down...", ephemeral=True)
    await bot.close()

# ---------------- HELP COMMAND ----------------
@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())
    cmds = {
        ".help": "Show this menu",
        ".lock": "Lock channel",
        ".unlock": "Unlock channel",
        ".locked": "List locked channels",
        ".blacklist": "Manage blacklists",
        ".check_timer": "Check lock timer",
        ".owner": "Bot creator",
    }
    for c, d in cmds.items():
        embed.add_field(name=c, value=d, inline=False)
    await ctx.send(embed=embed)
# ---------------- ADDITIONAL SLASH COMMANDS ----------------
@bot.tree.command(name="lock", description="Lock this channel")
async def slash_lock(interaction: discord.Interaction):
    await lock_channel(interaction.channel)
    await interaction.response.send_message("🔒 Channel locked", ephemeral=True)

@bot.tree.command(name="unlock", description="Unlock this channel")
async def slash_unlock(interaction: discord.Interaction):
    await unlock_channel(interaction.channel, interaction.user)
    await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)

@bot.tree.command(name="check_timer", description="Check lock timer for this channel")
async def slash_check_timer(interaction: discord.Interaction):
    if interaction.channel.id in lock_timers:
        mins = int((lock_timers[interaction.channel.id] - datetime.now()).total_seconds() // 60)
        await interaction.response.send_message(f"Unlocks in {mins} minutes", ephemeral=True)
    else:
        await interaction.response.send_message("Channel not locked", ephemeral=True)

@bot.tree.command(name="help", description="Show bot help menu")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())
    cmds = {
        "/help": "Show this menu",
        "/lock": "Lock this channel",
        "/unlock": "Unlock this channel",
        "/locked": "List locked channels",
        "/check_timer": "Check lock timer",
        "/servers": "List all servers (owner only)",
        "/shutdown": "Shutdown the bot (owner only)"
    }
    for c, d in cmds.items():
        embed.add_field(name=c, value=d, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------------- ON READY ----------------
@bot.event
async def on_ready():
    logging.info(f"✅ Bot online as {bot.user}")

    # Restore memory locks
    await startup_lock_scan()

    # Scan history for old locked channels
    await startup_history_scan()

    # Start the auto-unlock task
    if not check_lock_timers.is_running():
        check_lock_timers.start()

    # Sync slash commands
    await bot.tree.sync()
    logging.info("🌐 Slash commands synced")

# ---------------- START BOT ----------------
keep_alive()
bot.run(BOT_TOKEN)
