import discord
from discord.ext import commands
import asyncio
import requests
from bs4 import BeautifulSoup
import re

# Load tokens from tokens.txt
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

all_bots = []
lyrics_tasks = {}  # user_id -> asyncio.Task for lyrics status updates

# Util to fetch lyrics from AZLyrics
def get_lyrics(song_title, artist_name=""):
    artist_clean = re.sub(r'[^a-z0-9]', '', artist_name.lower())
    title_clean = re.sub(r'[^a-z0-9]', '', song_title.lower())
    if artist_clean:
        url = f"https://www.azlyrics.com/lyrics/{artist_clean}/{title_clean}.html"
    else:
        # fallback folder from first letter of title
        url = f"https://www.azlyrics.com/lyrics/{title_clean[0]}/{title_clean}.html"

    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except Exception:
        return None

    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    for div in soup.find_all("div"):
        if div.attrs == {}:
            lyrics = div.get_text(separator="\n").strip()
            if lyrics:
                return lyrics
    return None

# Run each bot with a token
async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    snipes = {}
    watched_users = {}
    watched_roles = set()
    react_all_servers = {}
    blacklisted_users = {}
    typer_tasks = {}

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user} (ID: {bot.user.id})")

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return  # Don't snipe own messages
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
        # Emojis per role not stored here; you can extend if needed
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

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")

    # Typing commands
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

    # Purge command: deletes messages from user
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

    # Help command with simple text and gif after
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

    # Lyrics status update commands

    async def lyrics_status_loop(ctx, song_title, artist_name):
        lyrics = get_lyrics(song_title, artist_name)
        if not lyrics:
            await ctx.send("Lyrics not found.")
            return

        lines = [line.strip() for line in lyrics.split("\n") if line.strip()]
        if not lines:
            await ctx.send("No valid lyrics lines found.")
            return

        # Show song title big text first
        await bot.change_presence(activity=discord.Game(name=f"🎵 {song_title}"))
        await ctx.send(f"Now showing lyrics for **{song_title}** by *{artist_name}* in status.")

        try:
            while True:
                for line in lines:
                    # Status max length is 128, truncate if needed
                    await bot.change_presence(activity=discord.Game(name=line[:128]))
                    await asyncio.sleep(1.5)
        except asyncio.CancelledError:
            await bot.change_presence(activity=None)
            await ctx.send("Lyrics status update stopped.")

    @bot.command()
    async def lyrics(ctx, *, query: str):
        parts = query.split(" - ", 1)
        song_title = parts[0].strip()
        artist_name = parts[1].strip() if len(parts) > 1 else ""

        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()

        task = asyncio.create_task(lyrics_status_loop(ctx, song_title, artist_name))
        lyrics_tasks[ctx.author.id] = task

        await ctx.message.delete()

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
        else:
            await ctx.send("You don't have any active lyrics status.")
        await ctx.message.delete()

    # Process other commands and reactions if needed
    @bot.event
    async def on_message(message):
        # Reacting logic
        if message.author.id in blacklisted_users:
            return

        author_id = message.author.id
        author_roles = {role.id for role in getattr(message.author, "roles", [])}
        should_react = (
            author_id == bot.user.id or
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

        # Spamall trigger
        if message.content.startswith("[[SPAMALL_TRIGGER]]::") and message.author != bot.user:
            try:
                _, count, msg = message.content.split("::", 2)
                for _ in range(int(count)):
                    await message.channel.send(msg)
                    await asyncio.sleep(0.1)
            except Exception as e:
                print("SPAMALL error:", e)

        await bot.process_commands(message)

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
