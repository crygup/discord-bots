import asyncio
import contextlib
import datetime
import importlib
import io
import itertools
import os
import textwrap
import traceback
import typing

import emoji as unicode_emoji

import discord
import jishaku.modules
from discord.ext import commands

from jishaku.codeblocks import Codeblock, codeblock_converter
from jishaku.features.baseclass import Feature
from jishaku.models import copy_context_with
from jishaku.paginators import WrappedPaginator

from DuckBot.__main__ import DuckBot, CustomContext
from DuckBot.helpers import paginator
from DuckBot.helpers.helper import count_others, count_lines


def setup(bot):
    bot.add_cog(Management(bot))


async def get_webhook(channel) -> discord.Webhook:
    webhook_list = await channel.webhooks()
    if webhook_list:
        for hook in webhook_list:
            if hook.token:
                return hook
    hook = await channel.create_webhook(name="DuckBot ModMail")
    return hook


def cleanup_code(content):
    """Automatically removes code blocks from the code."""
    # remove ```py\n```
    if content.startswith('```') and content.endswith('```'):
        return '\n'.join(content.split('\n')[1:-1])

    # remove `foo`
    return content.strip('` \n')


def is_reply():
    def predicate(ctx):
        if not ctx.message.reference:
            raise commands.BadArgument('You must reply to a message!')
        return True

    return commands.check(predicate)


class UnicodeEmoji:

    @classmethod
    async def convert(cls, ctx, argument):
        if argument not in list(unicode_emoji.EMOJI_UNICODE_ENGLISH.values()):
            return None
        return argument


