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
P2A_PREMIUM_ID = 1254602968938844171  # P2A Premium's ID

# Trigger phrases (case-insensitive)
TRIGGER_PHRASES = ["shiny hunt pings", "collection pings", "rare ping"]
SHINY_PHRASE = "these colors seem unusual..✨"

# Role ID for unlocking channels
UNLOCK_ROLE_ID = 123456789012345678  # Replace with the actual role ID

# Logging channel ID
LOG_CHANNEL_ID = 987654321098765432  # Replace with the actual channel ID for logging

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
    """Detect specific messages and handle accordingly."""
    if message.author.bot:
        # Check if the message is from Pokétwo
        if message.author.id == POKETWO_ID and SHINY_PHRASE in message.content.lower():
            await send_congratulations(message.channel)
        return

    print(f"Message from {message.author} ({message.author.id}): {message.content}")

    # Check for trigger phrases in any message
    if any(phrase in message.content.lower() for phrase in TRIGGER_PHRASES):
        print(f"Trigger phrase detected in message: {message.content}")
        await lock_channel(message.channel)
        await send_unlock_button(message.channel)

    await bot.process_commands(message)


async def lock_channel(channel):
    """Locks the channel by denying permissions for Pokétwo."""
    guild = channel.guild
    poketwo = guild.get_member(POKETWO_ID)

    if not poketwo:
        print("Pokétwo bot not found in this server.")
        return

    overwrite = channel.overwrites_for(poketwo)
    overwrite.view_channel = False
    overwrite.send_messages = False
    await channel.set_permissions(poketwo, overwrite=overwrite)

    print(f"Locked channel: {channel.name}")
    await channel.send(f"The channel has been locked for Pokétwo.")

    # Log the lock action
    await log_action(channel.guild, f"🔒 Locked channel: {channel.mention}")


async def send_unlock_button(channel):
    """Sends an unlock button in the channel."""
    class UnlockView(View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
        async def unlock(self, interaction: discord.Interaction, button: Button):
            role = interaction.guild.get_role(UNLOCK_ROLE_ID)
            if role in interaction.user.roles:
                await unlock_channel(channel)
                await interaction.response.send_message("Channel unlocked!", ephemeral=True)
                self.stop()
            else:
                await interaction.response.send_message(
                    "You don't have the required role to unlock this channel.",
                    ephemeral=True
                )

    embed = discord.Embed(
        title="Channel Locked",
        description="The channel has been locked for Pokétwo. Click the button below to unlock it if authorized.",
        color=discord.Color.red()
    )
    embed.set_footer(text="Use the unlock button to restore access.")
    await channel.send(embed=embed, view=UnlockView())


async def unlock_channel(channel):
    """Unlocks the channel by restoring permissions for Pokétwo."""
    guild = channel.guild
    poketwo = guild.get_member(POKETWO_ID)

    if not poketwo:
        print("Pokétwo bot not found in this server.")
        return

    await channel.set_permissions(poketwo, overwrite=None)
    print(f"Unlocked channel: {channel.name}")
    await channel.send("The channel has been unlocked!")

    # Log the unlock action
    await log_action(channel.guild, f"🔓 Unlocked channel: {channel.mention}")


async def log_action(guild, message):
    """Logs an action to the designated logging channel."""
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        await log_channel.send(message)
    else:
        print("Logging channel not found. Please verify the LOG_CHANNEL_ID.")


@bot.command(name="ping")
async def ping(ctx):
    """Responds with Pong!"""
    await ctx.send("Pong!")


@bot.command(name="owner")
async def owner(ctx):
    """Responds with the owner information."""
    await ctx.send("This bot is owned by **Cloud**. All rights reserved!")


@bot.command(name="d")
@commands.has_permissions(manage_channels=True)
async def delete_channel(ctx):
    """Deletes the current channel."""
    await ctx.channel.delete(reason=f"Deleted by {ctx.author}")


@bot.command(name="move")
@commands.has_permissions(manage_channels=True)
async def move_category(ctx, category_name: str):
    """Moves the current channel to the specified category."""
    category = discord.utils.get(ctx.guild.categories, name=category_name)
    if category:
        await ctx.channel.edit(category=category)
        await ctx.send(f"Moved channel to category: {category_name}")
    else:
        await ctx.send("Category not found. Please check the name and try again.")


async def send_congratulations(channel):
    """Sends a congratulatory embed for a shiny Pokémon detection."""
    embed = discord.Embed(
        title="✨ Shiny Pokémon Found! ✨",
        description="Congratulations on finding a shiny Pokémon! 🎉",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Shiny hunting pays off!")
    await channel.send(embed=embed)


# Run the bot
bot.run(BOT_TOKEN)
