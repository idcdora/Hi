import discord
from discord.ext import commands
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
import re

with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

all_bots = []
watched_users = {}
watched_roles = set()
react_all_servers = {}
token_user_ids = set()
blacklisted_users = {}
watched_channel = 1077296245569237114

locked_gcs = {}

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
            if div.attrs == {}:
                lyrics = div.get_text(separator="\n").strip()
                return lyrics
    except Exception:
        return None
    return None

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

def get_lyrics(song_title, artist_name):
    lyrics = get_lyrics_azlyrics(song_title, artist_name)
    if lyrics:
        return lyrics
    lyrics = get_lyrics_lyricsfreak(song_title, artist_name)
    if lyrics:
        return lyrics
    return None

async def set_custom_status(token, text):
    url = "https://discord.com/api/v10/users/@me/settings"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    payload = {
        "custom_status": {
            "text": text[:128],
            "emoji_name": None
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return True
            else:
                return False

class MyBot(commands.Bot):
    def __init__(self, token):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", self_bot=True, intents=intents)
        self.token = token
        self.lyric_task = None
        self.typer_tasks = {}
        self.snipes = {}

    async def setup_hook(self):
        self.loop.create_task(self.locked_gc_monitor_loop())

    async def locked_gc_monitor_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            for gc_id, user_ids in locked_gcs.items():
                guild = self.get_guild(gc_id)
                if not guild:
                    continue
                for user_id in list(user_ids):
                    member = guild.get_member(user_id)
                    if member is None:
                        # re-add logic if needed, actual re-add not possible via API
                        pass
            await asyncio.sleep(5)

async def run_bot(token):
    bot = MyBot(token)
    all_bots.append(bot)

    @bot.event
    async def on_ready():
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
            except Exception:
                pass
        await bot.process_commands(message)

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return
        bot.snipes[message.channel.id] = message

    @bot.command()
    async def snipe(ctx):
        msg = bot.snipes.get(ctx.channel.id)
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
            await ctx.send("Provide emojis.")
            return
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Reacting to {user.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unreact(ctx, user: discord.User):
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")
        await ctx.message.delete()

    @bot.command()
    async def watchrole(ctx, role: discord.Role):
        watched_roles.add(role.id)
        await ctx.send(f"Watching role {role.name}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching role {role.name}")
        await ctx.message.delete()

    @bot.command()
    async def reactall(ctx, server_id: int, *emojis):
        if not emojis:
            await ctx.send("Provide emojis.")
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
    async def massdmspam(ctx, message: str, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end_time = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end_time:
            for member in ctx.guild.members:
                if not member.bot:
                    try:
                        await member.send(message)
                    except:
                        pass
        await ctx.send("Done mass DM spam.")

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        async with aiohttp.ClientSession() as session:
            for _ in range(count):
                try:
                    await session.post(url, json={"content": message})
                except:
                    pass
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
        await ctx.send(f"Typing forever in <#{channel_id}> (use !stoptyper to stop)")
        task = asyncio.create_task(typing_loop(channel))
        bot.typer_tasks[ctx.author.id] = task

    async def typing_loop(channel):
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @bot.command()
    async def stoptyper(ctx):
        task = bot.typer_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            bot.typer_tasks.pop(ctx.author.id, None)
            await ctx.send("Typing stopped.")
        else:
            await ctx.send("No active typer.")

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

    @bot.command()
    async def gclock(ctx, target: str, gc_id: int):
        guild = bot.get_guild(gc_id)
        if not guild:
            await ctx.send("Invalid group chat ID.")
            return
        if gc_id not in locked_gcs:
            locked_gcs[gc_id] = set()
        if target.lower() == "all":
            for member in guild.members:
                locked_gcs[gc_id].add(member.id)
            await ctx.send(f"Locked all members in group chat {gc_id}.")
        else:
            try:
                user = await commands.MemberConverter().convert(ctx, target)
                locked_gcs[gc_id].add(user.id)
                await ctx.send(f"Locked {user} in group chat {gc_id}.")
            except:
                await ctx.send("Invalid user.")
        await ctx.message.delete()

    @bot.command()
    async def gcunlock(ctx, target: str, gc_id: int):
        if gc_id not in locked_gcs:
            await ctx.send("Group chat is not locked.")
            return
        if target.lower() == "all":
            locked_gcs[gc_id].clear()
            await ctx.send(f"Unlocked all members in group chat {gc_id}.")
        else:
            try:
                user = await commands.MemberConverter().convert(ctx, target)
                locked_gcs[gc_id].discard(user.id)
                await ctx.send(f"Unlocked {user} in group chat {gc_id}.")
            except:
                await ctx.send("Invalid user.")
        await ctx.message.delete()

    @bot.command()
    async def gcview(ctx, gc_id: int):
        if gc_id not in locked_gcs or not locked_gcs[gc_id]:
            await ctx.send("No locked users in this group chat.")
            return
        user_mentions = [f"<@{uid}>" for uid in locked_gcs[gc_id]]
        await ctx.send(f"Locked users in GC {gc_id}:\n" + ", ".join(user_mentions))
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
            "**🔹 Group Chat Lock:**\n"
            "`!gclock`, `!gcunlock`, `!gcview`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    @bot.command()
    async def lyrics(ctx, *, song: str):
        if " - " not in song:
            await ctx.send("Provide song and artist like `Song Title - Artist`")
            return
        song_name, artist_name = song.split(" - ", 1)
        await ctx.message.delete()
        lyrics = get_lyrics(song_name, artist_name)
        if not lyrics:
            await ctx.send("Lyrics not found.")
            return
        lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
        if not lines:
            await ctx.send("No lyrics lines found.")
            return
        if bot.lyric_task:
            bot.lyric_task.cancel()
        async def update_status_loop():
            try:
                while True:
                    for line in lines:
                        await set_custom_status(bot.token, line)
                        await asyncio.sleep(1.5)
            except asyncio.CancelledError:
                await set_custom_status(bot.token, "")
        bot.lyric_task = asyncio.create_task(update_status_loop())
        await ctx.send("Started lyrics status update!")

    @bot.command()
    async def stoplyrics(ctx):
        await ctx.message.delete()
        if bot.lyric_task:
            bot.lyric_task.cancel()
            bot.lyric_task = None
            await set_custom_status(bot.token, "")
            await ctx.send("Stopped lyrics status.")
        else:
            await ctx.send("No active lyrics status.")

    await bot.start(bot.token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
