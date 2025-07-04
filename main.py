import discord
from discord.ext import commands
import asyncio
import aiohttp
import requests
import random
import time
import os

# ================ Globals ================
watched_users = {}  # user_id -> emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> emojis
blacklisted_users = {}

temp_emails = []  # (email, expiry_time)

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

# ================ Selfbot Runner ================
async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    typer_tasks = {}
    lyrics_tasks = {}

    # ============ Events ==============
    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")

    snipes = {}
    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return
        snipes[message.channel.id] = message

    @bot.event
    async def on_message(message):
        await bot.process_commands(message)

    # ============ Help ================
    @bot.command(name="h")
    async def help_cmd(ctx):
        help_message = (
            "**Commands:**\n"
            "\n"
            "**🔹 Reacting:**\n"
            "`!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n"
            "**🔹 Spamming:**\n"
            "`!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n"
            "**🔹 Status:**\n"
            "`!rpc`, `!statusall`, `!typer`, `!stoptyper`, `!lyrics`, `!stoplyrics`\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "**🔹 Temp Mail:**\n"
            "`!tempmail [amount]`, `!checkmail <email>`, `!emails`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    # ============= Snipe ==============
    @bot.command()
    async def snipe(ctx):
        msg = snipes.get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe!")
            return
        await ctx.send(f"Sniped message from {msg.author}: {msg.content}")
        await ctx.message.delete()

    # ============= Blacklist ==========
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

    # ============= React ==============
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
    async def watchrole(ctx, role: discord.Role, *emojis):
        watched_roles.add(role.id)
        await ctx.send(f"Watching role {role.name}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching role {role.name}")
        await ctx.message.delete()

    # ============= Spam ==============
    async def mass_dm(guild, message):
        for member in guild.members:
            if not member.bot:
                try:
                    await member.send(message)
                except:
                    pass

    @bot.command()
    async def spam(ctx, *, args):
        msg, count = args.rsplit(" ", 1)
        for _ in range(int(count)):
            await ctx.send(msg)
        await ctx.message.delete()

    @bot.command()
    async def spamall(ctx, *, args):
        msg, count = args.rsplit(" ", 1)
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)
        await ctx.message.delete()

    @bot.command()
    async def massdmspam(ctx, message, seconds: int):
        end = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end:
            await mass_dm(ctx.guild, message)
        await ctx.send("Mass DM done.")

    async def webhook_spam(url, message, count):
        async with aiohttp.ClientSession() as s:
            for _ in range(count):
                await s.post(url, json={"content": message})

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await webhook_spam(url, message, count)
        await ctx.send("Webhook spam done.")

    # ============= Status & Typing ==============
    @bot.command()
    async def rpc(ctx, activity_type, *, msg):
        await bot.change_presence(activity=discord.Game(name=msg))
        await ctx.send(f"Status set to {activity_type} {msg}")
        await ctx.message.delete()

    @bot.command()
    async def statusall(ctx, activity_type, *, msg):
        await bot.change_presence(activity=discord.Game(name=msg))
        await ctx.send(f"All bots set to {activity_type} {msg}")
        await ctx.message.delete()

    @bot.command()
    async def typer(ctx, channel_id: int):
        channel = bot.get_channel(channel_id)
        task = asyncio.create_task(typing_loop(channel))
        typer_tasks[ctx.author.id] = task
        await ctx.send(f"Typing forever in <#{channel_id}>")

    async def typing_loop(channel):
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @bot.command()
    async def stoptyper(ctx):
        task = typer_tasks.pop(ctx.author.id, None)
        if task:
            task.cancel()
            await ctx.send("Typing stopped.")
        else:
            await ctx.send("No active typing.")

    # ============= Lyrics ==============
    @bot.command()
    async def lyrics(ctx, *, song: str):
        await ctx.message.delete()
        if ctx.author.id in lyrics_tasks:
            lyrics_tasks[ctx.author.id].cancel()
        task = asyncio.create_task(lyrics_status_loop(song))
        lyrics_tasks[ctx.author.id] = task
        await ctx.send(f"Streaming lyrics for {song}")

    async def lyrics_status_loop(song):
        lines = get_dummy_lyrics(song)  # Replace with your own logic if you have an API
        while True:
            for line in lines:
                await bot.change_presence(activity=discord.Game(name=line))
                await asyncio.sleep(random.uniform(5, 10))

    def get_dummy_lyrics(song):
        # This is placeholder. You’d replace with actual scraped or API-fetched lyrics.
        return [f"{song} - line {i}" for i in range(1, 11)]

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.pop(ctx.author.id, None)
        if task:
            task.cancel()
            await ctx.send("Lyrics stopped.")
        else:
            await ctx.send("No lyrics running.")

    # ============= Temp Mail ==============
    @bot.command()
    async def tempmail(ctx, amount: int = 1):
        emails = []
        for _ in range(amount):
            login = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz1234567890", k=10))
            domain = random.choice(["1secmail.com", "1secmail.org", "1secmail.net"])
            email = f"{login}@{domain}"
            expiry = time.time() + 86400
            temp_emails.append((email, expiry))
            emails.append(email)
        await ctx.send("Generated emails:\n" + "\n".join(emails))

    @bot.command()
    async def checkmail(ctx, email: str):
        await ctx.message.delete()
        try:
            username, domain = email.split("@")
        except:
            await ctx.send("Invalid format!")
            return
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                await ctx.send(f"Failed to check mail: HTTP {r.status_code}")
                return
            data = r.json()
            if not data:
                await ctx.send(f"No emails found for {email}")
                return
            msg_lines = [f"From: {m['from']} | Subject: {m['subject']} | Date: {m['date']}" for m in data]
            await ctx.send(f"Emails for {email}:\n" + "\n".join(msg_lines))
        except Exception as e:
            await ctx.send(f"Error: {e}")

    @bot.command()
    async def emails(ctx):
        now = time.time()
        listing = []
        for email, expiry in temp_emails:
            left = int(expiry - now)
            listing.append(f"{email} (expires in {left // 3600}h {left % 3600 // 60}m)")
        await ctx.send("Stored temp emails:\n" + "\n".join(listing))

    await bot.start(token)

# ================ Main =================
async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens))

asyncio.run(main())
