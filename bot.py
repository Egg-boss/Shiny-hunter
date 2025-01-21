import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import random

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

POKETWO_ID = 716390085896962058  # Replace with Pokétwo's actual User ID

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

# Channel blacklist and log channel ID
blacklisted_channels = set()
log_channel_id = None


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check for messages from Pokétwo and "These colors seem unusual... ✨"
    if message.author.bot and str(message.author) == "Pokétwo#8236":
        if "These colors seem unusual... ✨" in message.content:
            embed = discord.Embed(
                title="🎉 Congratulations! 🎉",
                description=f"{message.author.mention} has found a shiny Pokémon!",
                color=discord.Color.gold(),
            )
            embed.set_footer(text="Keep hunting for more rare Pokémon!")
            await message.channel.send(embed=embed)

    # Keyword detection logic
    if message.author.bot:
        active_keywords = [k for k, v in KEYWORDS.items() if v]
        if any(keyword in message.content.lower() for keyword in active_keywords):
            if message.channel.id not in blacklisted_channels:
                await lock_channel(message.channel)
                embed = discord.Embed(
                    title="Channel Locked",
                    description="This channel has been locked due to specific keywords being detected.",
                    color=discord.Color.red(),
                )
                embed.set_footer(text="Use the unlock command or button to restore access.")
                view = UnlockView(channel=message.channel)
                await message.channel.send(embed=embed, view=view)
                await log_event(message.guild, f"🔒 Channel locked: {message.channel.name} due to keyword detection.")

    # Process commands after handling custom logic
    await bot.process_commands(message)


@bot.command(name="help")
async def help_command(ctx):
    """Custom help command to display all available commands."""
    embed = discord.Embed(
        title="Bot Commands",
        description="Here are the available commands:",
        color=discord.Color.blue(),
    )
    embed.add_field(name=".help", value="Displays this help message.", inline=False)
    embed.add_field(name=".add_keyword <keyword>", value="Add a new keyword to monitor.", inline=False)
    embed.add_field(name=".remove_keyword <keyword>", value="Remove an existing keyword.", inline=False)
    embed.add_field(name=".toggle_keyword <keyword>", value="Enable/disable keyword detection.", inline=False)
    embed.add_field(name=".list_keywords", value="List the statuses of all keywords.", inline=False)
    embed.add_field(name=".lock", value="Manually lock the current channel.", inline=False)
    embed.add_field(name=".unlock", value="Manually unlock the current channel.", inline=False)
    embed.add_field(name=".blacklist <add/remove/list> [channel]", value="Manage blacklisted channels.", inline=False)
    embed.add_field(name=".log_channel <set/unset>", value="Set or unset the log channel.", inline=False)
    embed.add_field(name=".joke", value="Sends a random joke.", inline=False)
    embed.add_field(name=".8ball <question>", value="Ask the magic 8-ball a question.", inline=False)
    embed.add_field(name=".inspire", value="Sends a motivational quote.", inline=False)

    await ctx.send(embed=embed)


@bot.command(name="add_keyword")
async def add_keyword(ctx, *, keyword: str):
    """Adds a new keyword to the monitoring list."""
    if keyword in KEYWORDS:
        await ctx.send(f"The keyword `{keyword}` is already in the list.")
    else:
        KEYWORDS[keyword] = True
        await ctx.send(f"The keyword `{keyword}` has been added and is now active.")


@bot.command(name="remove_keyword")
async def remove_keyword(ctx, *, keyword: str):
    """Removes a keyword from the monitoring list."""
    if keyword in KEYWORDS:
        del KEYWORDS[keyword]
        await ctx.send(f"The keyword `{keyword}` has been removed from the list.")
    else:
        await ctx.send(f"The keyword `{keyword}` was not found in the list.")


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock_command(ctx):
    """Manually locks the current channel."""
    await lock_channel(ctx.channel)
    await ctx.send(f"🔒 The channel `{ctx.channel.name}` has been locked.")


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock_command(ctx):
    """Manually unlocks the current channel."""
    await unlock_channel(ctx.channel)
    await ctx.send(f"🔓 The channel `{ctx.channel.name}` has been unlocked.")


# Lock/Unlock Helpers
async def lock_channel(channel):
    overwrite = channel.overwrites_for(channel.guild.default_role)
    overwrite.send_messages = False
    await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)


async def unlock_channel(channel):
    overwrite = channel.overwrites_for(channel.guild.default_role)
    overwrite.send_messages = None
    await channel.set_permissions(channel.guild.default_role, overwrite=overwrite)


# Logging
async def log_event(guild, message):
    """Logs messages to the log channel if set."""
    if log_channel_id:
        log_channel = guild.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(message)


bot.run(BOT_TOKEN)
    
