import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in the environment variables.")

POKETWO_ID = 716390085896962058  # Replace this with Pokétwo's actual User ID

# Intents setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

# Set command prefix to "."
bot = commands.Bot(command_prefix=".", intents=intents)

# Remove default help command to override it
bot.remove_command("help")

# Keywords to monitor and their toggle status
KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

# Channel blacklist
blacklisted_channels = set()
temp_locks = {}  # Track temporary locks with expiration times
lock_duration = timedelta(hours=12)  # Default lock duration (can toggle between 12 and 24 hours)


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
                "You don't have the 'unlock' role to unlock this channel.",
                ephemeral=True,
            )


@bot.event
async def on_ready():
    logging.info(f"Bot is online as {bot.user}")
    check_temp_locks.start()


@bot.event
async def on_message(message):
    try:
        if message.author == bot.user:
            return

        if message.author.bot and str(message.author) == "Pokétwo#8236":
            if "These colors seem unusual... ✨" in message.content:
                embed = discord.Embed(
                    title="🎉 Congratulations! 🎉",
                    description=f"{message.author.mention} has found a shiny Pokémon!",
                    color=discord.Color.gold(),
                )
                embed.set_footer(text="Keep hunting for more rare Pokémon!")
                await message.channel.send(embed=embed)

        if message.author.bot and message.content:
            active_keywords = [k for k, v in KEYWORDS.items() if v]
            if any(keyword in message.content.lower() for keyword in active_keywords):
                if message.channel.id not in blacklisted_channels:
                    unlock_time = datetime.utcnow() + lock_duration
                    temp_locks[message.channel.id] = unlock_time
                    await lock_channel(message.channel, unlock_time)

        await bot.process_commands(message)
    except Exception as e:
        logging.error(f"Error in on_message: {e}")


@bot.command(name="toggle_lock_duration")
@commands.has_permissions(manage_channels=True)
async def toggle_lock_duration(ctx):
    global lock_duration
    if lock_duration == timedelta(hours=12):
        lock_duration = timedelta(hours=24)
        await ctx.send("Lock duration has been set to 24 hours.")
    else:
        lock_duration = timedelta(hours=12)
        await ctx.send("Lock duration has been set to 12 hours.")


@tasks.loop(minutes=1)
async def check_temp_locks():
    now = datetime.utcnow()
    for channel_id, unlock_time in list(temp_locks.items()):
        if now >= unlock_time:
            temp_locks.pop(channel_id)
            channel = bot.get_channel(channel_id)
            if channel:
                await unlock_channel(channel, bot.user)


@bot.command(name="unlock")
async def unlock(ctx):
    unlock_role = discord.utils.get(ctx.guild.roles, name="unlock")

    if unlock_role in ctx.author.roles or ctx.author.guild_permissions.manage_channels:
        await unlock_channel(ctx.channel, ctx.author)
    else:
        await ctx.send(
            "You don't have the required permissions or the 'unlock' role to unlock this channel."
        )


@bot.command(name="del")
@commands.has_permissions(manage_channels=True)
async def delete_channel(ctx):
    await ctx.channel.delete()


@bot.command(name="move")
@commands.has_permissions(manage_channels=True)
async def move_channel(ctx, *, category_name: str):
    category = discord.utils.get(ctx.guild.categories, name=category_name)
    if category:
        await ctx.channel.edit(category=category)
        await ctx.send(f"Channel moved to category: {category.name}")
    else:
        await ctx.send(f"Category '{category_name}' not found.")


@bot.command(name="clone")
@commands.has_permissions(manage_channels=True)
async def clone_channel(ctx):
    cloned_channel = await ctx.channel.clone()
    await ctx.send(f"Channel cloned successfully. New channel: {cloned_channel.mention}")


@bot.command(name="owner")
async def bot_owner(ctx):
    embed = discord.Embed(
        title="Bot Creator",
        description="This bot was made by 💨 Suk Ballz",
        color=discord.Color.purple(),
    )
    await ctx.send(embed=embed)


async def lock_channel(channel, unlock_time):
    await set_channel_permissions(channel, view_channel=False, send_messages=False)
    time_remaining = (unlock_time - datetime.utcnow()).total_seconds()
    hours, remainder = divmod(time_remaining, 3600)
    minutes, _ = divmod(remainder, 60)

    embed = discord.Embed(
        title="Channel Locked",
        description=(
            f"This channel has been locked due to specific keywords being detected.\n"
            f"The channel will automatically unlock in {int(hours)} hours and {int(minutes)} minutes."
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text="Use the unlock command or button to restore access. If the button fails, use `.unlock`.")
    view = UnlockView(channel=channel)
    await channel.send(embed=embed, view=view)


async def unlock_channel(channel, user):
    await set_channel_permissions(channel, view_channel=None, send_messages=None)
    embed = discord.Embed(
        title="Channel Unlocked",
        description=f"Happy hunting, {user.mention}! Let's see some unusual colors... ✨",
        color=discord.Color.green(),
    )
    embed.set_footer(text="You can lock the channel again using the lock command.")
    await channel.send(embed=embed)


async def set_channel_permissions(channel, view_channel=None, send_messages=None):
    guild = channel.guild
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        logging.warning("Pokétwo bot not found in this server.")
        return

    overwrite = channel.overwrites_for(poketwo)

    if view_channel is not None:
        overwrite.view_channel = view_channel
    else:
        overwrite.view_channel = True

    if send_messages is not None:
        overwrite.send_messages = send_messages
    else:
        overwrite.send_messages = True

    await channel.set_permissions(poketwo, overwrite=overwrite)


bot.run(BOT_TOKEN)
                          
