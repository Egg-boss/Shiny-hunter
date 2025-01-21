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

# A list to store blacklisted channels
blacklisted_channels = []

# Keywords to monitor in messages
KEYWORDS = ["shiny hunt pings", "collection pings", "rare ping"]


@bot.event
async def on_ready():
    """Called when the bot is ready."""
    print(f"Bot is online as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")


@bot.event
async def on_message(message):
    """Monitor messages from all bots."""
    if message.author == bot.user:
        return

    if message.author.bot:  # Check if the message is from a bot
        if message.channel.id in blacklisted_channels:
            return  # Ignore blacklisted channels for locking logic

        # Check for exact keywords in the message content
        if any(keyword in message.content.lower() for keyword in KEYWORDS):
            await lock_channel(message.channel)
            embed = discord.Embed(
                title="Channel Locked",
                description=f"The channel has been locked due to detected bot activity containing the following keywords: {', '.join(KEYWORDS)}.",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Use the unlock command or button to restore access.")
            await message.channel.send(embed=embed)

        if "these colors seem unusual..✨" in message.content.lower():
            embed = discord.Embed(
                title="Congratulations!",
                description="A shiny Pokémon was detected! Celebrate the moment! 🎉",
                color=discord.Color.gold(),
            )
            await message.channel.send(embed=embed)
    await bot.process_commands(message)


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Manually locks the channel for Pokétwo and sends an embed with an unlock button."""
    await lock_channel(ctx.channel)
    embed = discord.Embed(
        title="Channel Locked",
        description="The channel has been manually locked for Pokétwo.",
        color=discord.Color.red(),
    )
    embed.set_footer(text="Use the unlock button or command to restore access.")

    # Add unlock button
    class UnlockView(View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
        async def unlock_button(self, interaction: discord.Interaction, button: Button):
            if interaction.user.guild_permissions.manage_channels:
                await unlock_channel(ctx.channel)
                await interaction.response.send_message("Channel unlocked!", ephemeral=True)
                self.stop()
            else:
                await interaction.response.send_message(
                    "You don't have permission to unlock this channel.", ephemeral=True
                )

    await ctx.send(embed=embed, view=UnlockView())


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Manually unlocks the channel for Pokétwo and sends an embed."""
    await unlock_channel(ctx.channel)
    embed = discord.Embed(
        title="Channel Unlocked",
        description="The channel has been unlocked for Pokétwo.",
        color=discord.Color.green(),
    )
    embed.set_footer(text="You can lock the channel again using the lock command.")
    await ctx.send(embed=embed)


@bot.command(name="blacklist_channel")
@commands.has_permissions(manage_channels=True)
async def blacklist_channel(ctx, channel: discord.TextChannel):
    """Blacklists a channel to prevent it from being locked."""
    if channel.id not in blacklisted_channels:
        blacklisted_channels.append(channel.id)
        await ctx.send(f"Channel {channel.mention} has been blacklisted from locking.")
    else:
        await ctx.send(f"Channel {channel.mention} is already blacklisted.")


@bot.command(name="remove_blacklist_channel")
@commands.has_permissions(manage_channels=True)
async def remove_blacklist_channel(ctx, channel: discord.TextChannel):
    """Removes a channel from the blacklist."""
    if channel.id in blacklisted_channels:
        blacklisted_channels.remove(channel.id)
        await ctx.send(f"Channel {channel.mention} has been removed from the blacklist.")
    else:
        await ctx.send(f"Channel {channel.mention} is not blacklisted.")


@bot.command(name="view_blacklist")
async def view_blacklist(ctx):
    """Displays all blacklisted channels."""
    if blacklisted_channels:
        channels = [f"<#{channel_id}>" for channel_id in blacklisted_channels]
        await ctx.send(f"Blacklisted Channels:\n{', '.join(channels)}")
    else:
        await ctx.send("There are no blacklisted channels.")


@bot.command(name="delete_channel")
@commands.has_permissions(manage_channels=True)
async def delete_channel(ctx, channel: discord.TextChannel):
    """Deletes a specified channel."""
    await channel.delete()
    await ctx.send(f"Channel {channel.name} has been deleted.")


async def lock_channel(channel):
    """Locks the channel for Pokétwo."""
    guild = channel.guild
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        print("Pokétwo bot not found in this server.")
        return

    # Set permissions to lock the channel for Pokétwo
    overwrite = channel.overwrites_for(poketwo)
    overwrite.view_channel = False
    overwrite.send_messages = False
    await channel.set_permissions(poketwo, overwrite=overwrite)
    print(f"Locked channel: {channel.name}")


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


# Custom help command
@bot.remove_command("help")  # Removes the default help command
@bot.command(name="help")
async def help_command(ctx):
    """Displays a list of all available commands."""
    embed = discord.Embed(
        title="Bot Commands",
        description="Here is a list of all available commands:",
        color=discord.Color.green(),
    )

    commands_list = [
        {"name": "!lock", "description": "Manually locks the current channel for Pokétwo."},
        {"name": "!unlock", "description": "Manually unlocks the current channel for Pokétwo."},
        {"name": "!blacklist_channel <channel>", "description": "Blacklists a channel to prevent it from being locked."},
        {"name": "!remove_blacklist_channel <channel>", "description": "Removes a channel from the blacklist."},
        {"name": "!view_blacklist", "description": "Displays all blacklisted channels."},
        {"name": "!delete_channel <channel>", "description": "Deletes a specified channel."},
        {"name": "!ping", "description": "Responds with Pong!"},
        {"name": "!owner", "description": "Displays information about the bot's owner."},
        {"name": "!help", "description": "Displays this list of commands."},
    ]

    for command in commands_list:
        embed.add_field(name=command["name"], value=command["description"], inline=False)

    embed.set_footer(text="Use the commands responsibly!")
    await ctx.send(embed=embed)


@bot.command(name="ping")
async def ping(ctx):
    """Responds with Pong!"""
    await ctx.send("Pong!")


@bot.command(name="owner")
async def owner(ctx):
    """Displays information about the bot owner."""
    await ctx.send("This bot is owned by **Cloud**. All rights reserved!")


# Run the bot
bot.run(BOT_TOKEN)
