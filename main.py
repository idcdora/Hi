import discord
from discord.ext import commands
import asyncio
import aiohttp
import random
import string
import time
import lyricsgenius

# Config
GENIUS_TOKEN = "ILkH7espIOfaqvoQ_PSxeUP9nsPonM7C65kb0bZL2l8lUh0B33vJiXN0whJ5mUKf"

# Globals
watched_users = {}  # user_id -> list of emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}
snipes = {}

# Temp mail domains
TEMPMAIL_DOMAINS = [
    "1secmail.com",
    "1secmail.org",
    "1secmail.net",
    "wwjmp.com",
    "esiix.com",
    "xojxe.com"
]
EMAILS_FILE = "emails.txt"

# Genius setup
genius = lyricsgenius.Genius(GENIUS_TOKEN)
genius.remove_section_headers = True
genius.skip_non_songs = True
genius.excluded_terms = ["(Remix)", "(Live)"]

# Helper: Save email to file with timestamp
def save_email(email):
    timestamp = time.time()
    with open(EMAILS_FILE, "a") as f:
        f.write(f"{email} {timestamp}\n")

# Helper: Load emails from file
def load_emails():
    emails = []
    try:
        with open(EMAILS_FILE, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 2:
                    email, ts = parts
                    emails.append((email, float(ts)))
    except FileNotFoundError:
        pass
    return emails

# Generate random username
def generate_random_username(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

# Load your tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

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

async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    typer_tasks = {}
    lyrics_tasks = {}

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

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return
        snipes[message.channel.id] = message

    # Commands

    # --- Moderation & React ---

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

    # --- Spamming ---

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

    # --- Status ---

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

    # --- Typing ---

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

    # --- Purge ---

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

    # --- Help ---

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
            "`!lyrics <song name or link>`, `!stoplyrics`\n"
            "\n"
            "**🔹 Temp Mail:**\n"
            "`!tempmail [count]`, `!checkmail <email>`, `!emails`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    # --- Lyrics (updates status with lyrics, line by line) ---

    async def lyrics_loop(bot, ctx, song):
        lyrics_lines = [line.strip() for line in song.lyrics.splitlines() if line.strip()]
        # Remove the title and artist lines if present
        if lyrics_lines and lyrics_lines[0].lower().startswith(song.title.lower()):
            lyrics_lines.pop(0)
        if lyrics_lines and lyrics_lines[0].lower().startswith(song.artist.lower()):
            lyrics_lines.pop(0)

        try:
            for line in lyrics_lines:
                await bot.change_presence(activity=discord.Game(name=line))
                await asyncio.sleep(7)  # wait 7 seconds before next line
        except asyncio.CancelledError:
            pass
        finally:
            # Clear presence after done
            await bot.change_presence(activity=None)

    @bot.command()
    async def lyrics(ctx, *, query: str):
        await ctx.message.delete()
        if ctx.author.id in lyrics_tasks:
            lyrics_tasks[ctx.author.id].cancel()
            lyrics_tasks.pop(ctx.author.id, None)

        try:
            song = genius.search_song(query)
            if not song:
                await ctx.send("No lyrics found for that song.")
                return
            await ctx.send(f"Lyrics found for **{song.title}** by *{song.artist}*. Updating status...")
            task = asyncio.create_task(lyrics_loop(bot, ctx, song))
            lyrics_tasks[ctx.author.id] = task
        except Exception as e:
            await ctx.send(f"Error fetching lyrics: {e}")

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
            await ctx.send("Stopped updating lyrics status.")
        else:
            await ctx.send("You have no active lyrics status.")
        await ctx.message.delete()

    # --- Temp mail commands ---

    @bot.command()
    async def tempmail(ctx, count: int = 1):
        emails = []
        for _ in range(count):
            username = generate_random_username()
            domain = random.choice(TEMPMAIL_DOMAINS)
            email = f"{username}@{domain}"
            emails.append(email)
            save_email(email)
        await ctx.send(f"Generated emails:\n" + "\n".join(emails))
        await ctx.message.delete()

    @bot.command()
    async def checkmail(ctx, email: str):
        try:
            username, domain = email.split("@")
        except ValueError:
            await ctx.send("Invalid email format!")
            return

        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await ctx.send(f"Failed to check email, HTTP status: {resp.status}")
                    return
                data = await resp.json()
                if not data:
                    await ctx.send(f"No emails found for {email}")
                    return
                messages = []
                for msg in data:
                    messages.append(f"From: {msg['from']}\nSubject: {msg['subject']}\nDate: {msg['date']}\nID: {msg['id']}\n---")
                await ctx.send(f"Emails for {email}:\n" + "\n".join(messages))
        await ctx.message.delete()

    @bot.command()
    async def emails(ctx):
        all_emails = load_emails()
        if not all_emails:
            await ctx.send("No stored emails.")
            await ctx.message.delete()
            return

        current_time = time.time()
        messages = []
        for email, timestamp in all_emails:
            time_left = max(0, 86400 - (current_time - timestamp))  # 24h expiration
            hours_left = int(time_left // 3600)
            messages.append(f"{email} - {hours_left}h left")

        chunk_size = 1900
        output = ""
        for line in messages:
            if len(output) + len(line) + 1 > chunk_size:
                await ctx.send(output)
                output = ""
            output += line + "\n"
        if output:
            await ctx.send(output)
        await ctx.message.delete()

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
