import discord
from discord.ext import commands

# Bot setup
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True  # Required for reading message content
bot = commands.Bot(command_prefix="!", intents=intents)

# Keywords to trigger channel locking
KEYWORDS = ["shiny hunt", "collection", "rare ping"]

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}.")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if the message is from any bot
    if message.author.bot:
        # Check for keywords in the message content
        if any(keyword in message.content.lower() for keyword in KEYWORDS):
            # Lock the channel
            await lock_channel(message.channel)
            await message.channel.send("Channel locked due to detected bot activity.")
    await bot.process_commands(message)  # Ensure commands still work

async def lock_channel(channel):
    """Lock the channel by disabling send messages for all bots."""
    for member in channel.members:
        if member.bot:  # Check if the member is a bot
            overwrite = channel.overwrites_for(member)
            overwrite.send_messages = False  # Disable sending messages
            await channel.set_permissions(member, overwrite=overwrite)
    print(f"Locked {channel.name} for all bots.")

async def unlock_channel(channel):
    """Unlock the channel by enabling send messages for all bots."""
    for member in channel.members:
        if member.bot:  # Check if the member is a bot
            overwrite = channel.overwrites_for(member)
            overwrite.send_messages = None  # Reset permission to default
            await channel.set_permissions(member, overwrite=overwrite)
    print(f"Unlocked {channel.name} for all bots.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Manually lock the channel for all bots."""
    await lock_channel(ctx.channel)
    await ctx.send("Locked this channel for all bots.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Manually unlock the channel for all bots."""
    await unlock_channel(ctx.channel)
    await ctx.send("Unlocked this channel for all bots.")

# Run the bot
bot.run("YOUR_DISCORD_BOT_TOKEN")
