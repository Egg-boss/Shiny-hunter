import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button
import os, sqlite3, logging, threading
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask

# ================= ENV =================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", 0))
POKETWO_ID = 716390085896962058

if not BOT_TOKEN or not OWNER_ID:
    raise RuntimeError("Missing BOT_TOKEN or OWNER_ID")

# ================= LOGGING =================
logging.basicConfig(level=logging.INFO)

# ================= KEEP ALIVE =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot alive"

def keep_alive():
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=8080),
        daemon=True
    ).start()

# ================= DISCORD =================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ================= DATABASE =================
def db():
    con = sqlite3.connect("bot.db")
    con.row_factory = sqlite3.Row
    return con

def init_db():
    d = db()
    d.execute("CREATE TABLE IF NOT EXISTS locks (channel_id INTEGER UNIQUE, unlock_at TEXT)")
    d.execute("CREATE TABLE IF NOT EXISTS blacklisted_channels (guild_id INTEGER, channel_id INTEGER UNIQUE)")
    d.execute("CREATE TABLE IF NOT EXISTS blacklisted_categories (guild_id INTEGER, category_id INTEGER UNIQUE)")
    d.execute("""
        CREATE TABLE IF NOT EXISTS server_config (
            guild_id INTEGER UNIQUE,
            lock_hours INTEGER DEFAULT 12,
            keywords_enabled INTEGER DEFAULT 1
        )
    """)
    d.commit()
    d.close()

init_db()

# ================= STATE =================
lock_timers = {}
blacklisted_channels = set()
blacklisted_categories = set()

KEYWORDS = ["shiny hunt pings", "collection pings", "rare ping"]

# ================= CONFIG =================
def get_config(gid):
    d = db()
    row = d.execute("SELECT * FROM server_config WHERE guild_id=?", (gid,)).fetchone()
    if not row:
        d.execute("INSERT INTO server_config VALUES (?,?,?)", (gid, 12, 1))
        d.commit()
        row = d.execute("SELECT * FROM server_config WHERE guild_id=?", (gid,)).fetchone()
    d.close()
    return row

# ================= LOAD STATE =================
def load_state():
    d = db()
    now = datetime.now()

    for r in d.execute("SELECT * FROM locks"):
        end = datetime.fromisoformat(r["unlock_at"])
        if end > now:
            lock_timers[r["channel_id"]] = end

    blacklisted_channels.update(x["channel_id"] for x in d.execute("SELECT channel_id FROM blacklisted_channels"))
    blacklisted_categories.update(x["category_id"] for x in d.execute("SELECT category_id FROM blacklisted_categories"))
    d.close()

# ================= PERMISSIONS =================
async def set_permissions(channel, lock: bool):
    try:
        member = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return

    if lock:
        await channel.set_permissions(member, view_channel=False, send_messages=False)
    else:
        await channel.set_permissions(member, overwrite=None)

# ================= STARTUP SCAN =================
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

        await set_permissions(channel, True)
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

                    # Stop if unlocked found
                    if "🔓 Channel Unlocked" in title:
                        break

                    # Restore lock if found first
                    if "🔒 Channel Locked" in title:
                        await lock_channel(channel)
                        logging.info(f"🔒 Restored lock from history: #{channel.name}")
                        break
            except Exception as e:
                logging.warning(f"Failed scanning #{channel.name}: {e}")
                continue

# ================= LOCK CORE =================
async def lock_channel(channel):
    if channel.id in lock_timers:
        return

    cfg = get_config(channel.guild.id)
    end = datetime.now() + timedelta(hours=cfg["lock_hours"])
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
            color=discord.Color.green()
        )
    )

# ================= UNLOCK BUTTON =================
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock(self, interaction: discord.Interaction, _):
        await unlock_channel(self.channel, interaction.user)
        await interaction.response.send_message("Unlocked.", ephemeral=True)

# ================= EVENTS =================
@bot.event
async def on_ready():
    global blacklisted_channels, blacklisted_categories
    blacklisted_channels, blacklisted_categories = load_blacklists()
    logging.info(f"Bot online as {bot.user}")

    # Restore any locks already in lock_timers (DB / memory)
    await startup_lock_scan()

    # Scan channel history to catch old locked channels not in DB
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
            await msg.channel.send(
                embed=discord.Embed(title="🔒 Channel Locked", color=discord.Color.red()),
                view=UnlockView(msg.channel)
            )

    await bot.process_commands(msg)
@bot.command()
@commands.has_permissions(manage_guild=True)
async def setlockhours(ctx, hours: int):
    if hours < 1 or hours > 72:
        return await ctx.send("Lock hours must be between 1 and 72")

    d = db()
    d.execute(
        "INSERT OR REPLACE INTO server_config (guild_id, lock_hours, keywords_enabled) "
        "VALUES (?, ?, COALESCE((SELECT keywords_enabled FROM server_config WHERE guild_id=?),1))",
        (ctx.guild.id, hours, ctx.guild.id)
    )
    d.commit(); d.close()

    await ctx.send(f"🔧 Lock duration set to **{hours} hours**")
