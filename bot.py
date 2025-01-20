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
    """Detect specific keywords or mentions in bot messages and lock the channel."""
    # Ignore messages from the bot itself
    if message.author.bot:
        # Check for specific keywords in bot messages
        keywords = ["shiny hunt pings", "collection pings", "rare ping"]
        if any(keyword in message.content.lower() for keyword in keywords):
            print(f"Keyword detected in message: {message.content}")
            await lock_channel(message.channel)
            await send_unlock_button(message.channel)
        return

    # Allow other bot commands to process
    await bot.process_commands(message)


async def lock_channel(channel):
    """Locks the channel by denying permissions for Pokétwo."""
    guild = channel.guild
    poketwo = guild.get_member(POKETWO_ID)

    if not poketwo:
        print("Pokétwo bot not found in this server.")
        return

    # Lock the channel for Pokétwo
    overwrite = channel.overwrites_for(poketwo)
    overwrite.view_channel = False
    overwrite.send_messages = False
    await channel.set_permissions(poketwo, overwrite=overwrite)

    print(f"Locked channel: {channel.name}")
    await channel.send(f"The channel has been locked for Pokétwo.")


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


async def send_unlock_button(channel):
    """Sends an unlock button in the channel."""
    class UnlockView(View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
        async def unlock(self, interaction: discord.Interaction, button: Button):
            # Ensure the user has the Unlock role
            unlock_role = discord.utils.get(interaction.guild.roles, name="Unlock")
            if unlock_role in interaction.user.roles:
                await unlock_channel(channel)
                await interaction.response.send_message("Channel unlocked!", ephemeral=True)
                self.stop()
            else:
                await interaction.response.send_message(
                    "You don't have the required 'Unlock' role to unlock this channel.",
                    ephemeral=True,
                )

    # Embed for unlock notification
    embed = discord.Embed(
        title="Channel Locked",
        description="The channel has been locked for Pokétwo. Click the button below to unlock it.",
        color=discord.Color.red(),
    )
    embed.set_footer(text="Use the unlock button to restore access.")
    await channel.send(embed=embed, view=UnlockView())


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Manually locks the channel."""
    await lock_channel(ctx.channel)
    await ctx.send(f"Channel {ctx.channel.mention} has been locked manually.")


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Manually unlocks the channel."""
    await unlock_channel(ctx.channel)
    await ctx.send(f"Channel {ctx.channel.mention} has been unlocked manually.")


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
