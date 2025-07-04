import discord
from discord.ext import commands
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
import time

watched_users = {}
watched_roles = set()
react_all_servers = {}
token_user_ids = set()
all_bots = []
blacklisted_users = {}
lyrics_tasks = {}

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

# GENIUS HELPERS (bs4 no API key needed)
def search_genius(query):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }
    url = f"https://genius.com/api/search/multi?per_page=5&q={requests.utils.quote(query)}"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Search HTTP error: {r.status_code}")
        return None
    data = r.json()
    for section in data.get("response", {}).get("sections", []):
        if section.get("type") == "song":
            hits = section.get("hits", [])
            if hits:
                return hits[0]["result"]["url"]
    return None

def get_lyrics_lines(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9"
    }
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Lyrics HTTP error: {r.status_code}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    lyrics_divs = soup.find_all("div", attrs={"data-lyrics-container": "true"})
    lyrics = "\n".join(div.get_text(separator="\n") for div in lyrics_divs)
    return [line.strip() for line in lyrics.split("\n") if line.strip()]

# BOT MAIN
async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)
    typer_tasks = {}

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

    @bot.event
    async def on_message(message):
        if message.author.id in blacklisted_users:
            return
        await bot.process_commands(message)

    snipes = {}
    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return
        snipes[message.channel.id] = message

    # Snipe
    @bot.command()
    async def snipe(ctx):
        msg = snipes.get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe!")
            return
        await ctx.send(f"Sniped: {msg.author}: {msg.content or '[embed/image]'}")

    # Blacklist
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

    # React commands
    @bot.command()
    async def react(ctx, user: discord.User, *emojis):
        if not emojis:
            await ctx.send("Provide emojis.")
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
        await ctx.send(f"Watching {role.name}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching {role.name}")
        await ctx.message.delete()

    @bot.command()
    async def reactall(ctx, server_id: int, *emojis):
        react_all_servers[server_id] = list(emojis)
        await ctx.send(f"Reacting in server {server_id}")
        await ctx.message.delete()

    @bot.command()
    async def unreactall(ctx, server_id: int):
        react_all_servers.pop(server_id, None)
        await ctx.send(f"Stopped reacting in server {server_id}")
        await ctx.message.delete()

    # Spam
    @bot.command()
    async def spam(ctx, *, args):
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spam <msg> <count>")
            return
        await ctx.message.delete()
        for _ in range(count):
            await ctx.send(msg)

    @bot.command()
    async def massdmspam(ctx, message, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end:
            for member in ctx.guild.members:
                if not member.bot:
                    try: await member.send(message)
                    except: pass
        await ctx.send("Done.")

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send("Spamming webhook...")
        async with aiohttp.ClientSession() as session:
            for _ in range(count):
                try: await session.post(url, json={"content": message})
                except: pass
        await ctx.send("Done.")

    # Status
    @bot.command()
    async def rpc(ctx, activity_type: str, *, activity_message: str):
        if activity_type == "streaming":
            activity = discord.Streaming(name=activity_message, url="https://twitch.tv/test")
        elif activity_type == "playing":
            activity = discord.Game(name=activity_message)
        else:
            enum_type = getattr(discord.ActivityType, activity_type, discord.ActivityType.playing)
            activity = discord.Activity(type=enum_type, name=activity_message)
        await bot.change_presence(activity=activity)
        await ctx.send(f"Status set to {activity_type} {activity_message}")
        await ctx.message.delete()

    @bot.command()
    async def statusall(ctx, activity_type: str, *, activity_message: str):
        for b in all_bots:
            try:
                if activity_type == "streaming":
                    act = discord.Streaming(name=activity_message, url="https://twitch.tv/test")
                elif activity_type == "playing":
                    act = discord.Game(name=activity_message)
                else:
                    enum_type = getattr(discord.ActivityType, activity_type, discord.ActivityType.playing)
                    act = discord.Activity(type=enum_type, name=activity_message)
                await b.change_presence(activity=act)
            except: pass
        await ctx.send(f"All bots set to {activity_type}")
        await ctx.message.delete()

    # Typer
    @bot.command()
    async def typer(ctx, channel_id: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Invalid channel.")
            return
        await ctx.send(f"Typing forever in <#{channel_id}>. Use !stoptyper.")
        task = asyncio.create_task(typing_loop(channel))
        typer_tasks[ctx.author.id] = task

    async def typing_loop(channel):
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @bot.command()
    async def stoptyper(ctx):
        task = typer_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            typer_tasks.pop(ctx.author.id, None)
            await ctx.send("Stopped typing.")
        else:
            await ctx.send("No active typer.")
        await ctx.message.delete()

    # Purge
    @bot.command()
    async def purge(ctx, user: discord.User, amount: int):
        deleted = 0
        async for msg in ctx.channel.history(limit=1000):
            if deleted >= amount: break
            if msg.author == user:
                try:
                    await msg.delete()
                    deleted += 1
                except: pass
        await ctx.send(f"Deleted {deleted} from {user.name}", delete_after=5)
        await ctx.message.delete()

    # Lyrics commands
    @bot.command()
    async def lyrics(ctx, *, query: str):
        await ctx.message.delete()
        if query.startswith("http"):
            lyrics_url = query
        else:
            lyrics_url = search_genius(query)
            if not lyrics_url:
                await ctx.send("No Genius link found.")
                return
        lines = get_lyrics_lines(lyrics_url)
        if not lines:
            await ctx.send("Couldn't extract lyrics.")
            return
        await ctx.send("Lyrics found. Updating status...")
        task = asyncio.create_task(update_lyrics_status(bot, lines))
        lyrics_tasks[ctx.author.id] = task

    async def update_lyrics_status(bot, lines):
        i = 0
        while True:
            await bot.change_presence(activity=discord.Game(name=lines[i]))
            i = (i + 1) % len(lines)
            await asyncio.sleep(4)

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
            await ctx.send("Stopped lyrics.")
        else:
            await ctx.send("No lyrics running.")
        await ctx.message.delete()

    # Help
    @bot.command(name="h")
    async def help_cmd(ctx):
        msg = (
            "**Commands:**\n\n"
            "**🔹 Reacting:** `!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n"
            "**🔹 Spamming:** `!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n"
            "**🔹 Status:** `!rpc`, `!statusall`, `!typer`, `!stoptyper`, `!lyrics`, `!stoplyrics`\n"
            "**🔹 Moderation:** `!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "*:3*"
        )
        await ctx.send(msg)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
