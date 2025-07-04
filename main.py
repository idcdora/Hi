import discord
from discord.ext import commands
import asyncio
import aiohttp
import re
import requests
from bs4 import BeautifulSoup
import random

watched_users = {}  # user_id -> list of emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

# Utility: Mass DM
async def mass_dm(guild, message):
    for member in guild.members:
        if not member.bot:
            try:
                await member.send(message)
            except:
                pass

# Utility: Webhook spam
async def webhook_spam(url, message, count):
    async with aiohttp.ClientSession() as session:
        for _ in range(count):
            try:
                await session.post(url, json={"content": message})
            except:
                pass

def clean_string(s):
    # Lowercase, remove non-alphanumeric for URLs
    return re.sub(r'[^a-z0-9]', '', s.lower())

def get_lyrics_azlyrics(song_title, artist_name):
    artist = clean_string(artist_name)
    title = clean_string(song_title)
    url = f"https://www.azlyrics.com/lyrics/{artist}/{title}.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return None  # fallback needed
    soup = BeautifulSoup(resp.text, "html.parser")
    # AZLyrics lyrics div has no class/id and comes after all divs with class ringtone
    divs = soup.find_all("div")
    for div in divs:
        if div.attrs == {}:
            lyrics = div.get_text(separator="\n").strip()
            if lyrics:
                return lyrics
    return None

def get_lyrics_lyricsdotcom(song_title, artist_name):
    # Search song on lyrics.com and scrape lyrics page if found
    base_search = "https://www.lyrics.com/serp.php?st={}&qtype=2"
    query = requests.utils.quote(song_title)
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(base_search.format(query), headers=headers)
    if resp.status_code != 200:
        return None
    soup = BeautifulSoup(resp.text, "html.parser")
    results = soup.select("td.tal.qx a")  # song title links
    for link in results:
        song_page = "https://www.lyrics.com" + link.get("href")
        resp2 = requests.get(song_page, headers=headers)
        if resp2.status_code != 200:
            continue
        soup2 = BeautifulSoup(resp2.text, "html.parser")
        lyrics_div = soup2.find("pre", attrs={"id": "lyric-body-text"})
        if lyrics_div:
            lyrics = lyrics_div.get_text(separator="\n").strip()
            if lyrics:
                return lyrics
    return None

async def fetch_lyrics(song_title, artist_name):
    # Try AZLyrics first
    lyrics = get_lyrics_azlyrics(song_title, artist_name)
    if lyrics:
        return lyrics
    # Fallback to Lyrics.com
    lyrics = get_lyrics_lyricsdotcom(song_title, artist_name)
    return lyrics

# Run single bot instance
async def run_bot(token):
    # Using discord.py-self style client (self_bot=True)
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    typer_tasks = {}
    lyrics_tasks = {}

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

    # Reaction related data and on_message
    @bot.event
    async def on_message(message):
        if message.author.id in blacklisted_users:
            return

        author_id = message.author.id
        author_roles = {role.id for role in getattr(message.author, "roles", [])} if hasattr(message.author, "roles") else set()
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

    snipes = {}

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return  # Optional: don't snipe own deletions
        snipes[message.channel.id] = message

    # Snipe command
    @bot.command()
    async def snipe(ctx):
        msg = snipes.get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe!")
            return
        content = msg.content or "[embed/image]"
        author = msg.author
        await ctx.send(f"Sniped message from {author}: {content}")

    # Blacklist commands
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
        # You can store emojis per role if you want
        await ctx.send(f"Watching role {role.name} with emojis: {''.join(emojis) if emojis else 'None'}")
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

    # Spam commands
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

    # Status commands
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

    # Typing command with stop feature
    @bot.command()
    async def typer(ctx, channel_id: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Invalid channel ID.")
            return
        await ctx.send(f"Typing forever in <#{channel_id}> (use !stoptyper to stop)")
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
            await ctx.send("Typing stopped.")
        else:
            await ctx.send("You don't have any active typer.")

    # Purge command: deletes a number of messages from a specific user
    @bot.command()
    async def purge(ctx, user: discord.User, amount: int):
        deleted = 0
        async for msg in ctx.channel.history(limit=1000):
            if deleted >= amount:
                break
            if msg.author == user:
                try:
                    await msg.delete()
                    deleted += 1
                except:
                    pass
        await ctx.send(f"Deleted {deleted} messages from {user.name}.", delete_after=5)
        await ctx.message.delete()

    # Help command (simple text + gif after)
    @bot.command(name="h")
    async def help_cmd(ctx, *, command_name: str = None):
        if command_name:
            # Show help for specific command if exists
            cmd = bot.get_command(command_name)
            if cmd:
                desc = cmd.help or "No description available."
                await ctx.send(f"**{cmd.name}**\n{desc}")
            else:
                await ctx.send("Command not found.")
            return

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
            "`!rpc`, `!statusall`, `!typer`, `!stoptyper`, `!lyrics`, `!stoplyrics`\n"
            "\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    # Lyrics status updating
    async def lyrics_status_loop(bot, ctx, song_title, artist_name):
        try:
            lyrics = await asyncio.to_thread(fetch_lyrics, song_title, artist_name)
            if not lyrics:
                await ctx.send("Lyrics not found.")
                return
            lines = [line.strip() for line in lyrics.split('\n') if line.strip()]
            # Put song title in status (big text) and lyrics line in small text
            # Discord activity small text is the "details", big text is the "state"
            # Use discord.Activity with type listening and set details=lyric line, state=song title
            i = 0
            while True:
                if i >= len(lines):
                    i = 0
                line = lines[i]
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    details=line[:128],  # small text (max 128)
                    state=song_title[:128]  # big text (max 128)
                )
                await bot.change_presence(activity=activity)
                i += 1
                await asyncio.sleep(random.uniform(1, 2))  # 1 to 2 seconds
        except Exception as e:
            print(f"Error fetching lyrics or updating status: {e}")
            await ctx.send(f"Error: {e}")

    @bot.command()
    async def lyrics(ctx, *, song_query: str):
        await ctx.message.delete()
        parts = song_query.split('-')
        if len(parts) == 2:
            artist_name = parts[0].strip()
            song_title = parts[1].strip()
        else:
            # If no dash, treat all as title and blank artist
            song_title = song_query.strip()
            artist_name = ""

        # If already running lyrics status, cancel it first for this user
        if ctx.author.id in lyrics_tasks:
            lyrics_tasks[ctx.author.id].cancel()

        # Start new lyrics status loop
        task = asyncio.create_task(lyrics_status_loop(bot, ctx, song_title, artist_name))
        lyrics_tasks[ctx.author.id] = task
        await ctx.send(f"Lyrics status started for **{song_title}** by *{artist_name}*")

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
            # Clear presence after stopping
            await bot.change_presence(activity=None)
            await ctx.send("Lyrics status stopped.")
        else:
            await ctx.send("No active lyrics status.")

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
