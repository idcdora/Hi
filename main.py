import discord
from discord.ext import commands
import asyncio
import aiohttp
import base64
import requests

watched_users = {}  # user_id -> list of emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}
sniped_messages = {}  # channel_id -> (author, content)

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

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

async def fetch_lyrics(song_name):
    # Simple Genius lyrics fetcher without API token using web scraping
    import aiohttp
    from bs4 import BeautifulSoup

    query = song_name.replace(" ", "+")
    search_url = f"https://genius.com/api/search/multi?per_page=5&q={query}"
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as resp:
            data = await resp.json()
    sections = data.get("response", {}).get("sections", [])
    song_path = None
    for section in sections:
        if section["type"] == "song" and section["hits"]:
            song_path = section["hits"][0]["result"]["path"]
            break
    if not song_path:
        return None, None
    song_url = "https://genius.com" + song_path
    async with aiohttp.ClientSession() as session:
        async with session.get(song_url) as resp:
            text = await resp.text()
    soup = BeautifulSoup(text, "html.parser")
    lyrics_div = soup.find("div", class_="lyrics") or soup.find("div", class_="Lyrics__Container-sc-1ynbvzw-6 YYrds")
    if not lyrics_div:
        return None, None
    lyrics = lyrics_div.get_text(separator="\n").strip()
    title = soup.find("h1", class_="header_with_cover_art-primary_info-title")
    title_text = title.text.strip() if title else song_name
    return title_text, lyrics

async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    typing_tasks = {}  # channel_id -> asyncio.Task

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

    @bot.event
    async def on_message_delete(message):
        if message.guild:
            sniped_messages[message.channel.id] = (message.author, message.content)
        else:
            # For DMs, store using channel id
            sniped_messages[message.channel.id] = (message.author, message.content)

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
            watched_roles.intersection(author_roles) or
            (message.guild and message.guild.id in react_all_servers)
        )

        if should_react:
            try:
                if author_id in watched_users:
                    emojis = watched_users[author_id]
                elif message.guild and message.guild.id in react_all_servers:
                    emojis = react_all_servers[message.guild.id]
                else:
                    emojis = []
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
    async def watchrole(ctx, role: discord.Role, *emojis):
        watched_roles.add(role.id)
        # Optionally store emojis per role if you want more control here
        await ctx.send(f"Watching role {role.name} with emojis {''.join(emojis) if emojis else '(default)'}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching role {role.name}")
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
        if channel_id in typing_tasks:
            await ctx.send("Already typing in that channel.")
            return

        await ctx.send(f"Typing forever in <#{channel_id}>")

        async def typing_loop():
            try:
                while True:
                    async with channel.typing():
                        await asyncio.sleep(5)
            except asyncio.CancelledError:
                pass

        task = bot.loop.create_task(typing_loop())
        typing_tasks[channel_id] = task

    @bot.command()
    async def stoptyper(ctx, channel_id: int):
        task = typing_tasks.get(channel_id)
        if task:
            task.cancel()
            typing_tasks.pop(channel_id, None)
            await ctx.send(f"Stopped typing in <#{channel_id}>")
        else:
            await ctx.send("No typing task found for that channel.")
        await ctx.message.delete()

    @bot.command()
    async def purge(ctx, user: discord.User, amount: int):
        def is_user(m):
            return m.author.id == user.id
        deleted = await ctx.channel.purge(limit=amount, check=is_user)
        await ctx.send(f"Deleted {len(deleted)} messages from {user.name}.", delete_after=5)
        await ctx.message.delete()

    @bot.command()
    async def snipe(ctx):
        data = sniped_messages.get(ctx.channel.id)
        if data:
            author, content = data
            if author == bot.user:
                await ctx.send("Nothing to snipe.")
                return
            await ctx.send(f"Sniped message from **{author}**:\n{content}")
        else:
            await ctx.send("No recently deleted message found.")
        await ctx.message.delete()

    @bot.command(name="h")
    async def help_cmd(ctx):
        help_message = (
            "**Commands:**\n"
            "\n"
            "**🔹 Reacting:**\n"
            "`!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n"
            "\n"
            "**🔹 Spamming:**\n"
            "`!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n"
            "\n"
            "**🔹 Status:**\n"
            "`!rpc`, `!statusall`, `!typer`, `!stoptyper`, `!lyrics`\n"
            "\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    @bot.command()
    async def lyrics(ctx, *, song_name: str):
        await ctx.send(f"Fetching lyrics for: {song_name}")
        title, lyrics = await fetch_lyrics(song_name)
        if not lyrics:
            await ctx.send("Lyrics not found.")
            return
        # Send song title big and lyrics smaller
        await ctx.send(f"**{title}**\n\n{lyrics}")
        await ctx.message.delete()

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
