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
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ---------------- ENV ----------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set.")

POKETWO_ID = 716390085896962058

# ---------------- INTENTS ----------------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix=".", intents=intents)
bot.remove_command("help")

# ---------------- SETTINGS ----------------
lock_duration = 12

KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

blacklisted_channels = set()
blacklisted_categories = set()
lock_timers = {}

# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS blacklisted_channels (channel_id INTEGER PRIMARY KEY)")
    db.execute("CREATE TABLE IF NOT EXISTS blacklisted_categories (category_id INTEGER PRIMARY KEY)")
    db.commit()
    db.close()

def load_blacklists():
    db = get_db()
    ch = {r["channel_id"] for r in db.execute("SELECT channel_id FROM blacklisted_channels")}
    cat = {r["category_id"] for r in db.execute("SELECT category_id FROM blacklisted_categories")}
    db.close()
    return ch, cat

def add_channel_blacklist(cid):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO blacklisted_channels VALUES (?)", (cid,))
    db.commit()
    db.close()

def remove_channel_blacklist(cid):
    db = get_db()
    db.execute("DELETE FROM blacklisted_channels WHERE channel_id=?", (cid,))
    db.commit()
    db.close()

def add_category_blacklist(cid):
    db = get_db()
    db.execute("INSERT OR IGNORE INTO blacklisted_categories VALUES (?)", (cid,))
    db.commit()
    db.close()

def remove_category_blacklist(cid):
    db = get_db()
    db.execute("DELETE FROM blacklisted_categories WHERE category_id=?", (cid,))
    db.commit()
    db.close()

init_db()

