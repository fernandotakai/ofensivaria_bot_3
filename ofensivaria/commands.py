import asyncio
import aiofiles
import markovify

import re
import random
import logging

import abc
import six
import pytz
from datetime import datetime

from decorator import decorator
from ofensivaria import config

from itertools import chain


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

    REQUIRED_PARAMS = False

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

    async def prepare(self):
        return

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

            if self.REQUIRED_PARAMS and command_args and len(command_args) != len(args):
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

        as_text = kwargs.pop('as_text', False)
        async with self._http_client.get(url, **kwargs) as response:
            if as_text:
                content = await response.text()
            else:
                content = await response.json()
            return response, content

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

        if answer:
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
        _, json = await self.http_get(archive_api, params=dict(url=url))

        if json['archived_snapshots']:
            answer = json['archived_snapshots']['closest']['url']
        else:
            answer = 'Click here to archive - https://archive.is/?run=1&url=%s' % url

        return answer


class Google(Command):
    """ Uses google to return the first link given a query using 'I feel lucky'"""

    SLASH_COMMAND = '/google [query]'

    @reply
    @preview
    async def respond(self, text, message):
        url = message['args']['query']

        headers = {'User-agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:39.0) Gecko/20100101 Firefox/39.0'}
        response, _ = await self.http_get("https://www.google.com.br/search?q=%s&btnI=" % url,
                                          headers=headers, as_text=True, allow_redirects=True)

        return response.url


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
            return random.choice(await self._redis.lrange(key, 0, -1))
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
        gif_name = (await self._redis.srandmember('bot:gifs'))
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


class MtgCard(Command):
    """ Returns the image URL of a random Magic card.
    The default preview system is used to display the image.
    https://docs.magicthegathering.io/
    Possible improvements: use the same API for searching; display the portuguese card name, for laughs.
    """

    SLASH_COMMAND = '/mtg'

    async def respond(self, text, message):
        _, json = await self.http_get('https://api.scryfall.com/cards/random')

        self._logger.error(json)

        if not json or 'error' in json:
            return "Spellfire will be reprinted!"


        try:
            largest = sorted(json['image_uris'])[0]
            image = json['image_uris'].get('large', largest)
            url = json['scryfall_uri']
            name = json['name']
            price = json.get('usd', 0)
        except KeyError as e:
            self._logger.exception(e)
            return 'Could not get a card. Try again?'

        caption = f"{name}\n{url}\nUSD {price}"
        response = await self._bot.send_photo(message['chat']['id'], image, caption='')
        return caption


class Sandstorm(Command):

    SLASH_COMMAND = '/sandstorm'

    async def respond(self, text, message):
        await self._bot.send_audio(message['chat']['id'], 'AAQBABMdQN4pAASxodqPFrSjGDsUAAIC')
        return ""


class ProgrammerExcuses(Command):
    """ Returns a random programmer excuse.
    References: http://programmingexcuses.com/ , https://github.com/yelinaung/pe-api"""

    SLASH_COMMAND = '/excuse'

    async def respond(self, text, message):
        _, json = await self.http_get('http://pe-api.herokuapp.com/')

        if not json:
            return "The internet tubes are clogged."

        return json['message']


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

    async def respond(self, text, message):
        return '(╯°□°）╯︵ ┻━┻'


class Shrug(Command):

    SLASH_COMMAND = '/shrug'

    async def respond(self, text, message):
        return '¯\_(ツ)_/¯'


class RussianRouletteCommand(Command):

    SLASH_COMMAND = '/roulette'

    async def respond(self, text, message):
        username = message['from']['first_name']

        if random.randint(1, 6) == 3:
            await self._redis.hincrby('russian', username, 1)
            return "BANG! ~reloading"
        else:
            return "*click*"


class RussianScoreboardCommand(Command):

    RE_REPLACE = re.compile(r'`|\*|\|')
    SLASH_COMMAND = '/scoreboard'

    def _format(self, rank, values):
        word = 'time' if int(values[1]) <= 1 else 'times'
        name = self.RE_REPLACE.sub('', values[0])
        return f'{rank}.\t{name} - {values[1]} {word}'

    @markdown
    async def respond(self, text, message):
        values = await self._redis.hgetall('russian')

        if not values:
            return 'No one killed themselves yet :)'

        sorted_values = {k: int(v) for k, v in values.items()}
        sorted_values = sorted(sorted_values.items(), key=lambda v: v[1], reverse=True)

        scoreboard = '\n'.join(self._format(i, v) for i, v in enumerate(sorted_values, start=1))
        return f'```\n{scoreboard}\n```'


class SquareMeme(Command):

    SLASH_COMMAND = '/square [text]'

    def middle(self, string, rev):
        string = string[1:-1]
        rev = rev[1:-1]
        for i, l in enumerate(string):
            yield [l] + [' '] * len(string) + [rev[i]]

    def meme(self, value):
        rev = value[::-1]
        memed = [value] + list(self.middle(value, rev)) + [rev]
        return '\n'.join([' '.join(z) for z in memed])

    @markdown
    async def respond(self, text, message):
        text = message['args']['text']
        text = text.replace(' ', '')
        if len(text) < 2:
            return False
        return '```\n%s\n```' % self.meme(text)


