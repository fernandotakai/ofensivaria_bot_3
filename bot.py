import io
import asyncio
import config
import aiohttp
import aioredis
import commands
import logging

logging.basicConfig(format='%(asctime)s:%(levelname)s: %(message)s',
                    level=logging.INFO)


class TelegramBot:

    def __init__(self):
        self._repolling = 5
        self._redis = None
        self._url = 'https://api.telegram.org/bot{}'.format(config.TOKEN)
        self._file_url = 'https://api.telegram.org/file/bot{}/'.format(config.TOKEN)
        self.__setup = False
        self.__processed_status = set()

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

        async with self.client.request(method, url, **kwargs) as response:
            response = await response.json()
            return response

    async def get_updates(self):
        data = None

        if self.__processed_status:
            data = dict(offset=max(self.__processed_status) + 1)

        response = await self.__request('getUpdates', data=data)
        return response.get('result', [])

    async def send_message(self, chat_id, message, in_reply_to=None, preview=False):
        data = dict(chat_id=chat_id, text=message)

        if in_reply_to:
            data['reply_to_message_id'] = int(in_reply_to)

        data['disable_web_page_preview'] = 'true' if not preview else 'false'

        return await self.__request('sendMessage', 'post', data=data)

    async def send_document(self, chat_id, file_id_or_url, in_reply_to=None, preview=False):
        data = dict(chat_id=chat_id, document=file_id_or_url)

        if in_reply_to:
            data['reply_to_message_id'] = int(in_reply_to)

        headers = {}

        return await self.__request('sendDocument', 'post', data=data, headers=headers)

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

    async def setup(self):
        self.redis = await aioredis.create_redis((config.REDIS_HOST, config.REDIS_PORT,),)
        self.__processed_status = await self.get_processed_ids()
        self.client = aiohttp.ClientSession()
        self.commands = [cls(self, self.redis, self.client) for cls in commands.COMMANDS]
        self.__setup = True

    async def polling(self):
        if not self.__setup:
            raise Exception("Cannot start polling without setting up first")

        while True:
            updates = await self.get_updates()

            for update in updates:
                logging.info("Processing %s", update)
                await self.process_update(update)

            logging.info("Sleeping for %s", self._repolling)
            await asyncio.sleep(self._repolling)

    async def process_update(self, update):
        id = update['update_id']
        if id in self.__processed_status:
            return

        await self.redis.sadd('bot:updates', id)
        self.__processed_status.add(id)

        message = update.get('message')

        if message:
            for command in self.commands:
                try:
                    await command.process(self, message)
                except Exception as e:
                    logging.exception(e)

    async def cleanup(self):
        self.redis.close()
        await self.redis.wait_closed()
        await self.client.close()
