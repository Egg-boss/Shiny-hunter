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

# Lock duration settings
lock_duration = 12  # Default lock duration in hours

# Keywords to monitor and their toggle status
KEYWORDS = {
    "shiny hunt pings": True,
    "collection pings": True,
    "rare ping": True,
}

# Channel blacklist
blacklisted_channels = set()

# Lock countdown tasks
lock_timers = {}


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
                "You don't have the 'unlock' role to unlock this channel. Use `.unlock` instead.",
                ephemeral=True,
            )


@bot.event
async def on_ready():
    logging.info(f"Bot is online as {bot.user}")


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
                    await lock_channel(message.channel)
                    embed = discord.Embed(
                        title="Channel Locked",
                        description=(
                            f"This channel has been locked for {lock_duration} hours due to specific keywords being detected."
                        ),
                        color=discord.Color.red(),
                    )
                    embed.set_footer(text="Use the unlock button or `.unlock` to restore access.")
                    view = UnlockView(channel=message.channel)
                    await message.channel.send(embed=embed, view=view)

        await bot.process_commands(message)
    except Exception as e:
        logging.error(f"Error in on_message: {e}")


async def lock_channel(channel):
    await set_channel_permissions(channel, view_channel=False, send_messages=False)
    end_time = datetime.now() + timedelta(hours=lock_duration)
    lock_timers[channel.id] = end_time


async def unlock_channel(channel, user):
    await set_channel_permissions(channel, view_channel=None, send_messages=None)
    lock_timers.pop(channel.id, None)
    embed = discord.Embed(
        title="Channel Unlocked",
        description=f"The channel has been unlocked by {user.mention}. Happy hunting, let's see some unusual colors... ✨",
        color=discord.Color.green(),
    )
    await channel.send(embed=embed)


async def set_channel_permissions(channel, view_channel=None, send_messages=None):
    guild = channel.guild
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        logging.warning("Pokétwo bot not found in this server.")
        return

    overwrite = channel.overwrites_for(poketwo)
    overwrite.view_channel = view_channel if view_channel is not None else True
    overwrite.send_messages = send_messages if send_messages is not None else True
    await channel.set_permissions(poketwo, overwrite=overwrite)


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Bot Commands",
        description="Here are the available commands:",
        color=discord.Color.blue(),
    )
    commands_list = {
        ".help": "Displays this help message.",
        ".toggle_keyword <keyword>": "Enable/disable keyword detection.",
        ".list_keywords": "List the statuses of all keywords.",
        ".lock": "Manually lock the current channel.",
        ".unlock": "Manually unlock the current channel.",
        ".del": "Delete the current channel.",
        ".move <category>": "Move the current channel to a new category.",
        ".clone": "Clone the current channel.",
        ".toggle_lock_duration": "Toggle between 12-hour and 24-hour lock durations.",
        ".owner": "Displays the bot's creator.",
    }
    for command, description in commands_list.items():
        embed.add_field(name=command, value=description, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="toggle_lock_duration")
@commands.has_permissions(manage_channels=True)
async def toggle_lock_duration(ctx):
    global lock_duration
    lock_duration = 24 if lock_duration == 12 else 12
    await ctx.send(f"Lock duration toggled to {lock_duration} hours.")


@bot.command(name="owner")
async def bot_owner(ctx):
    embed = discord.Embed(
        title="Bot Creator",
        description="This bot was made by 💨 Suk Ballz",
        color=discord.Color.purple(),
    )
    await ctx.send(embed=embed)


@bot.command(name="del")
@commands.has_permissions(manage_channels=True)
async def delete_channel(ctx):
    await ctx.channel.delete()


@bot.command(name="move")
@commands.has_permissions(manage_channels=True)
async def move_channel(ctx, *, category_name: str):
    category = discord.utils.get(ctx.guild.categories, name=category_name)
    if not category:
        await ctx.send(f"Category `{category_name}` not found.")
        return
    await ctx.channel.edit(category=category)
    await ctx.send(f"Channel moved to `{category_name}`.")


@bot.command(name="clone")
@commands.has_permissions(manage_channels=True)
async def clone_channel(ctx):
    cloned_channel = await ctx.channel.clone()
    await cloned_channel.edit(position=ctx.channel.position + 1)
    await ctx.send("Channel cloned successfully.")


bot.run(BOT_TOKEN)
    
