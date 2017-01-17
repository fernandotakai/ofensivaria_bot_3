import re
import random
import logging

import abc
import six

from decorator import decorator
from ofensivaria import config


class ValidationException(Exception):
    def __init__(self, message):
        self.message = message


@decorator
async def reply(f, *args, **kwargs):
    r = await f(*args, **kwargs)

    if r:
        if isinstance(r, dict):
            r['needs_reply'] = True
        elif isinstance(r, str):
            r = dict(answer=r, needs_reply=True)
        elif isinstance(r, bytes):
            r = dict(answer=r.decode('utf8'), needs_reply=True)

    return r


@decorator
async def preview(f, *args, **kwargs):
    r = await f(*args, **kwargs)

    if r:
        if isinstance(r, dict):
            r['needs_preview'] = True
        elif isinstance(r, str):
            r = dict(answer=r, needs_preview=True)

    return r


@decorator
async def markdown(f, *args, **kwargs):
    r = await f(*args, **kwargs)

    if r:
        if isinstance(r, dict):
            r['markdown'] = True
        elif isinstance(r, str):
            r = dict(answer=r, markdown=True)

    return r


@six.add_metaclass(abc.ABCMeta)
class Command:

    # can be a single slash command or a
    # list of commands
    SLASH_COMMAND = None

    # defines if the command needs a reply or not
    REPLY_NEEDED = False

    # if the command supplies this, we will parse the text using this
    # regex and try to validate the command using it
    REGEX = None

    def __init__(self, bot, redis, http_client):
        self._bot = bot
        self._redis = redis
        self._http_client = http_client
        self._logger = logging.getLogger('command')
        self._logger.setLevel(config.LOGGING_LEVEL)

        if isinstance(self.SLASH_COMMAND, str):
            self.SLASH_COMMAND = [self.SLASH_COMMAND]

        if self.SLASH_COMMAND:
            self._commands = dict([(c.split(' ')[0].replace("/", ""), c) for c in self.SLASH_COMMAND])
            command_re = r'^\/(%s)\s?(.*)?$' % '|'.join("\\b%s\\b" % c.replace('/', '') for c in self._commands.keys())
            self._slash_re = re.compile(command_re, re.I)
            self._slash_args_re = re.compile(r'\[(\w+)\]')

    @abc.abstractmethod
    async def respond(self, text, message):
        pass

    def __validate_slash_command(self, text, message):

        result = self._slash_re.findall(text)

        if not result:
            return False

        try:
            command, args = result[0]
            command = command.lower()
            args = args.split()
        except ValueError:
            command, result[0][0].lower()
            args = None

        try:
            full_command = self._commands[command]
            command_args = self._slash_args_re.findall(full_command)

            if len(command_args) == 1 and len(args) > 1:
                args = [" ".join(args)]

            if command_args and len(command_args) != len(args):
                    raise ValidationException("Wrong number of arguments %s" % full_command)

            message['args'] = dict(zip(command_args, args))
        except (KeyError, IndexError):
            return False

        message['command'] = command.lower()

        return True

    def __validate_regex(self, text, message):
        result = self.REGEX.findall(text)

        if not result:
            return False

        message['result'] = result[0]
        return True

    def can_respond(self, text, message):
        if self.REGEX:
            return self.__validate_regex(text, message)

        if self.SLASH_COMMAND:
            return self.__validate_slash_command(text, message)

        return False

    async def http_get(self, url, params=None, **kwargs):
        kwargs.update({'timeout': 30, 'params': params})

        async with self._http_client.get(url, **kwargs) as response:
            json = await response.json()
            return response, json

    async def http_post(self, url, data=None, **kwargs):
        kwargs.update({'timeout': 30, 'data': data})

        async with self._http_client.post(url, **kwargs) as response:
            json = await response.json()
            return response, json

    async def __send_message(self, command_response, message):

        if command_response is False:
            return

        if isinstance(command_response, str):
            command_response = dict(answer=command_response)

        if isinstance(command_response, bytes):
            command_response = dict(answer=command_response.decode('utf8'))

        if not isinstance(command_response, dict):
            raise ValueError("Command response must be a dict")

        if 'answer' not in command_response:
            raise ValueError("Command response must have an answer")

        answer = command_response['answer']
        needs_reply = command_response.get('needs_reply', False)
        needs_preview = command_response.get('needs_preview', False)
        markdown = command_response.get('markdown', False)

        reply_id = message.get('message_id', None) if needs_reply else None

        await self._bot.send_message(message['chat']['id'], answer, reply_id, needs_preview, markdown)

    async def process(self, bot, message):
        try:
            text = message['text'].encode("utf-8").decode("utf-8")
            text = text.replace(u'\xa0', ' ')
            message['text'] = text
        except KeyError:
            message['text'] = ''
            text = ''

        try:
            if self.can_respond(text, message):
                response = await self.respond(text, message)
                await self.__send_message(response, message)
        except ValidationException as e:
            await self.__send_message(dict(answer=e.message), message)


