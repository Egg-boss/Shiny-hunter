import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Replace with Pokétwo's User ID
POKETWO_ID = 716390085896962058

# Intents setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Keywords to monitor in messages
KEYWORDS = ["shiny hunt pings", "collection pings", "rare ping"]

# Blacklist for locking
blacklist_channels = set()

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
        return  # Ignore the bot's own messages

    if message.channel.id in blacklist_channels:
        return  # Ignore blacklisted channels

    if message.author.bot:
        if any(keyword in message.content.lower() for keyword in KEYWORDS):
            await lock_channel(message.channel)
            embed = discord.Embed(
                title="Channel Locked",
                description=f"Due to detected bot activity with the keywords: {', '.join(KEYWORDS)}.",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Use the unlock command or button to restore access.")
            await message.channel.send(embed=embed)

    if "these colors seem unusual..✨" in message.content.lower():
        embed = discord.Embed(
            title="Congratulations!",
            description="A shiny Pokémon has been detected! 🎉",
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


async def lock_channel(channel):
    """Locks the channel for Pokétwo."""
    guild = channel.guild
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        print("Pokétwo bot not found in this server.")
        return

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

    await channel.set_permissions(poketwo, overwrite=None)
    print(f"Unlocked channel: {channel.name}")


@bot.command(name="ping")
async def ping(ctx):
    """Responds with Pong!"""
    await ctx.send("Pong!")


@bot.command(name="owner")
async def owner(ctx):
    """Responds with the owner information."""
    await ctx.send("This bot is owned by **Cloud**. All rights reserved!")


@bot.command(name="blacklist")
@commands.has_permissions(manage_channels=True)
async def blacklist(ctx):
    """Blacklists the current channel from being locked."""
    if ctx.channel.id not in blacklist_channels:
        blacklist_channels.add(ctx.channel.id)
        await ctx.send("This channel has been blacklisted from auto-locking.")
    else:
        await ctx.send("This channel is already blacklisted.")


@bot.command(name="whitelist")
@commands.has_permissions(manage_channels=True)
async def whitelist(ctx):
    """Removes the current channel from the blacklist."""
    if ctx.channel.id in blacklist_channels:
        blacklist_channels.remove(ctx.channel.id)
        await ctx.send("This channel has been removed from the blacklist.")
    else:
        await ctx.send("This channel is not in the blacklist.")


@bot.command(name="blacklisted")
@commands.has_permissions(manage_channels=True)
async def blacklisted(ctx):
    """Lists all blacklisted channels."""
    if not blacklist_channels:
        await ctx.send("No channels are blacklisted.")
    else:
        channel_mentions = [f"<#{channel_id}>" for channel_id in blacklist_channels]
        await ctx.send("Blacklisted channels:\n" + "\n".join(channel_mentions))


# Run the bot
bot.run(BOT_TOKEN)
