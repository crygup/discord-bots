import io
import traceback
import discord
from discord.ext import commands
from discord.ext.commands import BucketType

import DuckBot.errors as errors
from DuckBot.__main__ import DuckBot
from DuckBot.cogs import music as music_cog


warned = []


def setup(bot):
    bot.add_cog(Handler(bot))


class Handler(commands.Cog, name='Handler'):
    """
    🆘 Handle them errors 👀 How did you manage to get a look at this category????
    """

    def __init__(self, bot):
        self.bot: DuckBot = bot
        self.error_channel = 880181130408636456

    @commands.Cog.listener('on_command_error')
    async def error_handler(self, ctx: commands.Context, error):
        error = getattr(error, "original", error)

        ignored = (
            commands.CommandNotFound,
            music_cog.NoPlayer,
            music_cog.FullVoiceChannel,
            music_cog.NotAuthorized,
            music_cog.IncorrectChannelError,
            music_cog.AlreadyConnectedToChannel,
            music_cog.NoVoiceChannel,
            music_cog.QueueIsEmpty,
            music_cog.NoCurrentTrack,
            music_cog.PlayerIsAlreadyPaused,
            music_cog.PlayerIsNotPaused,
            music_cog.NoMoreTracks,
            music_cog.InvalidTimeString,
            music_cog.NoPerms,
            music_cog.NoConnection,
            music_cog.AfkChannel,
            music_cog.SkipInLoopMode,
            music_cog.InvalidTrack,
            music_cog.InvalidPosition,
            music_cog.InvalidVolume,
            music_cog.OutOfTrack,
            music_cog.NegativeSeek
        )

        if isinstance(error, ignored):
            return

        if isinstance(error, errors.UserBlacklisted):
            if ctx.author.id not in warned:
                warned.append(ctx.author.id)
                return await ctx.send("You can't do that! You're blacklisted.")
            else:
                return

        if isinstance(error, discord.ext.commands.CheckAnyFailure):
            for e in error.errors:
                if not isinstance(error, commands.NotOwner):
                    error = e
                    break

        if isinstance(error, discord.ext.commands.BadUnionArgument):
            if error.errors:
                error = error.errors[0]

        if isinstance(error, commands.NotOwner):
            return await ctx.send(f"you must own `{ctx.me.display_name}` to use `{ctx.command}`")

        if isinstance(error, commands.TooManyArguments):
            return await ctx.send(f"Too many arguments passed to the command!")

        if isinstance(error, discord.ext.commands.MissingPermissions):
            missing = [(e.replace('_', ' ').replace('guild', 'server')).title() for e in error.missing_permissions]
            perms_formatted = ", ".join(missing[:-2] + [" and ".join(missing[-2:])])
            return await ctx.send(f"You're missing **{perms_formatted}** permissions!")

        if isinstance(error, discord.ext.commands.BotMissingPermissions):
            missing = [(e.replace('_', ' ').replace('guild', 'server')).title() for e in error.missing_permissions]
            perms_formatted = ", ".join(missing[:-2] + [" and ".join(missing[-2:])])
            return await ctx.send(f"I'm missing **{perms_formatted}** permissions!")

        if isinstance(error, discord.ext.commands.MissingRequiredArgument):
            missing = f"{error.param.name}"
            command = f"{ctx.clean_prefix}{ctx.command} {ctx.command.signature}"
            separator = (' ' * (len([item[::-1] for item in command[::-1].split(missing[::-1], 1)][::-1][0]) - 1))
            indicator = ('^' * (len(missing) + 2))
            return await ctx.send(f"```\n{command}\n{separator}{indicator}\n{missing} "
                                  f"is a required argument that is missing.\n```")

        if isinstance(error, commands.errors.PartialEmojiConversionFailure):
            return await ctx.send(f"`{error.argument}` is not a valid Custom Emoji")

        if isinstance(error, commands.errors.CommandOnCooldown):
            embed = discord.Embed(color=0xD7342A,
                                  description=f'Please try again in {round(error.retry_after, 2)} seconds')
            embed.set_author(name='Command is on cooldown!', icon_url='https://i.imgur.com/izRBtg9.png')

            if error.type == BucketType.default:
                per = ""
            elif error.type == BucketType.user:
                per = "per user"
            elif error.type == BucketType.guild:
                per = "per server"
            elif error.type == BucketType.channel:
                per = "per channel"
            elif error.type == BucketType.member:
                per = "per member"
            elif error.type == BucketType.category:
                per = "per category"
            elif error.type == BucketType.role:
                per = "per role"
            else:
                per = ""

            embed.set_footer(text=f"cooldown: {error.cooldown.rate} per {error.cooldown.per}s {per}")
            return await ctx.send(embed=embed)

        if isinstance(error, discord.ext.commands.errors.MaxConcurrencyReached):
            embed = discord.Embed(color=0xD7342A, description=f"Please try again once you are done running the command")
            embed.set_author(name='Command is alrady running!', icon_url='https://i.imgur.com/izRBtg9.png')

            if error.per == BucketType.default:
                per = ""
            elif error.per == BucketType.user:
                per = "per user"
            elif error.per == BucketType.guild:
                per = "per server"
            elif error.per == BucketType.channel:
                per = "per channel"
            elif error.per == BucketType.member:
                per = "per member"
            elif error.per == BucketType.category:
                per = "per category"
            elif error.per == BucketType.role:
                per = "per role"
            else:
                per = ""

            embed.set_footer(text=f"limit is {error.number} command(s) running {per}")
            return await ctx.send(embed=embed)

        if isinstance(error, errors.NoQuotedMessage):
            return await ctx.send("<:reply:824240882488180747> Missing reply!")

        if isinstance(error, errors.MuteRoleNotFound):
            return await ctx.send("This server doesn't have a mute role, or it was deleted!"
                                  "\nAssign it with `muterole [new_role]` command, "
                                  "or can create it with the `muterole create` command")

        if isinstance(error, errors.NoEmojisFound):
            return await ctx.send("I couldn't find any emojis there.")

        if isinstance(error, commands.errors.MemberNotFound):
            return await ctx.send(f"I couldn't find `{error.argument}` in this server")

        if isinstance(error, commands.errors.UserNotFound):
            return await ctx.send(
                f"I've searched far and wide, but `{error.argument}` doesn't seem to be a member discord user...")

        if isinstance(error, commands.BadArgument):
            return await ctx.send(error or "Bad argument given!")

        if isinstance(error, discord.HTTPException):
            await ctx.send("Oh no! An unexpected HTTP error occurred while handling this command! 😔"
                           "\nI've notified the developers about it. in the meantime, maybe try again?")

        if isinstance(error, discord.Forbidden):
            await ctx.send("Oh no! It seems like I don't have permissions to perform that action!"
                           "\nThis may be due to me missing permissions in a specific channel, server"
                           "permissions, or an issue with role hierarchy. Try adjusting my permissions"
                           "for this server. \n(Note that I can't edit the server owner)")

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("This command does not work inside DMs")

        if isinstance(error, commands.PrivateMessageOnly):
            return await ctx.send("This command only works inside DMs")

        error_channel = self.bot.get_channel(self.error_channel)

        traceback_string = "".join(traceback.format_exception(
            etype=None, value=error, tb=error.__traceback__))

        await self.bot.wait_until_ready()

        if ctx.guild:
            command_data = f"by: {ctx.author.name} ({ctx.author.id})" \
                           f"\ncommand: {ctx.message.content[0:1700]}" \
                           f"\nguild_id: {ctx.guild.id}" \
                           f"\nowner: {ctx.guild.owner.name} ({ctx.guild.owner.id})" \
                           f"\nbot admin: {ctx.default_tick(ctx.me.guild_permissions.administrator)} " \
                           f"- role pos: {ctx.me.top_role.position}"
        else:
            command_data = f"command: {ctx.message.content[0:1700]}" \
                           f"\nCommand executed in DMs"

        to_send = f"```yaml\n{command_data}``````py\n{ctx.command} " \
                  f"command raised an error:\n{traceback_string}\n```"
        if len(to_send) < 2000:
            try:
                sent_error = await error_channel.send(to_send)

            except (discord.Forbidden, discord.HTTPException):
                sent_error = await error_channel.send(f"```yaml\n{command_data}``````py Command: {ctx.command}"
                                                      f"Raised the following error:\n```",
                                                      file=discord.File(io.StringIO(traceback_string),
                                                                        filename='traceback.py'))
        else:
            sent_error = await error_channel.send(f"```yaml\n{command_data}``````py Command: {ctx.command}"
                                                  f"Raised the following error:\n```",
                                                  file=discord.File(io.StringIO(traceback_string),
                                                                    filename='traceback.py'))
        try:
            await sent_error.add_reaction('🗑')
        except (discord.HTTPException, discord.Forbidden):
            pass
        raise error

    @commands.Cog.listener('on_raw_reaction_add')
    async def wastebasket(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id != self.error_channel or payload.member.bot:
            return
        await self.bot.get_channel(payload.channel_id).get_partial_message(payload.message_id).delete()