class YugiOhCard(Command):

    SLASH_COMMAND = ('/downloadcards', '/randomcard')
    URL = 'http://yugioh.wikia.com/wiki/Special:Ask/-5B-5BMedium::TCG-5D-5D/mainlabel%3D/limit%3D500/format%3Djson/offset%3D'

    async def _get(self, url):
        async with self._http_client.get(url) as response:
            return await response.json()

    async def _get_image(self, card_name):
        url = f'http://yugiohprices.com/api/card_image/{card_name}'

        async with self._http_client.get(url) as response:
            if response.status == 404:
                return False

            return response.history[0].headers['Location']

    async def command_downloadcards(self, *args, **kwargs):
        number = await self._redis.scard('cards')

        if not number:
            urls = [self.URL + str(offset) for offset in range(0, 6000, 500)]
            tasks = [self._get(url) for url in urls]
            results = await asyncio.gather(*tasks)

            cards = [c['results'].keys() for c in results]
            cards = list(chain(*cards))

            await self._redis.sadd('cards', *cards)
            number = await self._redis.scard('cards')

        return f'Downloaded {number}'

    async def command_randomcard(self, text, message, **kwargs):
        while True:
            card_name = await self._redis.srandmember('cards')

            image = await self._redis.hget('card_cache', card_name)

            if not image:
                image = await self._get_image(card_name)

            if image:
                wiki_name = card_name.replace(' ', '_')
                caption = f'{card_name} - http://yugioh.wikia.com/wiki/{wiki_name}'
                response = await self._bot.send_photo(message['chat']['id'], image, caption=caption)
                file_id = response['result']['photo'][0]['file_id']
                await self._redis.hset('card_cache', card_name, file_id)

                return ''

    async def respond(self, text, message):
        command = message.get('command', None)

        method = getattr(self, 'command_%s' % command)
        return await method(text, message, **message['args'])


class Quote(Command):

    SLASH_COMMAND = ('/quote [start]')
    REQUIRED_PARAMS = False
    CLEANUP_RE = re.compile(r'@\w+\s?')

    async def prepare(self):
        try:
            async with aiofiles.open('/markov/trained.json') as f:
                data = await f.read()
                self.model = markovify.NewlineText.from_json(data)
                self._logger.info('Loaded model!')
        except Exception as e:
            self._logger.exception("Couldn't load the model")
            self.model = None

    def _handle_error(self, start='that'):
        phrase = self.model.make_short_sentence(140)
        return f"I didn't understand {start}. Here's a random thought: \"{phrase}\""

    async def respond(self, text, message):
        if not self.model:
            return "I don't have a model, sorry :("

        if message.get('args'):
            try:
                start = "that"
                start = message['args']['start']

                if start.startswith('@ofensivaria'):
                    start = self.CLEANUP_RE.sub('', start)

                if start:
                    phrase = self.model.make_sentence_with_start(start, max_chars=140)
                else:
                    phrase = self.model.make_short_sentence(140)

                if not phrase:
                    return self._handle_error()

                return phrase
            except Exception:
                self._logger.exception('wat')
                return self._handle_error()
        else:
            return self.model.make_short_sentence(140)

class SgdqSchedule(Command):

    SLASH_COMMAND = ('/sgdq')
    LOCAL_TZ = pytz.timezone('America/Sao_Paulo')
    CHICAGO_TZ = pytz.timezone('America/Chicago')

    def _format_event(self, event, now=False):
        title, runners, length, _, _ = event['data']
        scheduled_stamp = event['scheduled_t']
        dt = datetime.fromtimestamp(scheduled_stamp, tz=self.CHICAGO_TZ)
        dt = self.LOCAL_TZ.normalize(dt)
        scheduled = dt.strftime('%H:%M')

        if not now:
            return f'{scheduled} - {title} - {length}'
        else:
            now = datetime.now(tz=self.LOCAL_TZ)
            diff = dt - now
            return f'In {diff} - {title}'

    @markdown
    async def respond(self, text, message):
        url = 'https://horaro.org/-/api/v1/schedules/45114j6eoi219j7ab0/ticker'
        _, json = await self.http_get(url)

        data = json['data']
        current_event = data['ticker']['current']
        next_event = data['ticker']['next']
        link = data['schedule']['link']
        current_str = next_str = None
        data = []

        if current_event:
            data.append('Now: %s' %self._format_event(current_event))
        else:
            data.append('Nothing right now')

        if next_event:
            data.append(self._format_event(next_event, now=True))

        result = '\n'.join(data)
        return f"```\n{result}\n```\nFull schedule here: {link}"


class MagicEightBall(Command):

    SLASH_COMMAND = ('/8ball [question]')
    ANSWERS = [
        "Definitivamente", "Sem dúvidas", "Você pode contar com isso", "Sinais apontam que sim",
        "Como eu vejo, sim", "Pergunta nebulosa, tente novamente", "Pergunte novamente mais tarde",
        "Melhor não te falar agora", "Não é possível prever agora", "Concentre-se e pergunte novamente",
        "Não conte com isso", "Minha resposta é não", "Minhas fontes dizem não",
        "A perspectiva não é boa", "Duvido muito",
    ]

    REGEX = re.compile("@[A-z0-9_-]+\s(.+?)\?+$", re.UNICODE)

    @reply
    async def respond(self, text, message):

        if not text.startswith('@ofensivaria_bot'):
            return False

        return random.choice(self.ANSWERS)
