import discord
from discord.ext import commands
from discord.ui import Button, View
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

POKETWO_ID = 716390085896962058  # Replace this with Pokétwo's actual User ID

# Intents setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Remove default help command to override it
bot.remove_command("help")

# Keywords to monitor
KEYWORDS = ["shiny hunt pings", "collection pings", "rare ping"]

# Channel blacklist
blacklisted_channels = set()


@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Check for messages from Pokétwo and "these colors seem unusual..✨"
    if message.author.bot and str(message.author) == "Pokétwo#8236":
        if "these colors seem unusual..✨" in message.content.lower():
            embed = discord.Embed(
                title="🎉 Congratulations! 🎉",
                description=f"{message.author.mention} has found a shiny Pokémon!",
                color=discord.Color.gold(),
            )
            embed.set_footer(text="Keep hunting for more rare Pokémon!")
            await message.channel.send(embed=embed)

    # Lock channel logic if specific keywords are detected
    if message.author.bot:
        if any(keyword in message.content.lower() for keyword in KEYWORDS):
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

    await bot.process_commands(message)


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


@bot.command(name="clone")
@commands.has_permissions(manage_channels=True)
async def clone(ctx, new_name: str = None):
    channel = ctx.channel
    try:
        cloned_channel = await channel.clone(name=new_name or channel.name)
        await ctx.send(f"Channel cloned successfully as {cloned_channel.mention}.")
    except discord.Forbidden:
        await ctx.send("I don't have the necessary permissions to clone this channel.")
    except Exception as e:
        await ctx.send(f"An error occurred while trying to clone the channel: {e}")


@bot.command(name="move")
@commands.has_permissions(manage_channels=True)
async def move(ctx, category_name: str):
    category = discord.utils.get(ctx.guild.categories, name=category_name)
    if not category:
        await ctx.send(f"Category '{category_name}' not found.")
        return

    try:
        await ctx.channel.edit(category=category)
        await ctx.send(f"Channel successfully moved to category: {category.name}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to move the channel.")
    except Exception as e:
        await ctx.send(f"An error occurred while moving the channel: {e}")


@bot.command(name="create")
@commands.has_permissions(manage_channels=True)
async def create(ctx, name: str, category_name: str = None):
    category = None
    if category_name:
        category = discord.utils.get(ctx.guild.categories, name=category_name)
        if not category:
            await ctx.send(f"Category '{category_name}' not found.")
            return

    try:
        channel = await ctx.guild.create_text_channel(name, category=category)
        await ctx.send(f"Channel '{channel.mention}' created successfully.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to create a new channel.")
    except Exception as e:
        await ctx.send(f"An error occurred while creating the channel: {e}")


@bot.command(name="blacklist")
@commands.has_permissions(manage_channels=True)
async def blacklist(ctx):
    if ctx.channel.id in blacklisted_channels:
        blacklisted_channels.remove(ctx.channel.id)
        await ctx.send(f"{ctx.channel.mention} has been removed from the blacklist.")
    else:
        blacklisted_channels.add(ctx.channel.id)
        await ctx.send(f"{ctx.channel.mention} has been added to the blacklist.")


@bot.command(name="blacklist_list")
@commands.has_permissions(manage_channels=True)
async def blacklist_list(ctx):
    if not blacklisted_channels:
        await ctx.send("No channels are currently blacklisted.")
        return

    blacklisted = [f"<#{channel_id}>" for channel_id in blacklisted_channels]
    await ctx.send("Blacklisted channels:\n" + "\n".join(blacklisted))


@bot.command(name="help")
async def custom_help(ctx):
    embed = discord.Embed(
        title="Help - Available Commands",
        description="Here are the commands you can use:",
        color=discord.Color.blue(),
    )
    embed.add_field(name="!lock", value="Manually lock the current channel for Pokétwo.", inline=False)
    embed.add_field(name="!unlock", value="Manually unlock the current channel for Pokétwo.", inline=False)
    embed.add_field(name="!delete", value="Delete the current channel.", inline=False)
    embed.add_field(name=".move <category>", value="Move the current channel to a different category.", inline=False)
    embed.add_field(name=".create <name> [category]", value="Create a new text channel.", inline=False)
    embed.add_field(name="!clone [new_name]", value="Clone the current channel with an optional new name.", inline=False)
    embed.add_field(name="!blacklist", value="Toggle blacklist status for the current channel.", inline=False)
    embed.add_field(name="!blacklist_list", value="List all blacklisted channels.", inline=False)
    embed.add_field(name="!help", value="Display this help message.", inline=False)
    embed.set_footer(text="Bot by Cloud.")
    await ctx.send(embed=embed)


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
