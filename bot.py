import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Replace with Pokétwo's User ID
POKETWO_ID = 716390085896962058  # Replace this with Pokétwo's actual User ID if needed

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


@bot.command(name="lock")
async def lock(ctx):
    """Locks the channel from Pokétwo and sends an unlock button."""
    guild = ctx.guild
    channel = ctx.channel

    # Fetch Pokétwo member
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)  # Use fetch_member for reliability
    except discord.NotFound:
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
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        print("Pokétwo bot not found in this server.")
        return

    # Restore default permissions for Pokétwo
    await channel.set_permissions(poketwo, overwrite=None)
    print(f"Unlocked channel: {channel.name}")
    await channel.send("The channel has been unlocked!")


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
