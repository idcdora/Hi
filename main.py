import discord
from discord.ext import commands
import asyncio
import aiohttp

watched_users = {}  # user_id -> list of emojis
watched_roles = {}  # role_id -> list of emojis
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}
last_deleted_messages = {}  # channel_id -> message
typing_tasks = {}  # channel_id -> asyncio.Task

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

async def mass_dm(guild, message):
    for member in guild.members:
        if not member.bot:
            try:
                await member.send(message)
            except:
                pass

async def webhook_spam(url, message, count):
    async with aiohttp.ClientSession() as session:
        for _ in range(count):
            try:
                await session.post(url, json={"content": message})
            except:
                pass

async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

    @bot.event
    async def on_message_delete(message):
        if not message.author.bot:
            last_deleted_messages[message.channel.id] = message

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
            watched_roles.keys() & author_roles or
            (message.guild and message.guild.id in react_all_servers)
        )

        if should_react:
            try:
                if author_id in watched_users:
                    emojis = watched_users[author_id]
                elif watched_roles.keys() & author_roles:
                    emojis = []
                    for rid in author_roles:
                        emojis += watched_roles.get(rid, [])
                elif message.guild and message.guild.id in react_all_servers:
                    emojis = react_all_servers[message.guild.id]
                else:
                    emojis = []
                for emoji in emojis:
                    await message.add_reaction(emoji)
            except:
                pass

        await bot.process_commands(message)

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
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Now reacting to {user.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unreact(ctx, user: discord.User):
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")
        await ctx.message.delete()

    @bot.command()
    async def watchrole(ctx, role: discord.Role, *emojis):
        watched_roles[role.id] = list(emojis)
        await ctx.send(f"Watching role {role.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.pop(role.id, None)
        await ctx.send(f"Stopped watching role {role.name}")
        await ctx.message.delete()

    @bot.command()
    async def reactall(ctx, server_id: int, *emojis):
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
        msg, count = args.rsplit(" ", 1)
        count = int(count)
        await ctx.message.delete()
        for _ in range(count):
            await ctx.send(msg)

    @bot.command()
    async def spamall(ctx, *, args):
        msg, count = args.rsplit(" ", 1)
        count = int(count)
        await ctx.message.delete()
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)

    @bot.command()
    async def massdmspam(ctx, message, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end_time = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end_time:
            await mass_dm(ctx.guild, message)
        await ctx.send("Done.")

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")

    @bot.command()
    async def rpc(ctx, activity_type: str, *, activity_message: str):
        if activity_type == "streaming":
            activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
        elif activity_type == "playing":
            activity = discord.Game(name=activity_message)
        else:
            enum_type = getattr(discord.ActivityType, activity_type)
            activity = discord.Activity(type=enum_type, name=activity_message)
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
        task = asyncio.create_task(keep_typing(channel))
        typing_tasks[channel_id] = task

    async def keep_typing(channel):
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @bot.command()
    async def typeroff(ctx, channel_id: int):
        task = typing_tasks.pop(channel_id, None)
        if task:
            task.cancel()
            await ctx.send(f"Stopped typing in <#{channel_id}>")
        else:
            await ctx.send("No typing task found.")

    @bot.command()
    async def snipe(ctx):
        msg = last_deleted_messages.get(ctx.channel.id)
        if msg:
            await ctx.send(f"Sniped: {msg.author}: {msg.content}")
        else:
            await ctx.send("Nothing to snipe!")

    @bot.command()
    async def purge(ctx, user: discord.User, limit: int):
        async for message in ctx.channel.history(limit=1000):
            if message.author == user:
                try:
                    await message.delete()
                except:
                    pass
                limit -= 1
                if limit <= 0:
                    break
        await ctx.send(f"Purged {user.name}'s messages.")
        await ctx.message.delete()

    @bot.command(name="h")
    async def help_cmd(ctx):
        await ctx.send("""**Commands**

**Reacting**
!react, !unreact, !reactall, !unreactall, !watchrole, !unwatchrole

**Spamming**
!spam, !spamall, !massdmspam, !webhookspam

**Status**
!rpc, !statusall, !typer, !typeroff

**Moderation**
!blacklist, !unblacklist, !purge, !snipe

*:3*""")
        await asyncio.sleep(0.5)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif?ex=6867de80&is=68668d00&hm=e81e1b88994e14b6b51982fc91d4c3af07dba8bbae87d2c581e787f80b0dca68")
        await ctx.message.delete()

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