# ---------------- UNLOCK VIEW ----------------
class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        unlock_role = discord.utils.get(interaction.guild.roles, name="unlock")
        if unlock_role in interaction.user.roles:
            await unlock_channel(self.channel, interaction.user)
            await interaction.response.send_message("Channel unlocked!", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message(
                "You don't have the 'unlock' role. Use `.unlock` instead.",
                ephemeral=True
            )

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    global blacklisted_channels, blacklisted_categories
    blacklisted_channels, blacklisted_categories = load_blacklists()
    if not check_lock_timers.is_running():
        check_lock_timers.start()
    logging.info(f"Bot online as {bot.user}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.author.bot and str(message.author) == "Pokétwo#8236":
        if "These colors seem unusual... ✨" in message.content:
            await message.channel.send(
                embed=discord.Embed(
                    title="🎉 Congratulations!",
                    description="A shiny Pokémon was found!",
                    color=discord.Color.gold()
                )
            )

    if message.author.bot and message.content:
        if message.channel.id not in blacklisted_channels:
            if not message.channel.category or message.channel.category.id not in blacklisted_categories:
                active = [k for k, v in KEYWORDS.items() if v]
                if any(k in message.content.lower() for k in active):
                    await lock_channel(message.channel)
                    await message.channel.send(
                        embed=discord.Embed(
                            title="🔒 Channel Locked",
                            description=f"Locked for {lock_duration} hours.",
                            color=discord.Color.red(),
                            timestamp=datetime.now()
                        ),
                        view=UnlockView(message.channel)
                    )

    await bot.process_commands(message)

# ---------------- LOCK SYSTEM ----------------
async def set_perms(channel, view=None, send=None):
    try:
        poketwo = await channel.guild.fetch_member(POKETWO_ID)
    except:
        return
    ow = channel.overwrites_for(poketwo)
    ow.view_channel = view if view is not None else True
    ow.send_messages = send if send is not None else True
    await channel.set_permissions(poketwo, overwrite=ow)

async def lock_channel(channel):
    await set_perms(channel, False, False)
    lock_timers[channel.id] = datetime.now() + timedelta(hours=lock_duration)

async def unlock_channel(channel, user):
    await set_perms(channel, None, None)
    lock_timers.pop(channel.id, None)
    await channel.send(
        embed=discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"Unlocked by {user.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
    )

@tasks.loop(seconds=60)
async def check_lock_timers():
    now = datetime.now()
    for cid, end in list(lock_timers.items()):
        if now >= end:
            ch = bot.get_channel(cid)
            if ch:
                await unlock_channel(ch, bot.user)

# ---------------- VIEW LOCKED (.vl) ----------------
class LockedView(View):
    def __init__(self, pages):
        super().__init__(timeout=120)
        self.pages = pages
        self.i = 0

    async def update(self, interaction):
        await interaction.response.edit_message(embed=self.pages[self.i], view=self)

    @discord.ui.button(label="⬅ Prev", style=discord.ButtonStyle.gray)
    async def prev(self, interaction, _):
        if self.i > 0:
            self.i -= 1
        await self.update(interaction)

    @discord.ui.button(label="Next ➡", style=discord.ButtonStyle.gray)
    async def next(self, interaction, _):
        if self.i < len(self.pages) - 1:
            self.i += 1
        await self.update(interaction)

@bot.command(name="vl")
async def view_locked(ctx):
    if not lock_timers:
        return await ctx.send("No locked channels.")
    items = list(lock_timers.items())
    pages = []
    for i in range(0, len(items), 10):
        e = discord.Embed(title="🔒 Locked Channels", color=discord.Color.red())
        for cid, end in items[i:i+10]:
            ch = bot.get_channel(cid)
            if ch:
                e.add_field(name=ch.name, value=f"Unlocks <t:{int(end.timestamp())}:R>", inline=False)
        pages.append(e)
    await ctx.send(embed=pages[0], view=LockedView(pages))

# ---------------- BLACKLIST ----------------
@bot.group(invoke_without_command=True)
@commands.has_permissions(manage_channels=True)
async def blacklist(ctx):
    await ctx.send("Use `.blacklist add/remove/list` or `.blacklist category add/remove`")

@blacklist.command()
async def add(ctx, channel: discord.TextChannel):
    blacklisted_channels.add(channel.id)
    add_channel_blacklist(channel.id)
    await ctx.send(f"{channel.mention} blacklisted.")

@blacklist.command()
async def remove(ctx, channel: discord.TextChannel):
    blacklisted_channels.discard(channel.id)
    remove_channel_blacklist(channel.id)
    await ctx.send(f"{channel.mention} removed.")

@blacklist.command()
async def list(ctx):
    if not blacklisted_channels:
        return await ctx.send("No blacklisted channels.")
    await ctx.send("\n".join(bot.get_channel(c).mention for c in blacklisted_channels if bot.get_channel(c)))

@blacklist.group()
async def category(ctx): pass

@category.command()
async def add(ctx, category: discord.CategoryChannel):
    blacklisted_categories.add(category.id)
    add_category_blacklist(category.id)
    await ctx.send(f"Category `{category.name}` blacklisted.")

@category.command()
async def remove(ctx, category: discord.CategoryChannel):
    blacklisted_categories.discard(category.id)
    remove_category_blacklist(category.id)
    await ctx.send(f"Category `{category.name}` unblacklisted.")

# ---------------- ALL ORIGINAL COMMANDS ----------------
@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())
    for c in [
        ".help",".check_timer",".toggle_keyword",".list_keywords",".lock",".unlock",
        ".rename",".move",".create",".clone",".del",".toggle_lock_duration",".vl",".blacklist"
    ]:
        embed.add_field(name=c, value="—", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def check_timer(ctx):
    if ctx.channel.id in lock_timers:
        t = lock_timers[ctx.channel.id] - datetime.now()
        await ctx.send(f"Unlocks in {t}")
    else:
        await ctx.send("Not locked.")

@bot.command()
async def list_keywords(ctx):
    await ctx.send("\n".join(f"{k}: {'ON' if v else 'OFF'}" for k,v in KEYWORDS.items()))

@bot.command()
async def toggle_keyword(ctx, *, keyword):
    if keyword in KEYWORDS:
        KEYWORDS[keyword] = not KEYWORDS[keyword]
        await ctx.send(f"{keyword} toggled.")
    else:
        await ctx.send("Invalid keyword.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def toggle_lock_duration(ctx):
    global lock_duration
    lock_duration = 24 if lock_duration == 12 else 12
    await ctx.send(f"{lock_duration}h lock duration.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def rename(ctx, *, name):
    await ctx.channel.edit(name=name)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def del_(ctx):
    await ctx.channel.delete()

@bot.command()
@commands.has_permissions(manage_channels=True)
async def move(ctx, *, category):
    cat = discord.utils.get(ctx.guild.categories, name=category)
    if cat:
        await ctx.channel.edit(category=cat)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def create(ctx, name, *, category=None):
    cat = discord.utils.get(ctx.guild.categories, name=category) if category else None
    await ctx.guild.create_text_channel(name, category=cat)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def clone(ctx):
    await ctx.channel.clone()

@bot.command()
async def owner(ctx):
    await ctx.send("💨 Suk Ballz")

# ---------------- RUN ----------------
bot.run(BOT_TOKEN)
