import discord
from discord.ext import commands
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
import re
import json

watched_users = {}  # user_id -> list of emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}
lyrics_tasks = {}

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

def get_lyrics(song_title, artist_name=""):
    # Format artist and title for AZLyrics
    artist_clean = re.sub(r'[^a-z0-9]', '', artist_name.lower())
    title_clean = re.sub(r'[^a-z0-9]', '', song_title.lower())
    if artist_clean:
        url = f"https://www.azlyrics.com/lyrics/{artist_clean}/{title_clean}.html"
    else:
        url = f"https://www.azlyrics.com/lyrics/{title_clean[0]}/{title_clean}.html"

    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except Exception:
        return None

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    # AZLyrics lyrics div has no class or id, it's the first div after the <div class="ringtone"> element
    for div in soup.find_all("div"):
        if div.attrs == {}:
            lyrics = div.get_text(separator="\n").strip()
            if lyrics:
                return lyrics
    return None

async def run_bot(token):
    intents = discord.Intents.none()  # For selfbot
    bot = commands.Bot(command_prefix="!", self_bot=True, intents=intents)
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

    # Snipe storage
    snipes = {}

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return  # Optionally don't snipe own deletions
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

    # Status commands (presence changing, big status)
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
            "`!lyrics <song> - <artist>`, `!stoplyrics`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    # Lyrics custom status commands

    async def set_custom_status(text):
        payload = {
            "activities": [
                {
                    "name": text[:128],
                    "type": 4,
                    "state": text[:128]
                }
            ],
            "status": "online",
            "since": 0,
            "afk": False
        }
        await bot.ws.send(json.dumps({
            "op": 3,
            "d": payload
        }))

    async def clear_custom_status():
        payload = {
            "activities": [],
            "status": "online",
            "since": 0,
            "afk": False
        }
        await bot.ws.send(json.dumps({
            "op": 3,
            "d": payload
        }))

    async def lyrics_loop(ctx, song_title, artist_name):
        lyrics = get_lyrics(song_title, artist_name)
        if not lyrics:
            await ctx.send("Lyrics not found.")
            return
        lines = [line.strip() for line in lyrics.split("\n") if line.strip()]
        if not lines:
            await ctx.send("No valid lyrics found.")
            return

        await ctx.send(f"Showing lyrics for **{song_title}** by *{artist_name}* in custom status.")

        try:
            while True:
                for line in lines:
                    await set_custom_status(line)
                    await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            await clear_custom_status()
            await ctx.send("Lyrics custom status stopped.")

    @bot.command()
    async def lyrics(ctx, *, query: str):
        parts = query.split(" - ", 1)
        song_title = parts[0].strip()
        artist_name = parts[1].strip() if len(parts) > 1 else ""

        # Cancel previous lyrics task if running
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()

        task = asyncio.create_task(lyrics_loop(ctx, song_title, artist_name))
        lyrics_tasks[ctx.author.id] = task

        await ctx.message.delete()

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
        else:
            await ctx.send("No active lyrics custom status.")
        await ctx.message.delete()

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