class Management(commands.Cog, name='Bot Management'):
    """
    🤖 Commands meant for the bot developers to manage the bots functionalities. Not meant for general use.
    """

    def __init__(self, bot):
        self.research_channels = (881215900315951184, 881246869873917962, 881246946776449045, 881247025688084521)
        self.bot: DuckBot = bot
        self._last_result = None

    # Git but to the correct directory
    @Feature.Command(parent="jsk", name="git")
    async def jsk_git(self, ctx: CustomContext, *, argument: codeblock_converter):
        """
        Shortcut for 'jsk sh git'. Invokes the system shell.
        """
        return await ctx.invoke("jsk shell",
                                argument=Codeblock(argument.language, "cd ~/.git/DiscordBots\ngit " + argument.content))

    @commands.group(aliases=['setstatus', 'ss', 'activity'], invoke_without_subcommand=True)
    @commands.is_owner()
    async def status(self, ctx: CustomContext):
        if not ctx.invoked_subcommand:
            await ctx.send_help(ctx.command)

    @status.command(name='playing')
    async def status_playing(self, ctx: CustomContext, text):
        await self.bot.change_presence(activity=discord.Game(name=f'{text}'))
        await ctx.message.add_reaction('✅')
        await ctx.send(f"Activity changed to `Playing {text}` ")

    @status.command(name='listening')
    async def status_listening(self, ctx: CustomContext, text):
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name=f'{text}'))
        await ctx.message.add_reaction('✅')
        await ctx.send(f"Activity changed to `Listening to {text}` ")

    @status.command(name='watching')
    async def status_watching(self, ctx: CustomContext, text):
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name=f'{text}'))
        await ctx.message.add_reaction('✅')
        await ctx.send(f"Activity changed to `Watching {text}` ")

    @status.command(name='competing')
    async def status_competing(self, ctx: CustomContext, text):
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.competing, name=f'{text}'))
        await ctx.message.add_reaction('✅')
        await ctx.send(f"Activity changed to `Competing in {text}`")

    @commands.command(aliases=['mm'], help="puts the bot under maintenance", usage="[on|off]")
    @commands.is_owner()
    @commands.bot_has_permissions(add_reactions=True)
    async def maintenance(self, ctx, *, reason: str = None):
        if reason:
            await ctx.message.add_reaction(ctx.toggle(True))
            self.bot.maintenance = reason
        else:
            await ctx.message.add_reaction(ctx.toggle(False))
            self.bot.maintenance = None

    @commands.command(aliases=['sp'], help="toggles no-prefix mode on or off",
                      usage="[on|off]")
    @commands.is_owner()
    @commands.bot_has_permissions(add_reactions=True)
    async def silentprefix(self, ctx, state: typing.Optional[str] = None):
        if state == 'on':
            await ctx.message.add_reaction(ctx.toggle(True))
            self.bot.noprefix = True
        elif state == 'off':
            await ctx.message.add_reaction(ctx.toggle(False))
            self.bot.noprefix = False
        else:
            if not self.bot.noprefix:
                await ctx.message.add_reaction(ctx.toggle(True))
                self.bot.noprefix = True
            elif self.bot.noprefix:
                await ctx.message.add_reaction(ctx.toggle(False))
                self.bot.noprefix = False

    @commands.command(help="Unloads an extension", aliases=['unl', 'ue', 'uc'])
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def unload(self, ctx, extension):
        embed = discord.Embed(color=ctx.me.color, description=f"⬇ {extension}")
        message = await ctx.send(embed=embed, footer=False)
        try:
            self.bot.unload_extension("DuckBot.cogs.{}".format(extension))
            await asyncio.sleep(0.5)
            embed = discord.Embed(color=ctx.me.color, description=f"✅ {extension}")
            await message.edit(embed=embed)

        except discord.ext.commands.ExtensionNotFound:
            await asyncio.sleep(0.5)
            embed = discord.Embed(color=ctx.me.color, description=f"❌ Extension not found")
            await message.edit(embed=embed)

        except discord.ext.commands.ExtensionNotLoaded:
            await asyncio.sleep(0.5)
            embed = discord.Embed(color=ctx.me.color, description=f"❌ Extension not loaded")
            await message.edit(embed=embed)

    @commands.command(help="Reloads all extensions", aliases=['relall', 'rall', 'reloadall', 'load'])
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def reload(self, ctx, *extensions: jishaku.modules.ExtensionConverter):
        self.bot.last_rall = datetime.datetime.utcnow()
        pages = WrappedPaginator(prefix='', suffix='')
        to_send = []
        err = False
        first_reload_failed_extensions = []

        extensions = extensions or [await jishaku.modules.ExtensionConverter.convert(self, ctx, '~')]

        for extension in itertools.chain(*extensions):
            method, icon = (
                (self.bot.reload_extension, "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}")
                if extension in self.bot.extensions else
                (self.bot.load_extension, "\N{INBOX TRAY}")
            )
            # noinspection PyBroadException
            try:
                method(extension)
                pages.add_line(f"{icon} `{extension}`")
            except Exception:
                first_reload_failed_extensions.append(extension)

        error_keys = {
            discord.ext.commands.ExtensionNotFound: 'Not found',
            discord.ext.commands.NoEntryPointError: 'No setup function',
            discord.ext.commands.ExtensionNotLoaded: 'Not loaded',
            discord.ext.commands.ExtensionAlreadyLoaded: 'Already loaded',
        }

        for extension in first_reload_failed_extensions:
            method, icon = (
                (self.bot.reload_extension, "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}")
                if extension in self.bot.extensions else
                (self.bot.load_extension, "\N{INBOX TRAY}")
            )
            try:
                method(extension)
                pages.add_line(f"{icon} `{extension}`")

            except tuple(error_keys.keys()) as exc:
                pages.add_line(f"{icon}❌ `{extension}` - {error_keys[type(exc)]}")

            except discord.ext.commands.ExtensionFailed as e:
                traceback_string = f"```py" \
                                   f"\n{''.join(traceback.format_exception(etype=None, value=e, tb=e.__traceback__))}" \
                                   f"\n```"
                pages.add_line(f"{icon}❌ `{extension}` - Execution error")
                to_dm = f"❌ {extension} - Execution error - Traceback:"

                if (len(to_dm) + len(traceback_string) + 5) > 2000:
                    await ctx.author.send(file=io.StringIO(traceback_string))
                else:
                    await ctx.author.send(f"{to_dm}\n{traceback_string}")

        for page in pages.pages:
            await ctx.send(page)

    @commands.command(name="mreload", aliases=['mload', 'mrl', 'rlm'])
    @commands.is_owner()
    @commands.bot_has_permissions(send_messages=True, embed_links=True)
    async def reload_module(self, ctx, *extensions: jishaku.modules.ExtensionConverter):
        """
        Reloads one or multiple extensions
        """
        pages = WrappedPaginator(prefix='', suffix='')

        if not extensions:
            extensions = [await jishaku.modules.ExtensionConverter.convert(self, ctx, os.getenv('COGS_PATH').replace('cogs', 'helpers') + '.*')]

        for extension in itertools.chain(*extensions):
            method, icon = (
                (None, "\N{CLOCKWISE RIGHTWARDS AND LEFTWARDS OPEN CIRCLE ARROWS}")
            )

            try:
                module = importlib.import_module(extension)
                importlib.reload(module)

            except Exception as exc:  # pylint: disable=broad-except
                traceback_data = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__, 1))

                pages.add_line(
                    f"{icon}\N{WARNING SIGN} `{extension}`\n```py\n{traceback_data}\n```",
                    empty=True
                )
            else:
                pages.add_line(f"{icon} `{extension}`")

        for page in pages.pages:
            await ctx.send(page)

    ###############################################################################
    ###############################################################################

    @commands.command(aliases=['pm', 'message', 'direct'])
    @commands.is_owner()
    @commands.guild_only()
    async def dm(self, ctx: CustomContext, member: discord.User, *, message=None):
        if ctx.channel.category_id == 878123261525901342:
            return
        category = self.bot.get_guild(774561547930304536).get_channel(878123261525901342)
        channel = discord.utils.get(category.channels, topic=str(member.id))
        if not channel:
            channel = await category.create_text_channel(
                name=f"{member}",
                topic=str(member.id),
                position=0,
                reason="DuckBot ModMail"
            )

        wh = await get_webhook(channel)

        files = []
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.size > 8388600:
                    await ctx.send('Sent message without attachment! File size greater than 8 MB.')
                    continue
                files.append(await attachment.to_file(spoiler=attachment.is_spoiler()))

        try:
            await member.send(content=message, files=files)
        except:
            return await ctx.message.add_reaction('⚠')

        try:
            await wh.send(content=message, username=ctx.author.name, avatar_url=ctx.author.display_avatar.url,
                          files=files)
        except:
            await ctx.message.add_reaction('🤖')
            await ctx.message.add_reaction('‼')
        await ctx.message.add_reaction('💌')

    @commands.command()
    async def sudo(self, ctx: CustomContext, target: discord.User, channel: typing.Optional[discord.abc.Messageable], sub: str, *, arg: str):
        """
        Run a command as someone else.
        """

        if ctx.guild:
            with contextlib.suppress(discord.HTTPException):
                target_member = ctx.guild.get_member(target.id) or await ctx.guild.fetch_member(target.id)

            target = target_member or target

        alt_ctx = await copy_context_with(ctx, author=target, content=ctx.prefix + arg, channel=channel)

        if alt_ctx.command is None:
            if alt_ctx.invoked_with is None:
                return await ctx.send('This bot has been hard-configured to ignore this user.')
            return await ctx.send(f'Command "{alt_ctx.invoked_with}" is not found')

        return await alt_ctx.command.invoke(alt_ctx)

    @commands.command(pass_context=True, hidden=True, name='eval', aliases=['ev'])
    @commands.is_owner()
    async def _eval(self, ctx: CustomContext, *, body: str):
        """Evaluates a code"""
        env = {
            'bot': self.bot,
            '_b': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            '_c': ctx.channel,
            'author': ctx.author,
            '_a': ctx.author,
            'guild': ctx.guild,
            '_g': ctx.guild,
            'message': ctx.message,
            '_m': ctx.message,
            '_': self._last_result,
            'reference': getattr(ctx.message.reference, 'resolved', None),
            '_r': getattr(ctx.message.reference, 'resolved', None),
            '_get': discord.utils.get,
            '_find': discord.utils.find,
            '_gist': ctx.gist,
            '_now': discord.utils.utcnow,
        }
        env.update(globals())

        body = cleanup_code(body)
        stdout = io.StringIO()
        to_send: str = None

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            try:
                await ctx.message.add_reaction('⚠')
            except (discord.Forbidden, discord.HTTPException):
                pass
            to_send = f'{e.__class__.__name__}: {e}'
            if len(to_send) > 1880:
                return await ctx.send(file=discord.File(io.StringIO(to_send), filename='output.py'))
            return await ctx.send(f'```py\n{to_send}\n```')

        func = env['func']
        try:
            with contextlib.redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('⚠')
            except (discord.Forbidden, discord.HTTPException):
                pass
            to_send = f'\n{value}{traceback.format_exc()}'
            if len(to_send) > 1880:
                return await ctx.send(file=discord.File(io.StringIO(to_send), filename='output.py'))
            return await ctx.send(f'```py\n{to_send}\n```')

        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except (discord.Forbidden, discord.HTTPException):
                pass

            if ret is None:
                if value:
                    to_send = f'{value}'
            else:
                self._last_result = ret
                to_send = f'{value}{ret}'
            if to_send:
                to_send = to_send.replace(self.bot.http.token, '[discord token redacted]')
                if len(to_send) > 1985:
                    await ctx.send(file=discord.File(io.StringIO(to_send), filename='output.py'))
                else:
                    await ctx.send(f"```py\n{to_send}\n```")

    @commands.group(name='sql', aliases=['db', 'database', 'psql', 'postgre'], invoke_without_command=True)
    @commands.is_owner()
    async def postgre(self, ctx: CustomContext, *, query: str):
        """Executes an SQL query to the database"""
        body = cleanup_code(query)
        await ctx.invoke(self._eval, body=f"return await bot.db.fetch(f\"\"\"{body}\"\"\")")

    @commands.is_owner()
    @postgre.command(name='fetch', aliases=['f'])
    async def postgre_fetch(self, ctx, *, query: str):
        """Executes an SQL query to the database (Fetch)"""
        body = cleanup_code(query)
        await ctx.invoke(self._eval, body=f"return await bot.db.fetch(f\"\"\"{body}\"\"\")")

    @commands.is_owner()
    @postgre.command(name='fetchval', aliases=['fr'])
    async def postgre_fetchval(self, ctx, *, query: str):
        """Executes an SQL query to the database (Fetchval)"""
        body = cleanup_code(query)
        await ctx.invoke(self._eval, body=f"return await bot.db.fetchval(f\"\"\"{body}\"\"\")")

    @commands.is_owner()
    @postgre.command(name='fetchrow', aliases=['fv'])
    async def postgre_fetchrow(self, ctx, *, query: str):
        """Executes an SQL query to the database (Fetchrow)"""
        body = cleanup_code(query)
        await ctx.invoke(self._eval, body=f"return await bot.db.fetchrow(f\"\"\"{body}\"\"\")")

    @commands.group(invoke_without_command=True, aliases=['bl'])
    @commands.is_owner()
    async def blacklist(self, ctx: CustomContext) -> discord.Message:
        """ Blacklist management commands """
        if ctx.invoked_subcommand is None:
            return

    @blacklist.command(name="add", aliases=['a'])
    @commands.is_owner()
    async def blacklist_add(self, ctx: CustomContext,
                            user: discord.User) -> discord.Message:
        """ adds a user to the bot blacklist """

        await self.bot.db.execute(
            "INSERT INTO blacklist(user_id, is_blacklisted) VALUES ($1, $2) "
            "ON CONFLICT (user_id) DO UPDATE SET is_blacklisted = $2",
            user.id, True)

        self.bot.blacklist[user.id] = True

        return await ctx.send(f"Added **{user}** to the blacklist")

    @blacklist.command(name="remove", aliases=['r', 'rm'])
    @commands.is_owner()
    async def blacklist_remove(self, ctx: CustomContext,
                               user: discord.User) -> discord.Message:
        """
        removes a user from the bot blacklist
        """

        await self.bot.db.execute(
            "DELETE FROM blacklist where user_id = $1",
            user.id)

        self.bot.blacklist[user.id] = False

        return await ctx.send(f"Removed **{user}** from the blacklist")

    @blacklist.command(name='check', aliases=['c'])
    @commands.is_owner()
    async def blacklist_check(self, ctx: CustomContext, user: discord.User):
        """
        Checks a user's blacklist status
        """
        try:
            status = self.bot.blacklist[user.id]
        except KeyError:
            status = False
        return await ctx.send(f"**{user}** {'is' if status is True else 'is not'} blacklisted")

    @is_reply()
    @commands.is_owner()
    @commands.command()
    async def react(self, ctx, emoji: typing.Optional[typing.Union[UnicodeEmoji, discord.Emoji]]):
        if emoji:
            await ctx.message.reference.resolved.add_reaction(emoji)
        await ctx.message.delete(delay=0)

    @commands.command(name='server-list', aliases=['guilds-list', 'bot-servers'])
    @commands.is_owner()
    async def g_list(self, ctx: CustomContext):
        """
        Shows the bots servers info.
        """
        source = paginator.ServerInfoPageSource(guilds=self.bot.guilds, ctx=ctx)
        menu = paginator.ViewPaginator(source=source, ctx=ctx)
        await menu.start()

    @commands.command(aliases=['pull'])
    @commands.is_owner()
    async def git_pull(self, ctx: CustomContext, reload_everything: bool = False):
        """
        Attempts to pull from git
        """
        command = self.bot.get_command('jsk git')
        await ctx.invoke(command, argument=codeblock_converter('pull'))
        if reload_everything is True:
            mrl = self.bot.get_command('mrl')
            await ctx.invoke(mrl)
            rall = self.bot.get_command('rall')
            await ctx.invoke(rall)

    @commands.command(aliases=['push'])
    @commands.is_owner()
    async def git_push(self, ctx, *, message: str):
        """
        Attempts to push to git
        """
        command = self.bot.get_command('jsk git')
        await ctx.invoke(command, argument=codeblock_converter(f'add .\ngit commit -m "{message}"\ngit push origin master'))
