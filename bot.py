import json
import time
from datetime import datetime, timedelta, timezone

with open("config.json") as f:
    config = json.load(f)

import discord
from discord.ext import commands
from sqlalchemy import BigInteger, Column, Integer, Text, create_engine
from sqlalchemy.orm import Session, registry

mapper_reg = registry()
Base = mapper_reg.generate_base()


class InviteTracking(Base):
    __tablename__ = "invites"
    id = Column(Integer, primary_key=True, nullable=True)
    guild_id = Column(BigInteger, nullable=False)
    invite_code = Column(Text, nullable=False, unique=True)
    invite_uses = Column(BigInteger, nullable=False)

    def __init__(self, id, guild_id, invite_code, invite_uses):
        self.id = id
        self.guild_id = guild_id
        self.invite_code = invite_code
        self.invite_uses = invite_uses


engine = create_engine(f"sqlite:///{config['DATABASE_NAME']}", future=True)
Base.metadata.create_all(bind=engine)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
activity = discord.Activity(
    name=f"'{config['PREFIX']}'", type=discord.ActivityType.watching
)
bot = commands.Bot(
    command_prefix=config["PREFIX"],
    intents=intents,
    description="InviteTracker replacement",
    activity=activity,
)


@bot.event
async def on_member_join(member):
    inviter = None
    with Session(engine, autoflush=True) as session:
        codes = session.query(InviteTracking).filter_by(guild_id=member.guild.id).all()
    if len(codes) == 0:
        guild = await bot.fetch_guild(member.guild.id)
        invites = await guild.invites()
        for invite in invites:
            with Session(engine, autoflush=True) as session:
                new_code = InviteTracking(
                    id=None,
                    guild_id=guild.id,
                    invite_code=invite.code,
                    invite_uses=invite.uses,
                )
                session.add(new_code)
                session.commit()
    else:
        guild = await bot.fetch_guild(member.guild.id)
        invites = await guild.invites()
        for db_code in codes:
            for invite in invites:
                if invite.code == db_code.invite_code:
                    prev_uses = db_code.invite_uses
                    new_uses = invite.uses
                    if new_uses == prev_uses:
                        continue
                    elif new_uses > prev_uses:
                        inviter = invite.inviter
                        with Session(engine, autoflush=True) as session:
                            session.query(InviteTracking).filter_by(
                                guild_id=guild.id, invite_code=invite.code
                            ).update({"invite_uses": invite.uses})
                            session.commit()
                        break
    offset = (
        (time.timezone if (time.localtime().tm_isdst == 0) else time.altzone)
        / 60
        / 60
        * -1
    )
    now = datetime.strftime(
        datetime.now(tz=timezone(offset=timedelta(hours=offset))), "%I:%M %p"
    )
    channel = await bot.fetch_channel(config["CHANNEL_ID"])
    embed = discord.Embed(title=f"**{member} joined!**", color=discord.Color.blurple())
    if hasattr(member.avatar, "url"):
        embed.set_thumbnail(url=member.avatar.url)
    else:
        embed.set_thumbnail(url="https://cdn.discordapp.com/embed/avatars/1.png")
    joined_guild = await bot.fetch_guild(member.guild.id, with_counts=True)
    if inviter is None:
        inviter = member.guild.owner
    embed.add_field(
        name="",
        value=f"**{member}** ({member.id}) joined the server and has been invited by **{inviter}**\n\nWe now have **{joined_guild.approximate_member_count}** members in the server.",
    )
    embed.set_footer(icon_url=inviter.avatar.url, text=f"{inviter} • Today at {now}")
    await channel.send(embed=embed)


@bot.event
async def on_raw_member_remove(payload):
    offset = (
        (time.timezone if (time.localtime().tm_isdst == 0) else time.altzone)
        / 60
        / 60
        * -1
    )
    now = datetime.strftime(
        datetime.now(tz=timezone(offset=timedelta(hours=offset))), "%I:%M %p"
    )
    channel = await bot.fetch_channel(config["CHANNEL_ID"])
    embed = discord.Embed(title=f"**{payload.user} left!**", color=discord.Color.red())
    left_guild = await bot.fetch_guild(payload.guild_id, with_counts=True)
    embed.add_field(
        name="",
        value=f"**{payload.user}** ({payload.user.id}) left the server!\n\nWe now have **{left_guild.approximate_member_count}** members in the server.",
    )
    embed.set_footer(
        icon=payload.user.avatar.url, text=f"{payload.user} • Today at {now}"
    )
    await channel.send(embed=embed)


@bot.event
async def on_ready():
    with Session(engine, autoflush=True) as session:
        async for guild in bot.fetch_guilds():
            invites = await guild.invites()
            for invite in invites:
                exists = (
                    session.query(InviteTracking.invite_code)
                    .filter_by(guild_id=guild.id, invite_code=invite.code)
                    .one_or_none()
                )
                if exists:
                    session.query(InviteTracking).filter_by(
                        guild_id=guild.id, invite_code=invite.code
                    ).update({"invite_uses": int(invite.uses)})
                    session.commit()
                    continue
                else:
                    new_code = InviteTracking(
                        id=None,
                        guild_id=guild.id,
                        invite_code=invite.code,
                        invite_uses=invite.uses,
                    )
                    session.add(new_code)
                    session.commit()
    print(f"Logged in as {bot.user}")


bot.run(config["TOKEN"])