class Ping(Command):
    """ Simple ping command to make sure the bot itself works """

    SLASH_COMMAND = '/ping'

    async def respond(self, text, message):
        return 'pong'


class Title(Command):
    """ Returns an imgur album showing the reason our chat title
    is the way it's """

    SLASH_COMMAND = '/title'

    async def respond(self, text, message):
        return '''season 1: http://imgur.com/a/0OlQR
season 2: http://imgur.com/a/y6A2F'''


class EitherOr(Command):
    """ Asks the bot about one or another option -- bot returns one of them
    OR 'sim' (which has a 10 percent chance of happening). Example:

    user: github or bitbucket?
    bot: > github or bitbucket?
    github"""

    REGEX = re.compile("(.+?)\sou\s(.+?)\?+$", re.UNICODE)

    @reply
    async def respond(self, text, message):

        if not text.startswith('@ofensivaria_bot'):
            return False

        choices = message['result']

        if random.randint(1, 100) < 10:
            answer = 'sim'
        else:
            answer = random.choice(choices).strip()

        return answer.replace("@ofensivaria_bot", "")


class Help(Command):
    """ LOLHELP """
    SLASH_COMMAND = '/help'

    @reply
    async def respond(self, text, message):
        return 'Deus ajuda quem cedo madruga'


class ArchiveUrl(Command):
    """ Tries to archive an url and returns the archive to the chat """

    SLASH_COMMAND = '/archive [url]'

    async def respond(self, text, message):
        url = message['args']['url']

        archive_api = 'http://archive.org/wayback/available'
        json = await self.http_get(archive_api, params=dict(url=url))

        if json['archived_snapshots']:
            answer = json['archived_snapshots']['closest']['url']
        else:
            answer = 'Click here to archive - https://archive.is/?run=1&url=%s' % url

        return answer


class Google(Command):
    """ Uses google to return the first link given a query using 'I feel lucky'"""

    SLASH_COMMAND = '/google [query]'

    @reply
    async def respond(self, text, message):
        url = message['args']['query']

        headers = {'User-agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:39.0) Gecko/20100101 Firefox/39.0'}
        response, _ = await self.http_get("https://www.google.com.br/search?q=%s&btnI=" % url, headers=headers)

        answer = "Google answered %s" % response.url

        return answer


class DanceGif(Command):
    """ DANCE """

    SLASH_COMMAND = '/dance'

    @reply
    @preview
    async def respond(self, text, message):
        dances = [
            'http://i.imgur.com/EE8XOqr.gifv',
            'http://i.imgur.com/VeK7Otb.gifv',
            'http://i.imgur.com/ZtwGLMW.gifv'
        ]

        return random.choice(dances)


