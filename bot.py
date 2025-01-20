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
TRIGGER_PHRASES = ["shiny hunt ping", "rare ping", "collection ping"]

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
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")


@bot.event
async def on_message(message):
    """Detect specific pings from P2A Premium and lock the channel."""
    # Ignore messages from the bot itself
    if message.author.bot:
        return

    # Check if the message is from P2A Premium and contains trigger phrases
    if message.author.id == P2A_PREMIUM_ID and any(phrase in message.content.lower() for phrase in TRIGGER_PHRASES):
        await lock_channel(message.channel)
        await send_unlock_button(message.channel)

    # Process other commands
    await bot.process_commands(message)


@bot.command(name="ping")
async def ping(ctx):
    """Responds with Pong!"""
    await ctx.send("Pong!")


async def lock_channel(channel):
    """Locks the channel by denying permissions for Pokétwo."""
    guild = channel.guild
    poketwo = guild.get_member(POKETWO_ID)

    if poketwo:
        # Modify channel permissions for Pokétwo
        overwrite = channel.overwrites_for(poketwo)
        overwrite.view_channel = False
        overwrite.send_messages = False
        await channel.set_permissions(poketwo, overwrite=overwrite)
        print(f"Locked channel: {channel.name}")
        await channel.send(f"The channel has been locked to prevent Pokétwo from accessing it.")
    else:
        print("Pokétwo bot not found in this server.")


async def send_unlock_button(channel):
    """Sends an unlock button in the channel."""
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

    await channel.send("Click the button below to unlock the channel.", view=UnlockView())


async def unlock_channel(channel):
    """Unlocks the channel by restoring permissions for Pokétwo."""
    guild = channel.guild
    poketwo = guild.get_member(POKETWO_ID)

    if poketwo:
        # Reset the channel's permission overrides for Pokétwo
        await channel.set_permissions(poketwo, overwrite=None)
        print(f"Unlocked channel: {channel.name}")
        await channel.send("The channel has been unlocked.")
    else:
        print("Pokétwo bot not found in this server.")


# Run the bot
bot.run(BOT_TOKEN)
