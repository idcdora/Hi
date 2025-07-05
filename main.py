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
lyric_tasks = {}
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
    except:
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
    except:
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
    headers = {"Authorization": token, "Content-Type": "application/json"}
    payload = {"custom_status": {"text": text[:128], "emoji_name": None}}
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json=payload, headers=headers) as resp:
            return resp.status == 200

class MyBot(commands.Bot):
    def __init__(self, token):
        super().__init__(command_prefix="!", self_bot=True)
        self.token = token
        self.lyric_task = None
        self.typer_tasks = {}
        self.locked_gc_users = {}

    async def on_ready(self):
        token_user_ids.add(self.user.id)
        all_bots.append(self)
        print(f"[+] Logged in as {self.user}")

    async def on_message(self, message):
        if message.author.id in blacklisted_users:
            return
        author_id = message.author.id
        author_roles = {role.id for role in getattr(message.author, "roles", [])}
        should_react = (
            author_id == self.user.id or
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
            except:
                pass
        if message.content.startswith("[[SPAMALL_TRIGGER]]::") and message.author != self.user:
            try:
                _, count, msg = message.content.split("::", 2)
                for _ in range(int(count)):
                    await message.channel.send(msg)
                    await asyncio.sleep(0.1)
            except:
                pass
        await self.process_commands(message)

    async def on_message_delete(self, message):
        if message.author.id == self.user.id:
            return
        if not hasattr(self, 'snipes'):
            self.snipes = {}
        self.snipes[message.channel.id] = message

    @commands.command()
    async def snipe(self, ctx):
        msg = getattr(self, 'snipes', {}).get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe!")
            return
        content = msg.content or "[embed/image]"
        author = msg.author
        await ctx.send(f"Sniped message from {author}: {content}")

    @commands.command()
    async def blacklist(self, ctx, user_id: int):
        blacklisted_users[user_id] = True
        await ctx.send(f"User {user_id} blacklisted.")
        await ctx.message.delete()

    @commands.command()
    async def unblacklist(self, ctx, user_id: int):
        blacklisted_users.pop(user_id, None)
        await ctx.send(f"User {user_id} unblacklisted.")
        await ctx.message.delete()

    @commands.command()
    async def react(self, ctx, user: discord.User, *emojis):
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Now reacting to {user.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @commands.command()
    async def unreact(self, ctx, user: discord.User):
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")
        await ctx.message.delete()

    @commands.command()
    async def watchrole(self, ctx, role: discord.Role, *emojis):
        watched_roles.add(role.id)
        await ctx.send(f"Watching role {role.name} with emojis: {''.join(emojis) if emojis else 'None'}")
        await ctx.message.delete()

    @commands.command()
    async def unwatchrole(self, ctx, role: discord.Role):
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching role {role.name}")
        await ctx.message.delete()

    @commands.command()
    async def reactall(self, ctx, server_id: int, *emojis):
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
        react_all_servers[server_id] = list(emojis)
        await ctx.send(f"Reacting in server {server_id} with {''.join(emojis)}")
        await ctx.message.delete()

    @commands.command()
    async def unreactall(self, ctx, server_id: int):
        react_all_servers.pop(server_id, None)
        await ctx.send(f"Stopped reacting in server {server_id}")
        await ctx.message.delete()

    @commands.command()
    async def spam(self, ctx, *, args):
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spam <message> <count>")
            return
        await ctx.message.delete()
        for _ in range(count):
            await ctx.send(msg)

    @commands.command()
    async def spamall(self, ctx, *, args):
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spamall <message> <count>")
            return
        await ctx.message.delete()
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)

    @commands.command()
    async def massdmspam(self, ctx, message, seconds: int):
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

    @commands.command()
    async def webhookspam(self, ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        async with aiohttp.ClientSession() as session:
            for _ in range(count):
                try:
                    await session.post(url, json={"content": message})
                except:
                    pass
        await ctx.send("Done.")

    @commands.command()
    async def rpc(self, ctx, activity_type: str, *, activity_message: str):
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
        await self.change_presence(activity=activity)
        await ctx.send(f"Status set to {activity_type} {activity_message}")
        await ctx.message.delete()

    @commands.command()
    async def statusall(self, ctx, activity_type: str, *, activity_message: str):
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

    @commands.command()
    async def typer(self, ctx, channel_id: int):
        channel = self.get_channel(channel_id)
        if not channel:
            await ctx.send("Invalid channel ID.")
            return
        await ctx.send(f"Typing forever in <#{channel_id}> (use !stoptyper to stop)")
        task = asyncio.create_task(self.typing_loop(channel))
        self.typer_tasks[ctx.author.id] = task

    async def typing_loop(self, channel):
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @commands.command()
    async def stoptyper(self, ctx):
        task = self.typer_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            self.typer_tasks.pop(ctx.author.id, None)
            await ctx.send("Typing stopped.")
        else:
            await ctx.send("You don't have any active typer.")

    @commands.command()
    async def purge(self, ctx, user: discord.User, amount: int):
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

    @commands.command(name="h")
    async def help_cmd(self, ctx):
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

    @commands.command()
    async def lyrics(self, ctx, *, song: str):
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
        if self.lyric_task:
            self.lyric_task.cancel()
        async def update_status_loop():
            try:
                while True:
                    for line in lines:
                        await set_custom_status(self.token, line)
                        await asyncio.sleep(1)
            except asyncio.CancelledError:
                await set_custom_status(self.token, "")
        self.lyric_task = asyncio.create_task(update_status_loop())
        await ctx.send("Started updating custom status with lyrics!")

    @commands.command()
    async def stoplyrics(self, ctx):
        await ctx.message.delete()
        if self.lyric_task:
            self.lyric_task.cancel()
            self.lyric_task = None
            await set_custom_status(self.token, "")
            await ctx.send("Stopped lyrics custom status update.")
        else:
            await ctx.send("No lyrics update running.")

    @commands.command()
    async def controlrpc(self, ctx, target: discord.User, activity_type: str, *, activity_message: str):
        if ctx.author.id != watched_channel:
            return
        bots = [b for b in all_bots if b.user.id == target.id]
        if not bots:
            await ctx.send("Target bot not found.")
            return
        b = bots[0]
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
        await b.change_presence(activity=activity)
        await ctx.message.delete()

    @commands.command()
    async def controlsay(self, ctx, target: discord.User, *, message: str):
        if ctx.author.id != watched_channel:
            return
        bots = [b for b in all_bots if b.user.id == target.id]
        if not bots:
            await ctx.send("Target bot not found.")
            return
        b = bots[0]
        await ctx.message.delete()
        await b.get_channel(ctx.channel.id).send(message)

    @commands.command()
    async def gclock(self, ctx, user: str, gc_id: int):
        if ctx.author.id != watched_channel:
            return
        guild = self.get_guild(gc_id)
        if not guild:
            await ctx.send("Invalid GC ID.")
            return
        if gc_id not in locked_gcs:
            locked_gcs[gc_id] = set()
        if user.lower() == "all":
            members = [m for m in guild.members if not m.bot]
            locked_gcs[gc_id].update({m.id for m in members})
            await ctx.send(f"Locked all users in GC {gc_id}")
        else:
            member = guild.get_member_named(user)
            if member:
                locked_gcs[gc_id].add(member.id)
                await ctx.send(f"Locked {member.name} in GC {gc_id}")
            else:
                await ctx.send("User not found in that GC.")

    @commands.command()
    async def gcunlock(self, ctx, user: str, gc_id: int):
        if ctx.author.id != watched_channel:
            return
        if gc_id not in locked_gcs:
            await ctx.send("No users locked in this GC.")
            return
        if user.lower() == "all":
            locked_gcs[gc_id].clear()
            await ctx.send(f"Unlocked all users in GC {gc_id}")
        else:
            for uid in list(locked_gcs[gc_id]):
                member = self.get_user(uid)
                if member and member.name.lower() == user.lower():
                    locked_gcs[gc_id].discard(uid)
                    await ctx.send(f"Unlocked {member.name} in GC {gc_id}")
                    break
            else:
                await ctx.send("User not locked in this GC.")

    @commands.command()
    async def gcview(self, ctx, gc_id: int):
        if ctx.author.id != watched_channel:
            return
        if gc_id not in locked_gcs or not locked_gcs[gc_id]:
            await ctx.send("No locked users in this GC.")
            return
        locked_names = []
        for uid in locked_gcs[gc_id]:
            user = self.get_user(uid)
            if user:
                locked_names.append(user.name)
        await ctx.send(f"Locked users in GC {gc_id}: {', '.join(locked_names)}")

    async def locked_gc_monitor_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            for gc_id, locked_users_set in locked_gcs.items():
                guild = self.get_guild(gc_id)
                if not guild:
                    continue
                current_members = {m.id for m in guild.members}
                for user_id in list(locked_users_set):
                    if user_id not in current_members:
                        member = self.get_user(user_id)
                        try:
                            await guild.add_member(member)
                        except:
                            pass
            await asyncio.sleep(5)

async def run_bot(token):
    intents = discord.Intents.none()
    bot = MyBot(token)
    bot.loop.create_task(bot.locked_gc_monitor_loop())
    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

if __name__ == "__main__":
    asyncio.run(main())
