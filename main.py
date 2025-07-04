import discord
from discord.ext import commands
import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup

# === GLOBALS ===
tokens = []
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

watched_users = {}
watched_roles = set()
react_all_servers = {}
blacklisted_users = {}
last_deleted = {}
typing_tasks = {}
all_bots = []

# === HELPERS ===
async def fetch(session, url):
    async with session.get(url) as resp:
        return await resp.text()

async def fetch_json(session, url):
    async with session.get(url) as resp:
        return await resp.json()

async def scrape_genius_lyrics(url):
    async with aiohttp.ClientSession() as session:
        html = await fetch(session, url)
        soup = BeautifulSoup(html, "html.parser")
        lyrics_divs = soup.find_all("div", attrs={"data-lyrics-container": "true"})
        lyrics = "\n".join(div.get_text(separator="\n") for div in lyrics_divs)
        return lyrics.strip()

async def search_lyrics_api(song):
    async with aiohttp.ClientSession() as session:
        data = await fetch_json(session, f"https://api.lyrics.ovh/v1/{song}")
        return data.get("lyrics")

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

# === MAIN BOT ===
async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")

    @bot.event
    async def on_message_delete(message):
        last_deleted[message.channel.id] = message

    @bot.event
    async def on_message(message):
        author_id = message.author.id
        author_roles = {role.id for role in getattr(message.author, "roles", [])}
        should_react = (
            author_id in watched_users
            or watched_roles.intersection(author_roles)
            or (message.guild and message.guild.id in react_all_servers)
        )

        if should_react:
            emojis = []
            if author_id in watched_users:
                emojis = watched_users[author_id]
            elif message.guild and message.guild.id in react_all_servers:
                emojis = react_all_servers[message.guild.id]
            for emoji in emojis:
                try:
                    await message.add_reaction(emoji)
                except Exception as e:
                    print("Reaction error:", e)
        await bot.process_commands(message)

    # === ALL COMMANDS ===
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
        watched_roles.add(role.id)
        await ctx.send(f"Watching role {role.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.discard(role.id)
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
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)
        await ctx.message.delete()

    @bot.command()
    async def massdmspam(ctx, message, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end_time = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end_time:
            await mass_dm(ctx.guild, message)
        await ctx.send("Done mass DM spam.")
        await ctx.message.delete()

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")
        await ctx.message.delete()

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
        await ctx.send(f"Typing forever in <#{channel_id}>")
        async def typing_loop():
            while True:
                async with channel.typing():
                    await asyncio.sleep(5)
        task = asyncio.create_task(typing_loop())
        typing_tasks[channel_id] = task
        await ctx.message.delete()

    @bot.command()
    async def stoptyper(ctx, channel_id: int):
        task = typing_tasks.get(channel_id)
        if task:
            task.cancel()
            await ctx.send(f"Stopped typing in <#{channel_id}>.")
        else:
            await ctx.send("No typing running for that channel.")
        await ctx.message.delete()

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
    async def purge(ctx, user: discord.User, limit: int = 100):
        await ctx.channel.purge(limit=limit, check=lambda m: m.author == user)
        await ctx.send(f"Purged messages from {user.name}.")
        await ctx.message.delete()

    @bot.command()
    async def snipe(ctx):
        msg = last_deleted.get(ctx.channel.id)
        if msg and msg.content != ctx.message.content:
            await ctx.send(f"Sniped: `{msg.author}`: {msg.content}")
        else:
            await ctx.send("No message to snipe.")
        await ctx.message.delete()

    @bot.command()
    async def lyrics(ctx, *, arg):
        await ctx.message.delete()
        if re.match(r"https?://(www\.)?genius\.com/.*", arg):
            lyrics = await scrape_genius_lyrics(arg)
        else:
            lyrics = await search_lyrics_api(arg)
        if lyrics:
            snippet = (lyrics[:100] + "...") if len(lyrics) > 100 else lyrics
            await ctx.send(f"🎵 Lyrics:\n```{snippet}```")
            await bot.change_presence(activity=discord.Game(name=snippet))
        else:
            await ctx.send("Couldn't find lyrics.")

    @bot.command(name="h")
    async def help_cmd(ctx):
        await ctx.message.delete()
        help_text = (
            "**Commands**\n\n"
            "**🔹 Reacting:** `!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n"
            "**🔹 Spamming:** `!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n"
            "**🔹 Status:** `!rpc`, `!statusall`, `!typer`, `!stoptyper`\n"
            "**🔹 Moderation:** `!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "**🔹 Music:** `!lyrics <song name or genius link>`\n\n"
            "*:3*"
        )
        await ctx.send(help_text)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