class MessageToGif(Command):
    """ Teaches the bot about gifs and gif names. If the user uses a name, the bot
    will send the gif to the chat. Supports more than one gif per name."""

    SLASH_COMMAND = ('/teach [name] [url]', '/forget [name]',
                     '/randomgif', '/gifs')

    def can_respond(self, text, message):
        return (text.endswith('.gif') and ' ' not in text) or super(MessageToGif, self).can_respond(text, message)

    async def get_gif(self, name):
        try:
            key = 'bot:gifs:%s' % name
            return random.choice(await self._redis.lrange(key, 0, -1)).decode('utf8')
        except IndexError:
            return

    async def command_teach(self, url, name):
        try:
            if not name.endswith('.gif'):
                return "gif name must end with .gif"

            elif 'http' not in url:
                return "gif is not a link"

            else:
                await self._redis.sadd('bot:gifs', name)
                await self._redis.lpush('bot:gifs:%s' % name, url)
                return "now i know about %s" % name

        except ValueError:
            return "/teach <name.gif> <url> is the right format"

    async def command_forget(self, name):
        await self._redis.delete('bot:gifs:%s' % name)
        await self._redis.srem('bot:gifs', name)

        return "forgot %s" % name

    async def command_randomgif(self):
        gif_name = (await self._redis.srandmember('bot:gifs')).decode('utf8')
        return await self.get_gif(gif_name)

    async def command_gifs(self):
        gifs = sorted(await self._redis.smembers('bot:gifs'))
        return ', '.join(sorted(gifs))

    @preview
    async def respond(self, text, message):
        text = message['text'].strip()
        command = message.get('command', None)

        if not command:
            return await self.get_gif(text)
        else:
            try:
                method = getattr(self, 'command_%s' % command)
                return await method(**message['args'])
            except Exception:
                return ""


class ConvertCurrency(Command):

    SLASH_COMMAND = ('/convert [value] [symbol]')

    async def respond(self, text, message):
        symbol = message['args']['symbol']
        try:
            value = float(message['args']['value'])
        except ValueError:
            return 'value must be a number'

        _, json = await self.http_get('http://api.fixer.io/latest', params={'base': symbol, 'symbols': 'BRL'})

        if not json or 'error' in json:
            return "Could not get value for currency %s" % symbol

        try:
            return "R$%.2f" % (value * json['rates']['BRL'])
        except KeyError:
            return 'Could not get value for currency %s' % symbol


class Sandstorm(Command):

    SLASH_COMMAND = '/sandstorm'

    async def respond(self, text, message):
        await self._bot.send_audio(message['chat']['id'], 'AAQBABMdQN4pAASxodqPFrSjGDsUAAIC')
        return ""


class Imgur(Command):

    SLASH_COMMAND = '/imgurid [client_id]'

    def can_respond(self, text, message):
        try:
            photo = message['photo']
            chat = message['chat']['type']

            return (chat == 'private' and len(photo) > 0)
        except KeyError:
            return super(Imgur, self).can_respond(text, message)

    async def respond(self, text, message):
        command = message.get('command', None)

        if not command:
            return await self.upload(message)
        else:
            client_id = message['args']['client_id']
            return await self.set_imgur_client_id(client_id)

    async def set_imgur_client_id(self, client_id):
        old_client_id = await self._redis.get('bot:imgur:client')

        if old_client_id:
            return "i already have a client id. clean it by hand before resetting"

        await self._redis.set("bot:imgur:client", client_id)
        return 'we are set for imgur'

    async def upload(self, message):
        photo = message['photo'][-1]
        file_id = photo['file_id']

        cached_image = await self._redis.hget('bot:imgur', file_id)

        if cached_image:
            return cached_image

        client_id = await self._redis.get('bot:imgur:client')

        if not client_id:
            return 'Nobody set my client id for imgur'

        client_id = client_id.decode('utf8')

        file_obj = await self._bot.get_file(file_id)
        file_path = file_obj['result']['file_path']
        fd = await self._bot.download_file(file_path)

        data = {'image': fd}
        headers = {'Authorization': 'Client-ID {}'.format(client_id)}

        response, json = await self.http_post('https://api.imgur.com/3/image', data=data, headers=headers)

        try:
            if not json['success']:
                raise ValueError

            link = json['data']['link']
            await self._redis.hset('bot:imgur', file_id, link)

            return link
        except (KeyError, ValueError):
            self._logger.exception(json)
            return "Could not upload :("


class FlipTable(Command):

    SLASH_COMMAND = '/flip'

    @reply
    async def respond(self, text, message):
        return '(╯°□°）╯︵ ┻━┻'


class SquareMeme(Command):

    SLASH_COMMAND = '/square [text]'

    def middle(self, string, rev):
        string = string[1:-1]
        for i, l in enumerate(string):
            yield [l] + [' '] * len(string) + [rev[i]]

    def meme(self, value):
        rev = value[::-1]
        memed = [value] + list(self.middle(value, rev)) + [rev]
        return '\n'.join([' '.join(z) for z in memed])

    @reply
    @markdown
    async def respond(self, text, message):
        text = message['args']['text']
        return '```\n%s\n```' % self.meme(text)
