import discord
from discord.ext import commands
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
import re

# Load tokens from tokens.txt (one token per line)
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

all_bots = []
watched_users = {}  # user_id -> list of emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
blacklisted_users = {}

watched_channel = 1077296245569237114

# === Lyrics API 1: AZLyrics ===
def get_lyrics_azlyrics(song_title, artist_name):
    artist = re.sub(r'[^a-z0-9]', '', artist_name.lower())
    title = re.sub(r'[^a-z0-9]', '', song_title.lower())
    url = f"https://www.azlyrics.com/lyrics/{artist}/{title}.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        divs = soup.find_all("div")
        for div in divs:
            if div.attrs == {}:  # lyrics div no class/id
                lyrics = div.get_text(separator="\n").strip()
                return lyrics
    except Exception:
        return None
    return None

# === Lyrics API 2: LyricsFreak ===
def get_lyrics_lyricsfreak(song_title, artist_name):
    artist = re.sub(r'[^a-z0-9]', '', artist_name.lower())
    title = re.sub(r'[^a-z0-9]', '', song_title.lower())
    url = f"https://www.lyricsfreak.com/{artist[0]}/{artist}/{title}-lyrics.html"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        lyrics_div = soup.find("div", class_="lyrictxt js-lyrics js-share-text-content")
        if lyrics_div:
            lyrics = lyrics_div.get_text(separator="\n").strip()
            return lyrics
    except Exception:
        return None
    return None

# === Utility to try all lyric APIs in order ===
def get_lyrics(song_title, artist_name):
    lyrics = get_lyrics_azlyrics(song_title, artist_name)
    if lyrics:
        return lyrics
    lyrics = get_lyrics_lyricsfreak(song_title, artist_name)
    if lyrics:
        return lyrics
    return None

# === Custom status updater ===
async def set_custom_status(token, text):
    url = "https://discord.com/api/v10/users/@me/settings"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    payload = {
        "custom_status": {
            "text": text[:128],  # max 128 chars
            "emoji_name": None
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return True
            else:
                print(f"Failed to update custom status: {resp.status}")
                return False

async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    lyric_task = None

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

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

    snipes = {}

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return
        snipes[message.channel.id] = message

    @bot.command()
    async def snipe(ctx):
        msg = snipes.get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe!")
            return
        content = msg.content or "[embed/image]"
        author = msg.author
        await ctx.send(f"Sniped message from {author}: {content}")

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

    async def mass_dm(guild, message):
        for member in guild.members:
            if not member.bot:
                try:
                    await member.send(message)
                except:
                    pass

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")

    async def webhook_spam(url, message, count):
        async with aiohttp.ClientSession() as session:
            for _ in range(count):
                try:
                    await session.post(url, json={"content": message})
                except:
                    pass

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
                    activity = discord.Streaming(name=activity_message, url="https://twitch.tv/idcdora2")
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
        await ctx.send(f"Typing forever in <#{channel_id}> (use !stoptyper to stop)")
        task = asyncio.create_task(typing_loop(channel))
        typer_tasks[ctx.author.id] = task

    typer_tasks = {}

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
            "`!rpc`, `!statusall`, `!typer`, `!stoptyper`\n"
            "\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "\n"
            "**🔹 Lyrics:**\n"
            "`!lyrics <Song> - <Artist>`, `!stoplyrics`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    # === Lyrics custom status commands ===
    @bot.command()
    async def lyrics(ctx, *, song: str):
        nonlocal lyric_task
        if " - " not in song:
            await ctx.send("Please provide song and artist like `Song Title - Artist`")
            return
        song_name, artist_name = song.split(" - ", 1)
        await ctx.message.delete()
        lyrics = get_lyrics(song_name, artist_name)
        if not lyrics:
            await ctx.send("Lyrics not found on any source.")
            return
        lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
        if not lines:
            await ctx.send("No valid lyrics lines found.")
            return
        if lyric_task:
            lyric_task.cancel()
        async def update_status_loop():
            try:
                while True:
                    for line in lines:
                        await set_custom_status(bot.http.token, line)
                        await asyncio.sleep(1.5)  # update every 1.5 seconds
            except asyncio.CancelledError:
                await set_custom_status(bot.http.token, "")  # Clear status on stop
        lyric_task = asyncio.create_task(update_status_loop())
        await ctx.send("Started updating custom status with lyrics!")

    @bot.command()
    async def stoplyrics(ctx):
        nonlocal lyric_task
        await ctx.message.delete()
        if lyric_task:
            lyric_task.cancel()
            lyric_task = None
            await set_custom_status(bot.http.token, "")  # Clear status
            await ctx.send("Stopped lyrics custom status update.")
        else:
            await ctx.send("No lyrics update running.")

    # === Control commands only usable by your user ID (watched_channel) ===
    @bot.command()
    async def controlrpc(ctx, target_user_id: int, activity_type: str, *, activity_message: str):
        if ctx.author.id != watched_channel:
            return
        await ctx.message.delete()

        target_bot = None
        for b in all_bots:
            if b.user and b.user.id == target_user_id:
                target_bot = b
                break

        if not target_bot:
            await ctx.send(f"User with ID {target_user_id} not found among bots.")
            return

        types = {
            "playing": discord.Game,
            "streaming": discord.Streaming,
            "listening": discord.Activity,
            "watching": discord.Activity,
            "competing": discord.Activity
        }
        activity_type = activity_type.lower()
        if activity_type == "streaming":
            activity = discord.Streaming(name=activity_message, url="https://twitch.tv/idcdora2")
        elif activity_type in types:
            if activity_type == "playing":
                activity = types[activity_type](name=activity_message)
            else:
                enum_type = getattr(discord.ActivityType, activity_type)
                activity = discord.Activity(type=enum_type, name=activity_message)
        else:
            await ctx.send("Invalid activity type.")
            return

        try:
            await target_bot.change_presence(activity=activity)
            await ctx.send(f"Changed presence of {target_bot.user} to {activity_type} {activity_message}")
        except Exception as e:
            await ctx.send(f"Failed to change presence: {e}")

    @bot.command()
    async def controlsay(ctx, target_user_id: int, *, message):
        if ctx.author.id != watched_channel:
            return
        
        await ctx.message.delete()

        
        target_bot = None
        for b in all_bots:
            if b.user and b.user.id == target_user_id:
                target_bot = b
                break

        if not target_bot:
            await ctx.send(f"User with ID {target_user_id} not found among bots.")
            return

        
        try:
            channel = target_bot.get_channel(ctx.channel.id)
            if not channel:
                # fallback: fetch channel by ID if not cached
                channel = await target_bot.fetch_channel(ctx.channel.id)
            await channel.send(message)
        except Exception as e:
            await ctx.send(f"Failed to send message as user {target_user_id}: {e}")

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
