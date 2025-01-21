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

# List of blacklisted channel IDs
BLACKLISTED_CHANNELS = []


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
        return  # Ignore the bot's own messages

    if message.author.bot:  # Check if the message is from a bot
        # Check for shiny Pokémon message from Pokétwo
        if (
            message.author.id == POKETWO_ID
            and "these colors seem unusual..✨" in message.content.lower()
        ):
            embed = discord.Embed(
                title="Congratulations!",
                description="A shiny Pokémon has appeared!",
                color=discord.Color.gold(),
            )
            embed.set_footer(text="Catch it before it disappears!")
            await message.channel.send(embed=embed)

        # Skip locking behavior if the channel is blacklisted
        if message.channel.id in BLACKLISTED_CHANNELS:
            return

        # Check for exact keywords in the message content
        if any(keyword in message.content.lower() for keyword in KEYWORDS):
            await lock_channel(message.channel)
            embed = discord.Embed(
                title="Channel Locked",
                description=f"The channel has been locked due to detected bot activity containing the following keywords: {', '.join(KEYWORDS)}.",
                color=discord.Color.red(),
            )
            embed.set_footer(text="Use the unlock command or button to restore access.")

            # Add unlock button
            class UnlockView(View):
                def __init__(self):
                    super().__init__(timeout=None)

                @discord.ui.button(label="Unlock Channel", style=discord.ButtonStyle.green)
                async def unlock_button(self, interaction: discord.Interaction, button: Button):
                    unlock_role = discord.utils.get(interaction.guild.roles, name="unlock")
                    if unlock_role in interaction.user.roles or interaction.user.guild_permissions.manage_channels:
                        await unlock_channel(message.channel)
                        await interaction.response.send_message("Channel unlocked!", ephemeral=True)
                        self.stop()
                    else:
                        await interaction.response.send_message(
                            "You don't have the required role to unlock this channel.", ephemeral=True
                        )

            await message.channel.send(embed=embed, view=UnlockView())

    await bot.process_commands(message)  # Ensure commands still work


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
    """Adds a channel to the blacklist for locking behavior."""
    if channel.id not in BLACKLISTED_CHANNELS:
        BLACKLISTED_CHANNELS.append(channel.id)
        await ctx.send(f"{channel.mention} has been added to the blacklist for locking behavior.")
    else:
        await ctx.send(f"{channel.mention} is already in the blacklist.")


@bot.command(name="remove_blacklist_channel")
@commands.has_permissions(manage_channels=True)
async def remove_blacklist_channel(ctx, channel: discord.TextChannel):
    """Removes a channel from the blacklist for locking behavior."""
    if channel.id in BLACKLISTED_CHANNELS:
        BLACKLISTED_CHANNELS.remove(channel.id)
        await ctx.send(f"{channel.mention} has been removed from the blacklist for locking behavior.")
    else:
        await ctx.send(f"{channel.mention} is not in the blacklist.")


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
