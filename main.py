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
watched_users = {}  # user_id -> list of emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
blacklisted_users = {}

watched_channel = 1077296245569237114  # Your ID here

locked_group_chats = {}  # gc_id: set of user_ids locked in

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
        super().__init__(command_prefix="!", self_bot=True)
        self.token = token
        self.lyric_task = None
        self.typer_tasks = {}
        all_bots.append(self)

    async def on_ready(self):
        print(f"[+] Logged in as {self.user}")
        token_user_ids.add(self.user.id)

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
            except Exception:
                pass

        if message.content.startswith("[[SPAMALL_TRIGGER]]::") and message.author != self.user:
            try:
                _, count, msg = message.content.split("::", 2)
                for _ in range(int(count)):
                    await message.channel.send(msg)
                    await asyncio.sleep(0.1)
            except Exception:
                pass

        # Locked GC monitor reinvites on leave
        if message.guild is None:  # DMs or group DM
            gc_id = message.channel.id
            if gc_id in locked_group_chats:
                locked_users = locked_group_chats[gc_id]
                # If author left GC, re-add them immediately (can't kick, but re-adding)
                # Discord selfbots can't manage group DMs membership via API
                # So this will be no-op or a placeholder

        await self.process_commands(message)

    async def on_message_delete(self, message):
        pass  # You can add snipe functionality here if desired

    # Commands
    @commands.command()
    async def snipe(self, ctx):
        await ctx.send("Nothing to snipe!")

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
            await self.mass_dm(ctx.guild, message)
        await ctx.send("Done mass DM spam.")

    async def mass_dm(self, guild, message):
        for member in guild.members:
            if not member.bot:
                try:
                    await member.send(message)
                except:
                    pass

    @commands.command()
    async def webhookspam(self, ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await self.webhook_spam(url, message, count)
        await ctx.send("Done.")

    async def webhook_spam(self, url, message, count):
        async with aiohttp.ClientSession() as session:
            for _ in range(count):
                try:
                    await session.post(url, json={"content": message})
                except:
                    pass

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
            "**Commands:**\n\n"
            "**🔹 Reacting:**\n"
            "`!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n\n"
            "**🔹 Spamming:**\n"
            "`!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n\n"
            "**🔹 Status:**\n"
            "`!rpc`, `!statusall`, `!typer`, `!stoptyper`\n\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n\n"
            "**🔹 Lyrics:**\n"
            "`!lyrics <Song> - <Artist>`, `!stoplyrics`\n\n"
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
                        await asyncio.sleep(1.5)
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

    # Control commands (only your ID)
    async def cog_check(self, ctx):
        if ctx.author.id != watched_channel:
            return False
        return True

    @commands.command()
    async def controlrpc(self, ctx, activity_type: str, *, activity_message: str):
        await ctx.message.delete()
        await self.rpc(ctx, activity_type, activity_message)

    @commands.command()
    async def controlsay(self, ctx, *, message: str):
        await ctx.message.delete()
        await ctx.send(message)

    @commands.command()
    async def gclock(self, ctx, target: str, gc_id: int):
        await ctx.message.delete()
        channel = self.get_channel(gc_id)
        if not channel or not channel.is_group():
            await ctx.send("Invalid group chat ID.")
            return
        if gc_id not in locked_group_chats:
            locked_group_chats[gc_id] = set()
        if target.lower() == "all":
            for member in channel.recipients:
                locked_group_chats[gc_id].add(member.id)
        else:
            if target.startswith("<@") and target.endswith(">"):
                user_id = int(target.strip("<@!>"))
            else:
                try:
                    user_id = int(target)
                except:
                    await ctx.send("Invalid user mention or ID.")
                    return
            locked_group_chats[gc_id].add(user_id)
        await ctx.send("Locked user(s) in the group chat.")

    @commands.command()
    async def gcunlock(self, ctx, target: str, gc_id: int):
        await ctx.message.delete()
        if gc_id not in locked_group_chats:
            await ctx.send("Group chat not locked.")
            return
        if target.lower() == "all":
            locked_group_chats[gc_id].clear()
        else:
            if target.startswith("<@") and target.endswith(">"):
                user_id = int(target.strip("<@!>"))
            else:
                try:
                    user_id = int(target)
                except:
                    await ctx.send("Invalid user mention or ID.")
                    return
            locked_group_chats[gc_id].discard(user_id)
        await ctx.send("Unlocked user(s) in the group chat.")

    @commands.command()
    async def gcview(self, ctx, gc_id: int):
        if gc_id not in locked_group_chats or not locked_group_chats[gc_id]:
            await ctx.send("No locked users in this group chat.")
            return
        users = locked_group_chats[gc_id]
        await ctx.send(f"Locked users in GC {gc_id}: {', '.join(str(u) for u in users)}")

async def run_bot(token):
    bot = MyBot(token)
    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
