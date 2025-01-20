import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Discord User IDs
POKETWO_ID = 716390085896962058  # Pokétwo's default ID
P2A_PREMIUM_ID = 1084324788679577650  # P2A Premium's ID

# Trigger phrases (case-insensitive)
TRIGGER_PHRASES = ["shiny hunt pings", "collection pings"]

# Blacklisted channels (stored as a set for efficiency)
blacklisted_channels = set()

# Intents setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """Called when the bot is ready."""
    print(f"Bot is online as {bot.user}")


@bot.event
async def on_message(message):
    """Detect specific messages and trigger actions."""
    # Ignore messages from the bot itself
    if message.author.bot:
        return

    # Ignore messages in blacklisted channels
    if message.channel.id in blacklisted_channels:
        return

    # Check if the message is from P2A Premium and contains trigger phrases
    if message.author.id == P2A_PREMIUM_ID and any(phrase in message.content.lower() for phrase in TRIGGER_PHRASES):
        await lock_channel(message.channel)
        await send_unlock_button(message.channel)

    # Check if Pokétwo says "these colors seem unusual..✨"
    if message.author.id == POKETWO_ID and "these colors seem unusual..✨" in message.content.lower():
        await send_congratulations_embed(message.channel)

    # Process other bot commands
    await bot.process_commands(message)


@bot.command(name="lock")
async def lock(ctx):
    """Locks the channel from Pokétwo and sends an unlock button."""
    if ctx.channel.id in blacklisted_channels:
        await ctx.send("This channel is blacklisted from using the lock command.")
        return

    guild = ctx.guild
    channel = ctx.channel
    poketwo = guild.get_member(POKETWO_ID)

    if not poketwo:
        await ctx.send("Pokétwo bot not found in this server.")
        return

    # Lock the channel for Pokétwo
    overwrite = channel.overwrites_for(poketwo)
    overwrite.view_channel = False
    overwrite.send_messages = False
    await channel.set_permissions(poketwo, overwrite=overwrite)

    # Create an embed
    embed = discord.Embed(
        title="Channel Locked",
        description="The channel has been locked for Pokétwo. Click the button below to unlock it.",
        color=discord.Color.red()
    )
    embed.set_footer(text="Use the unlock button to restore access.")

    # Send the unlock button
    class UnlockView(View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
        async def unlock(self, interaction: discord.Interaction, button: Button):
            # Ensure the user has permission to manage channels
            if interaction.user.guild_permissions.manage_channels:
                await unlock_channel(channel)
                await interaction.response.send_message("Channel unlocked!", ephemeral=True)
                self.stop()
            else:
                await interaction.response.send_message("You don't have permission to unlock this channel.", ephemeral=True)

    await ctx.send(embed=embed, view=UnlockView())


async def unlock_channel(channel):
    """Unlocks the channel by restoring permissions for Pokétwo."""
    guild = channel.guild
    poketwo = guild.get_member(POKETWO_ID)

    if not poketwo:
        print("Pokétwo bot not found in this server.")
        return

    # Restore default permissions for Pokétwo
    await channel.set_permissions(poketwo, overwrite=None)
    print(f"Unlocked channel: {channel.name}")
    await channel.send("The channel has been unlocked!")


@bot.command(name="blacklist")
async def blacklist(ctx, action: str = None):
    """Manages the blacklist of channels."""
    channel_id = ctx.channel.id

    if action == "add":
        blacklisted_channels.add(channel_id)
        await ctx.send(f"Channel **{ctx.channel.name}** has been added to the blacklist.")
    elif action == "remove":
        blacklisted_channels.discard(channel_id)
        await ctx.send(f"Channel **{ctx.channel.name}** has been removed from the blacklist.")
    elif action == "list":
        if not blacklisted_channels:
            await ctx.send("No channels are currently blacklisted.")
        else:
            channel_list = "\n".join([f"<#{ch_id}>" for ch_id in blacklisted_channels])
            await ctx.send(f"Blacklisted Channels:\n{channel_list}")
    else:
        await ctx.send("Invalid action! Use `!blacklist add`, `!blacklist remove`, or `!blacklist list`.")


async def send_congratulations_embed(channel):
    """Sends a congratulations embed when Pokétwo says 'these colors seem unusual..✨'."""
    embed = discord.Embed(
        title="Congratulations!",
        description="You've encountered something extraordinary! 🎉",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Keep up the amazing hunt!")
    await channel.send(embed=embed)


@bot.command(name="ping")
async def ping(ctx):
    """Responds with Pong!"""
    await ctx.send("Pong!")


@bot.command(name="owner")
async def owner(ctx):
    """Responds with the owner information."""
    await ctx.send("This bot is owned by **Cloud**. All rights reserved!")


# Run the bot
bot.run(BOT_TOKEN)
