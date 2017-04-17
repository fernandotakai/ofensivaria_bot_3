import io
import asyncio
import aiohttp
import aioredis
import logging

from ofensivaria import config
from stevedore import extension

logging.basicConfig(format='%(asctime)s:%(levelname)s:%(name)s: %(message)s',
                    level=logging.INFO)


class TelegramBot:

    def __init__(self):
        self._repolling = 2
        self._redis = None
        self._url = 'https://api.telegram.org/bot{}'.format(config.TOKEN)
        self._file_url = 'https://api.telegram.org/file/bot{}/'.format(config.TOKEN)
        self.__setup = False
        self.__processed_status = set()
        self.__logger = logging.getLogger('telegram-bot')
        self.__logger.setLevel(config.LOGGING_LEVEL)

    @property
    def was_initialized(self):
        return self.__setup

    async def __request(self, path, method="get", data=None, headers=None):
        url = "{}/{}".format(self._url, path)
        kwargs = {'timeout': 30}

        if headers:
            kwargs['headers'] = headers

        if data:
            if method == 'get':
                kwargs.update({'params': data})
            else:
                kwargs.update({'data': data})

        self.__logger.debug('Sending a %s request to %s with args %s', method, url, kwargs)
        async with self.client.request(method, url, **kwargs) as response:
            response = await response.json()
            return response

    async def get_updates(self):
        data = None

        if self.__processed_status:
            data = dict(offset=max(self.__processed_status) + 1)

        response = await self.__request('getUpdates', data=data)
        return response.get('result', [])

    async def send_message(self, chat_id, message, in_reply_to=None, preview=False, markdown=False):
        data = dict(chat_id=chat_id, text=message)

        if in_reply_to:
            data['reply_to_message_id'] = int(in_reply_to)

        data['disable_web_page_preview'] = 'true' if not preview else 'false'

        if markdown:
            data['parse_mode'] = 'Markdown'

        return await self.__request('sendMessage', 'post', data=data)

    async def send_document(self, chat_id, file_id_or_url, in_reply_to=None, preview=False):
        data = dict(chat_id=chat_id, document=file_id_or_url)

        if in_reply_to:
            data['reply_to_message_id'] = int(in_reply_to)

        headers = {}

        return await self.__request('sendDocument', 'post', data=data, headers=headers)

    async def send_photo(self, chat_id, file_id_or_url, caption=None, in_reply_to=None, preview=False):
        data = dict(chat_id=chat_id, photo=file_id_or_url)

        if in_reply_to:
            data['reply_to_message_id'] = int(in_reply_to)

        if caption:
            data['caption'] = caption

        return await self.__request('sendPhoto', 'post', data=data, headers={})

    async def me(self):
        return await self.__request('getMe')

    async def webhook_info(self):
        return await self.__request('getWebhookInfo')

    async def reset_webhook(self):
        data = {
            'url': '{}?token={}'.format(config.URL, config.TOKEN)
        }

        res1 = await self.__request('deleteWebhook')
        res2 = await self.__request('setWebhook', 'post', data=data)

        return res1, res2

    async def get_file(self, file_id):
        data = {'file_id': file_id}

        return await self.__request('getFile', data=data)

    async def download_file(self, file_path):
        url = "{}/{}".format(self._file_url, file_path)

        async with self.client.get(url) as response:
            return io.BytesIO(await response.read())

    async def get_processed_ids(self):
        updates = await self.redis.smembers('bot:updates')
        return set(map(int, updates))

    def __extension_manager_callback(self, ext, *args, **kwargs):
        self.__logger.info('Loading command %s', ext.name)
        return ext.obj

    async def setup(self):
        self.redis = await aioredis.create_redis((config.REDIS_HOST, config.REDIS_PORT,),)
        self.__processed_status = await self.get_processed_ids()
        print(self.__processed_status)
        self.client = aiohttp.ClientSession()

        extension_manager = extension.ExtensionManager(namespace='ofensivaria.bot.commands',
                                                       invoke_on_load=True,
                                                       invoke_args=(self, self.redis, self.client))

        self.commands = extension_manager.map(self.__extension_manager_callback)
        self.__setup = True

    async def polling(self):
        if not self.__setup:
            raise Exception("Cannot start polling without setting up first")

        while True:
            updates = await self.get_updates()

            for update in updates:
                self.__logger.info("Processing %s", update)
                await self.process_update(update)

            self.__logger.info("Sleeping for %s", self._repolling)
            await asyncio.sleep(self._repolling)

    async def process_update(self, update):
        id = update['update_id']
        if id in self.__processed_status:
            return

        await self.redis.sadd('bot:updates', id)
        self.__processed_status.add(id)
        print(self.__processed_status)

        message = update.get('message')

        if message:
            for command in self.commands:
                try:
                    await command.process(self, message)
                except Exception as e:
                    self.__logger.exception(e)

    async def cleanup(self):
        self.redis.close()
        await self.redis.wait_closed()
        await self.client.close()