@bot.command()
@commands.has_permissions(manage_guild=True)
async def keywords(ctx, state: str):
    state = state.lower()
    if state not in ("on", "off"):
        return await ctx.send("Use: `.keywords on` or `.keywords off`")

    enabled = 1 if state == "on" else 0

    d = db()
    d.execute(
        "INSERT OR REPLACE INTO server_config (guild_id, lock_hours, keywords_enabled) "
        "VALUES (?, COALESCE((SELECT lock_hours FROM server_config WHERE guild_id=?),12), ?)",
        (ctx.guild.id, ctx.guild.id, enabled)
    )
    d.commit(); d.close()

    await ctx.send(f"🔑 Keyword detection **{state.upper()}**")
@bot.command()
async def config(ctx):
    cfg = get_config(ctx.guild.id)

    embed = discord.Embed(title="Server Config", color=discord.Color.blue())
    embed.add_field(name="Lock Hours", value=cfg["lock_hours"], inline=False)
    embed.add_field(
        name="Keywords",
        value="ON" if cfg["keywords_enabled"] else "OFF",
        inline=False
    )

    await ctx.send(embed=embed)
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

# ================= AUTO UNLOCK =================
@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()
    for cid, end in list(lock_timers.items()):
        if now >= end:
            ch = bot.get_channel(cid)
            if ch:
                await unlock_channel(ch, bot.user)
# ================= HELP =================
@bot.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())

    embed.add_field(name=".lock", value="Lock current channel", inline=False)
    embed.add_field(name=".unlock", value="Unlock current channel", inline=False)
    embed.add_field(name=".locked", value="List locked channels", inline=False)
    embed.add_field(name=".blacklist", value="Manage blacklists", inline=False)
    embed.add_field(name=".servers", value="(Owner) List servers", inline=False)
    embed.add_field(name=".leave <server_id>", value="(Owner) Leave server", inline=False)
    embed.add_field(name=".owner", value="Bot creator", inline=False)

    embed.set_footer(text="Slash commands are also available")
    await ctx.send(embed=embed)

# ================= OWNER =================
@bot.command()
async def owner(ctx):
    await ctx.send("Made by Buddy — say thanks 😄")

def is_owner(interaction_or_ctx):
    uid = interaction_or_ctx.user.id if isinstance(interaction_or_ctx, discord.Interaction) else interaction_or_ctx.author.id
    return uid == OWNER_ID

# ================= LOCK / UNLOCK =================
@bot.command()
async def lock(ctx):
    await lock_channel(ctx.channel)
    await ctx.send("🔒 Channel locked", view=UnlockView(ctx.channel))

@bot.command()
async def unlock(ctx):
    await unlock_channel(ctx.channel, ctx.author)

# ================= LOCKED LIST (CHUNKED) =================
@bot.command()
async def locked(ctx):
    if not lock_timers:
        return await ctx.send("🔓 No channels are locked.")

    items = list(lock_timers.items())
    chunks = [items[i:i + 25] for i in range(0, len(items), 25)]

    for idx, chunk in enumerate(chunks, start=1):
        embed = discord.Embed(
            title=f"🔒 Locked Channels ({idx}/{len(chunks)})",
            color=discord.Color.red()
        )

        for cid, end in chunk:
            ch = bot.get_channel(cid)
            if not ch:
                continue
            mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
            embed.add_field(
                name=ch.name,
                value=f"{ch.mention} • {mins} min",
                inline=False
            )

        await ctx.send(embed=embed)

# ================= BLACKLIST =================
@bot.group(invoke_without_command=True)
async def blacklist(ctx):
    await ctx.send(
        "**Blacklist Commands**\n"
        ".blacklist add #channel\n"
        ".blacklist remove #channel\n"
        ".blacklist addcategory <name>\n"
        ".blacklist removecategory <name>\n"
        ".blacklist list"
    )

@blacklist.command()
async def add(ctx, channel: discord.TextChannel):
    blacklisted_channels.add(channel.id)
    d = db()
    d.execute("INSERT OR IGNORE INTO blacklisted_channels VALUES (?,?)", (ctx.guild.id, channel.id))
    d.commit(); d.close()
    await ctx.send(f"{channel.mention} blacklisted")

@blacklist.command()
async def remove(ctx, channel: discord.TextChannel):
    blacklisted_channels.discard(channel.id)
    d = db()
    d.execute("DELETE FROM blacklisted_channels WHERE channel_id=?", (channel.id,))
    d.commit(); d.close()
    await ctx.send(f"{channel.mention} removed")

