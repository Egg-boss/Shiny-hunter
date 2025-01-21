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

# Keywords to monitor in messages
KEYWORDS = ["shiny hunt pings", "collection pings", "rare ping"]
blacklisted_channels = set()


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
            embed.set_footer(text="Use the unlock button or command to restore access.")

            # Unlock button added directly to the lock embed
            class UnlockView(View):
                def __init__(self):
                    super().__init__(timeout=None)

                @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
                async def unlock_button(self, interaction: discord.Interaction, button: Button):
                    if interaction.user.guild_permissions.manage_channels:
                        await unlock_channel(message.channel)
                        await interaction.response.send_message("Channel unlocked!", ephemeral=True)
                        self.stop()
                    else:
                        await interaction.response.send_message(
                            "You don't have permission to unlock this channel.", ephemeral=True
                        )

            await message.channel.send(embed=embed, view=UnlockView())

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


@bot.command(name="blacklist")
@commands.has_permissions(manage_channels=True)
async def blacklist(ctx):
    """Toggles the blacklist status of a channel."""
    channel_id = ctx.channel.id
    if channel_id in blacklisted_channels:
        blacklisted_channels.remove(channel_id)
        await ctx.send("This channel has been removed from the blacklist.")
    else:
        blacklisted_channels.add(channel_id)
        await ctx.send("This channel has been added to the blacklist.")


@bot.command(name="blacklist_list")
@commands.has_permissions(manage_channels=True)
async def blacklist_list(ctx):
    """Lists all blacklisted channels."""
    if blacklisted_channels:
        channels = [f"<#{ch_id}>" for ch_id in blacklisted_channels]
        await ctx.send("Blacklisted channels:\n" + "\n".join(channels))
    else:
        await ctx.send("No channels are currently blacklisted.")


@bot.command(name="help")
async def help_command(ctx):
    """Displays a list of available commands."""
    embed = discord.Embed(
        title="Help - Available Commands",
        description="Here are the commands you can use:",
        color=discord.Color.blue(),
    )
    embed.add_field(name="!lock", value="Manually lock the current channel for Pokétwo.", inline=False)
    embed.add_field(name="!unlock", value="Manually unlock the current channel for Pokétwo.", inline=False)
    embed.add_field(name="!blacklist", value="Toggle blacklist status for the current channel.", inline=False)
    embed.add_field(name="!blacklist_list", value="List all blacklisted channels.", inline=False)
    embed.add_field(name="!help", value="Display this help message.", inline=False)
    embed.set_footer(text="Bot by Cloud.")
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


# Run the bot
bot.run(BOT_TOKEN)
