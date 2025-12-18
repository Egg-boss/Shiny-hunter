import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
from datetime import datetime, timedelta
import os
import logging
from flask import Flask
import threading

# ================= KEEP ALIVE =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Alive"

def keep_alive():
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=8080),
        daemon=True
    ).start()

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
POKETWO_ID = 716390085896962058

# ================= DISCORD =================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ================= CONFIG =================
LOCK_HOURS = 12
KEYWORDS = ["shiny hunt pings", "collection pings", "rare ping"]

lock_timers: dict[int, datetime] = {}
blacklisted_channels = set()
blacklisted_categories = set()

# ================= PERMISSIONS =================
async def set_channel_permissions(channel, lock: bool):
    try:
        poketwo = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return

    ow = channel.overwrites_for(poketwo)
    ow.send_messages = not lock
    ow.view_channel = True
    await channel.set_permissions(poketwo, overwrite=ow)

# ================= LOCK CORE =================
async def lock_channel(channel):
    if channel.id in lock_timers:
        return
    await set_channel_permissions(channel, True)
    lock_timers[channel.id] = datetime.now() + timedelta(hours=LOCK_HOURS)

async def unlock_channel(channel, user=None):
    if channel.id not in lock_timers:
        return
    await set_channel_permissions(channel, False)
    lock_timers.pop(channel.id, None)

    embed = discord.Embed(
        title="🔓 Channel Unlocked",
        color=discord.Color.green(),
        timestamp=datetime.now()
    )
    if user:
        embed.description = f"Unlocked by {user.mention}"
    await channel.send(embed=embed)

# ================= AUTO UNLOCK =================
@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()
    expired = [
        cid for cid, end in lock_timers.items()
        if now >= end
    ]
    for cid in expired:
        ch = bot.get_channel(cid)
        if ch:
            await unlock_channel(ch)

# ================= STARTUP HISTORY SCAN =================
async def startup_history_scan():
    await bot.wait_until_ready()
    logging.info("🔎 Startup scan running")

    for guild in bot.guilds:
        for channel in guild.text_channels:
            if channel.id in blacklisted_channels:
                continue
            if channel.category and channel.category.id in blacklisted_categories:
                continue

            try:
                async for msg in channel.history(limit=25):
                    if not msg.embeds:
                        continue
                    title = msg.embeds[0].title or ""
                    if "🔓 Channel Unlocked" in title:
                        break
                    if "🔒 Channel Locked" in title:
                        await lock_channel(channel)
                        logging.info(f"🔒 Restored lock: #{channel.name}")
                        break
            except:
                continue
# ================= EVENTS =================
@bot.event
async def on_ready():
    await startup_history_scan()
    if not check_lock_timers.is_running():
        check_lock_timers.start()
    await bot.tree.sync()
    logging.info(f"✅ Online as {bot.user}")

@bot.event
async def on_message(msg):
    if not msg.guild or not msg.author.bot:
        await bot.process_commands(msg)
        return

    if msg.channel.id in blacklisted_channels:
        return
    if msg.channel.category and msg.channel.category.id in blacklisted_categories:
        return

    if any(k in msg.content.lower() for k in KEYWORDS):
        await lock_channel(msg.channel)
        embed = discord.Embed(
            title="🔒 Channel Locked",
            description=f"Locked for {LOCK_HOURS} hours",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        await msg.channel.send(embed=embed, view=UnlockView(msg.channel))

# ================= UNLOCK BUTTON =================
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock(self, interaction: discord.Interaction, _):
        await unlock_channel(self.channel, interaction.user)
        await interaction.response.send_message("🔓 Unlocked", ephemeral=True)

# ================= PREFIX COMMANDS =================
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
        return await ctx.send("No locked channels")

    items = list(lock_timers.items())
    for i in range(0, len(items), 25):
        embed = discord.Embed(title="🔒 Locked Channels")
        for cid, end in items[i:i+25]:
            ch = bot.get_channel(cid)
            if not ch:
                continue
            mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
            embed.add_field(
                name=ch.name,
                value=f"{ch.mention}\nUnlocks in {mins} min",
                inline=False
            )
        await ctx.send(embed=embed)

# ================= SLASH COMMANDS =================
@bot.tree.command(name="lock")
async def slash_lock(interaction: discord.Interaction):
    await lock_channel(interaction.channel)
    await interaction.response.send_message("🔒 Locked", ephemeral=True)

@bot.tree.command(name="unlock")
async def slash_unlock(interaction: discord.Interaction):
    await unlock_channel(interaction.channel, interaction.user)
    await interaction.response.send_message("🔓 Unlocked", ephemeral=True)

@bot.tree.command(name="locked")
async def slash_locked(interaction: discord.Interaction):
    if not lock_timers:
        return await interaction.response.send_message("No locked channels", ephemeral=True)

# ================= SLASH BLACKLIST =================

@bot.tree.command(name="blacklist_add", description="Blacklist a channel")
@app_commands.describe(channel="Channel to blacklist")
async def blacklist_add(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)

    blacklisted_channels.add(channel.id)
    await interaction.response.send_message(
        f"🚫 {channel.mention} blacklisted",
        ephemeral=True
    )


@bot.tree.command(name="blacklist_remove", description="Remove channel from blacklist")
@app_commands.describe(channel="Channel to unblacklist")
async def blacklist_remove(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)

    blacklisted_channels.discard(channel.id)
    await interaction.response.send_message(
        f"✅ {channel.mention} removed",
        ephemeral=True
    )


@bot.tree.command(name="blacklist_list", description="List blacklisted channels/categories")
async def blacklist_list(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)

    lines = []

    for cid in blacklisted_channels:
        ch = bot.get_channel(cid)
        if ch:
            lines.append(f"Channel: {ch.mention}")

    for cid in blacklisted_categories:
        cat = discord.utils.get(interaction.guild.categories, id=cid)
        if cat:
            lines.append(f"Category: **{cat.name}**")

    if not lines:
        return await interaction.response.send_message("No blacklists set", ephemeral=True)

    await interaction.response.send_message(
        "```" + "\n".join(lines) + "```",
        ephemeral=True
    )


# ================= SLASH OWNER =================

@bot.tree.command(name="servers", description="List servers the bot is in")
async def servers(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)

    lines = [f"{g.name} ({g.id})" for g in bot.guilds]
    msg = "\n".join(lines[:25])

    await interaction.response.send_message(
        f"```{msg}```",
        ephemeral=True
    )


@bot.tree.command(name="leave", description="Force the bot to leave a server")
@app_commands.describe(guild_id="Guild ID to leave")
async def leave(interaction: discord.Interaction, guild_id: str):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)

    guild = bot.get_guild(int(guild_id))
    if not guild:
        return await interaction.response.send_message("Guild not found", ephemeral=True)

    await guild.leave()
    await interaction.response.send_message(
        f"👋 Left **{guild.name}**",
        ephemeral=True
    )

    items = list(lock_timers.items())
    embed = discord.Embed(title="🔒 Locked Channels")
    for cid, end in items[:25]:
        ch = bot.get_channel(cid)
        if not ch:
            continue
        mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
        embed.add_field(name=ch.name, value=f"{mins} min", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= START =================
keep_alive()
bot.run(BOT_TOKEN)