@blacklist.command()
async def addcategory(ctx, *, name):
    cat = discord.utils.get(ctx.guild.categories, name=name)
    if not cat:
        return await ctx.send("Category not found")

    blacklisted_categories.add(cat.id)
    d = db()
    d.execute("INSERT OR IGNORE INTO blacklisted_categories VALUES (?,?)", (ctx.guild.id, cat.id))
    d.commit(); d.close()
    await ctx.send(f"Category **{cat.name}** blacklisted")

@blacklist.command()
async def removecategory(ctx, *, name):
    cat = discord.utils.get(ctx.guild.categories, name=name)
    if not cat:
        return await ctx.send("Category not found")

    blacklisted_categories.discard(cat.id)
    d = db()
    d.execute("DELETE FROM blacklisted_categories WHERE category_id=?", (cat.id,))
    d.commit(); d.close()
    await ctx.send(f"Category **{cat.name}** removed")

@blacklist.command(name="list")
async def blacklist_list(ctx):
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

# ================= OWNER: SERVER LIST =================
@bot.command()
async def servers(ctx):
    if ctx.author.id != OWNER_ID:
        return

    embed = discord.Embed(title="Servers", color=discord.Color.gold())
    for g in bot.guilds:
        embed.add_field(name=g.name, value=f"ID: {g.id}", inline=False)

    await ctx.send(embed=embed)

# ================= OWNER: LEAVE SERVER =================
@bot.command()
async def leave(ctx, server_id: int):
    if ctx.author.id != OWNER_ID:
        return

    guild = bot.get_guild(server_id)
    if not guild:
        return await ctx.send("Server not found")

    await guild.leave()
    await ctx.send(f"Left **{guild.name}**")

# ================= SLASH COMMANDS =================
@bot.tree.command(name="lock")
async def slash_lock(interaction: discord.Interaction):
    await lock_channel(interaction.channel)
    await interaction.response.send_message("🔒 Channel locked", ephemeral=True)

@bot.tree.command(name="unlock")
async def slash_unlock(interaction: discord.Interaction):
    await unlock_channel(interaction.channel, interaction.user)
    await interaction.response.send_message("🔓 Channel unlocked", ephemeral=True)

@bot.tree.command(name="locked")
async def slash_locked(interaction: discord.Interaction):
    if not lock_timers:
        return await interaction.response.send_message("No locked channels", ephemeral=True)

    embed = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
    for cid, end in list(lock_timers.items())[:25]:
        ch = bot.get_channel(cid)
        if ch:
            mins = max(int((end - datetime.now()).total_seconds() // 60), 0)
            embed.add_field(name=ch.name, value=f"{mins} min", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="servers")
async def slash_servers(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("Owner only", ephemeral=True)

    embed = discord.Embed(title="Servers", color=discord.Color.gold())
    for g in bot.guilds:
        embed.add_field(name=g.name, value=str(g.id), inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)
@bot.tree.command(name="setlockhours")
@app_commands.describe(hours="Lock duration in hours (1–72)")
async def slash_setlockhours(interaction: discord.Interaction, hours: int):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("Missing permission", ephemeral=True)

    if hours < 1 or hours > 72:
        return await interaction.response.send_message("1–72 only", ephemeral=True)

    d = db()
    d.execute(
        "INSERT OR REPLACE INTO server_config (guild_id, lock_hours, keywords_enabled) "
        "VALUES (?, ?, COALESCE((SELECT keywords_enabled FROM server_config WHERE guild_id=?),1))",
        (interaction.guild.id, hours, interaction.guild.id)
    )
    d.commit(); d.close()

    await interaction.response.send_message(f"Lock duration set to {hours} hours", ephemeral=True)
@bot.tree.command(name="keywords")
@app_commands.describe(state="on or off")
async def slash_keywords(interaction: discord.Interaction, state: str):
    if not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("Missing permission", ephemeral=True)

    if state not in ("on", "off"):
        return await interaction.response.send_message("Use on/off", ephemeral=True)

    enabled = 1 if state == "on" else 0

    d = db()
    d.execute(
        "INSERT OR REPLACE INTO server_config (guild_id, lock_hours, keywords_enabled) "
        "VALUES (?, COALESCE((SELECT lock_hours FROM server_config WHERE guild_id=?),12), ?)",
        (interaction.guild.id, interaction.guild.id, enabled)
    )
    d.commit(); d.close()

    await interaction.response.send_message(f"Keywords {state}", ephemeral=True)
@bot.tree.command(name="config")
async def slash_config(interaction: discord.Interaction):
    cfg = get_config(interaction.guild.id)

    embed = discord.Embed(title="Server Config", color=discord.Color.blue())
    embed.add_field(name="Lock Hours", value=cfg["lock_hours"], inline=False)
    embed.add_field(
        name="Keywords",
        value="ON" if cfg["keywords_enabled"] else "OFF",
        inline=False
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# ================= START =================
keep_alive()
bot.run(BOT_TOKEN)
