import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import random
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in the environment variables.")

POKETWO_ID = 716390085896962058  # Replace this with Pokétwo's actual User ID

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

# Channel blacklist
blacklisted_channels = set()


class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        unlock_role = discord.utils.get(interaction.guild.roles, name="unlock")
        if unlock_role in interaction.user.roles:
            await set_channel_permissions(self.channel, view_channel=None, send_messages=None)
            await interaction.response.send_message("Channel unlocked!", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message(
                "You don't have the 'unlock' role to unlock this channel.",
                ephemeral=True,
            )


@bot.event
async def on_ready():
    logging.info(f"Bot is online as {bot.user}")


@bot.event
async def on_message(message):
    try:
        if message.author == bot.user:
            return

        if message.author.bot and str(message.author) == "Pokétwo#8236":
            if "These colors seem unusual... ✨" in message.content:
                embed = discord.Embed(
                    title="🎉 Congratulations! 🎉",
                    description=f"{message.author.mention} has found a shiny Pokémon!",
                    color=discord.Color.gold(),
                )
                embed.set_footer(text="Keep hunting for more rare Pokémon!")
                await message.channel.send(embed=embed)

        if message.author.bot and message.content:
            active_keywords = [k for k, v in KEYWORDS.items() if v]
            if any(keyword in message.content.lower() for keyword in active_keywords):
                if message.channel.id not in blacklisted_channels:
                    await set_channel_permissions(message.channel, view_channel=False, send_messages=False)
                    embed = discord.Embed(
                        title="Channel Locked",
                        description="This channel has been locked due to specific keywords being detected.",
                        color=discord.Color.red(),
                    )
                    embed.set_footer(text="Use the unlock command or button to restore access.")
                    view = UnlockView(channel=message.channel)
                    await message.channel.send(embed=embed, view=view)

        await bot.process_commands(message)
    except Exception as e:
        logging.error(f"Error in on_message: {e}")


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="Bot Commands",
        description="Here are the available commands:",
        color=discord.Color.blue(),
    )
    commands_list = {
        ".help": "Displays this help message.",
        ".toggle_keyword <keyword>": "Enable/disable keyword detection.",
        ".list_keywords": "List the statuses of all keywords.",
        ".lock": "Manually lock the current channel.",
        ".unlock": "Manually unlock the current channel.",
        ".del": "Delete the current channel.",
        ".move <category>": "Move the current channel to a new category.",
        ".clone": "Clone the current channel.",
        ".roll NdN": "Roll dice in NdN format (e.g., `2d6`).",
        ".owner": "Displays the bot's creator.",
    }
    for command, description in commands_list.items():
        embed.add_field(name=command, value=description, inline=False)

    await ctx.send(embed=embed)


@bot.command(name="owner")
async def bot_owner(ctx):
    embed = discord.Embed(
        title="Bot Creator",
        description="This bot was made by 💨 Suk Ballz",
        color=discord.Color.purple(),
    )
    await ctx.send(embed=embed)


@bot.command(name="toggle_keyword")
@commands.has_permissions(manage_channels=True)
async def toggle_keyword(ctx, *, keyword: str):
    keyword = keyword.lower()
    if keyword not in KEYWORDS:
        await ctx.send(f"The keyword `{keyword}` is not valid. Available keywords: {', '.join(KEYWORDS.keys())}")
        return

    KEYWORDS[keyword] = not KEYWORDS[keyword]
    status = "enabled" if KEYWORDS[keyword] else "disabled"
    await ctx.send(f"Detection for `{keyword}` has been {status}.")


@bot.command(name="list_keywords")
@commands.has_permissions(manage_channels=True)
async def list_keywords(ctx):
    statuses = [f"`{keyword}`: {'enabled' if status else 'disabled'}" for keyword, status in KEYWORDS.items()]
    await ctx.send("Keyword detection statuses:\n" + "\n".join(statuses))


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    if ctx.channel.id in blacklisted_channels:
        await ctx.send("This channel is blacklisted and cannot be locked.")
        return

    await set_channel_permissions(ctx.channel, view_channel=False, send_messages=False)
    embed = discord.Embed(
        title="Channel Locked",
        description="The channel has been manually locked for Pokétwo.",
        color=discord.Color.red(),
    )
    embed.set_footer(text="Use the unlock command or button to restore access.")
    view = UnlockView(channel=ctx.channel)
    await ctx.send(embed=embed, view=view)


@bot.command(name="unlock")
async def unlock(ctx):
    unlock_role = discord.utils.get(ctx.guild.roles, name="unlock")

    if unlock_role in ctx.author.roles or ctx.author.guild_permissions.manage_channels:
        await set_channel_permissions(ctx.channel, view_channel=None, send_messages=None)
        embed = discord.Embed(
            title="Channel Unlocked",
            description="The channel has been unlocked for Pokétwo.",
            color=discord.Color.green(),
        )
        embed.set_footer(text="You can lock the channel again using the lock command.")
        await ctx.send(embed=embed)
    else:
        await ctx.send(
            "You don't have the required permissions or the 'unlock' role to unlock this channel."
        )


async def set_channel_permissions(channel, view_channel=None, send_messages=None):
    guild = channel.guild
    try:
        poketwo = await guild.fetch_member(POKETWO_ID)
    except discord.NotFound:
        logging.warning("Pokétwo bot not found in this server.")
        return

    overwrite = channel.overwrites_for(poketwo)

    if view_channel is not None:
        overwrite.view_channel = view_channel
    else:
        overwrite.view_channel = True

    if send_messages is not None:
        overwrite.send_messages = send_messages
    else:
        overwrite.send_messages = True

    await channel.set_permissions(poketwo, overwrite=overwrite)


bot.run(BOT_TOKEN)
    
