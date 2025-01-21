import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv
import random

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

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


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")


@bot.event
async def on_message(message):
    try:
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
        if message.author.bot and message.content:
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

        # Process commands after handling custom logic
        await bot.process_commands(message)
    except Exception as e:
        print(f"Error in on_message: {e}")


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
    embed.add_field(name=".del", value="Delete the current channel.", inline=False)
    embed.add_field(name=".move <category>", value="Move the current channel to a new category.", inline=False)
    embed.add_field(name=".clone", value="Clone the current channel.", inline=False)
    embed.add_field(name=".roll NdN", value="Roll dice in NdN format (e.g., `2d6`).", inline=False)
    embed.add_field(name=".owner", value="Displays the bot's creator.", inline=False)

    await ctx.send(embed=embed)


@bot.command(name="owner")
async def bot_owner(ctx):
    """Display the bot creator."""
    embed = discord.Embed(
        title="Bot Creator",
        description="This bot was made by 💨 Suk Ballz",
        color=discord.Color.purple(),
    )
    await ctx.send(embed=embed)


@bot.command(name="toggle_keyword")
@commands.has_permissions(manage_channels=True)
async def toggle_keyword(ctx, *, keyword: str):
    """Toggle detection of a specific keyword."""
    keyword = keyword.lower()
    if keyword not in KEYWORDS:
        await ctx.send(f"The keyword `{keyword}` is not valid. Available keywords: {', '.join(KEYWORDS.keys())}")
        return

    # Toggle the status
    KEYWORDS[keyword] = not KEYWORDS[keyword]
    status = "enabled" if KEYWORDS[keyword] else "disabled"
    await ctx.send(f"Detection for `{keyword}` has been {status}.")


@bot.command(name="list_keywords")
@commands.has_permissions(manage_channels=True)
async def list_keywords(ctx):
    """List the status of all keywords."""
    statuses = [f"`{keyword}`: {'enabled' if status else 'disabled'}" for keyword, status in KEYWORDS.items()]
    await ctx.send("Keyword detection statuses:\n" + "\n".join(statuses))


@bot.command(name="lock")
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    if ctx.channel.id in blacklisted_channels:
        await ctx.send("This channel is blacklisted and cannot be locked.")
        return

    await lock_channel(ctx.channel)
    embed = discord.Embed(
        title="Channel Locked",
        description="The channel has been manually locked for Pokétwo.",
        color=discord.Color.red(),
    )
    embed.set_footer(text="Use the unlock command or button to restore access.")
    view = UnlockView(channel=ctx.channel)
    await ctx.send(embed=embed, view=view)


@bot.command(name="unlock")
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await unlock_channel(ctx.channel)
    embed = discord.Embed(
        title="Channel Unlocked",
        description="The channel has been unlocked for Pokétwo.",
        color=discord.Color.green(),
    )
    embed.set_footer(text="You can lock the channel again using the lock command.")
    await ctx.send(embed=embed)


@bot.command(name="del")
@commands.has_permissions(manage_channels=True)
async def delete_channel(ctx):
    """Delete the current channel."""
    await ctx.send(f"Deleting this channel: {ctx.channel.name}")
    await ctx.channel.delete()


@bot.command(name="move")
@commands.has_permissions(manage_channels=True)
async def move_channel(ctx, *, category_name: str):
    """Move the current channel to a specified category."""
    category = discord.utils.get(ctx.guild.categories, name=category_name)
    if not category:
        await ctx.send(f"Category `{category_name}` not found.")
        return

    await ctx.channel.edit(category=category)
    await ctx.send(f"Moved channel to category: `{category_name}`")


@bot.command(name="clone")
@commands.has_permissions(manage_channels=True)
async def clone_channel(ctx):
    """Clone the current channel."""
    cloned_channel = await ctx.channel.clone()
    await cloned_channel.edit(position=ctx.channel.position + 1)
    await ctx.send(f"Cloned channel: {cloned_channel.mention}")


@bot.command(name="roll")
async def roll(ctx, dice: str):
    """Roll dice in NdN format (e.g., 2d6)."""
    try:
        rolls, sides = map(int, dice.lower().split('d'))
    except ValueError:
        await ctx.send("Invalid dice format! Use `NdN` (e.g., `2d6`).")
        return

    if rolls <= 0 or sides <= 0:
        await ctx.send("The number of rolls and sides must be positive integers.")
        return

    results = [random.randint(1, sides) for _ in range(rolls)]
    await ctx.send(f"🎲 You rolled: {', '.join(map(str, results))} (Total: {sum(results)})")


class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        # Check if the user has the "unlock" role or manage_channels permission
        unlock_role = discord.utils.get(interaction.guild.roles, name="unlock")
        if unlock_role in interaction.user.roles or interaction.user.guild_permissions.manage_channels:
            await unlock_channel(self.channel)
            await interaction.response.send_message("Channel unlocked!", ephemeral=True)
            self.stop()
        else:
            await interaction.response.send_message(
                "You don't have permission or the 'unlock' role to unlock this channel.",
                ephemeral=True,
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
    
