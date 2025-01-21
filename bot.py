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


@bot.command(name="blacklist")
@commands.has_permissions(manage_channels=True)
async def blacklist_command(ctx, action: str, channel: discord.TextChannel = None):
    """
    Manage blacklisted channels.
    Usage:
      .blacklist add <channel>
      .blacklist remove <channel>
      .blacklist list
    """
    global blacklisted_channels

    if action.lower() == "add" and channel:
        blacklisted_channels.add(channel.id)
        await ctx.send(f"Channel `{channel.name}` has been added to the blacklist.")
        await log_event(ctx.guild, f"🚫 Blacklisted channel added: {channel.name}")
    elif action.lower() == "remove" and channel:
        blacklisted_channels.discard(channel.id)
        await ctx.send(f"Channel `{channel.name}` has been removed from the blacklist.")
        await log_event(ctx.guild, f"✅ Blacklisted channel removed: {channel.name}")
    elif action.lower() == "list":
        if not blacklisted_channels:
            await ctx.send("No channels are currently blacklisted.")
        else:
            channels = [f"<#{ch_id}>" for ch_id in blacklisted_channels]
            await ctx.send("Blacklisted channels:\n" + "\n".join(channels))
    else:
        await ctx.send("Invalid usage. Use `.blacklist <add/remove/list> [channel]`.")


@bot.command(name="log_channel")
@commands.has_permissions(manage_channels=True)
async def set_log_channel(ctx, action: str):
    """Set or unset the log channel."""
    global log_channel_id

    if action.lower() == "set":
        log_channel_id = ctx.channel.id
        await ctx.send(f"This channel (`{ctx.channel.name}`) is now set as the log channel.")
    elif action.lower() == "unset":
        log_channel_id = None
        await ctx.send("Log channel has been unset.")
    else:
        await ctx.send("Invalid usage. Use `.log_channel <set/unset>`.")


async def log_event(guild, message):
    """Logs messages to the log channel if set."""
    if log_channel_id:
        log_channel = guild.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(message)


@bot.command(name="joke")
async def joke_command(ctx):
    """Sends a random joke."""
    jokes = [
        "Why don’t skeletons fight each other? They don’t have the guts.",
        "Why did the scarecrow win an award? Because he was outstanding in his field!",
        "What do you call cheese that isn't yours? Nacho cheese.",
    ]
    await ctx.send(random.choice(jokes))


@bot.command(name="8ball")
async def eight_ball(ctx, *, question: str):
    """Answers a question with a random response."""
    responses = [
        "Yes.", "No.", "Maybe.", "Ask again later.", "Definitely!", "Not a chance."
    ]
    await ctx.send(f"🎱 {random.choice(responses)}")


@bot.command(name="inspire")
async def inspire_command(ctx):
    """Sends a motivational quote."""
    quotes = [
        "Believe you can and you're halfway there. - Theodore Roosevelt",
        "Don't watch the clock; do what it does. Keep going. - Sam Levenson",
        "Success is not final, failure is not fatal: It is the courage to continue that counts. - Winston Churchill",
    ]
    await ctx.send(random.choice(quotes))


class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.guild_permissions.manage_channels:
            await unlock_channel(self.channel)
            await interaction.response.send_message("Channel unlocked!", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message(
                "You don't have permission to unlock this channel.", ephemeral=True
            )


async def lock_channel(channel):
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


async def unlock_channel(channel):
    guild = channel.guild
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        print("Pokétwo bot not found in this server.")
        return

    await channel.set_permissions(poketwo, overwrite=None)


bot.run(BOT_TOKEN)
