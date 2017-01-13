import config
import logging

from sanic import Sanic
from sanic.views import HTTPMethodView
from sanic.response import text

from bot import TelegramBot

logging.basicConfig()

app = Sanic()
bot = TelegramBot()


async def cleanup(*args):
    await bot.cleanup()


async def startup(*args):
    await bot.setup()


@app.middleware('request')
def validate_token(request):
    token = request.args.get('token', None)

    if not config.DEBUG and token != config.TOKEN:
        logging.error('Got a request from outside telegram. Watchout!')
        return text(':)')


class TelegramRoute(HTTPMethodView):

    async def get(self, request):
        me = await bot.me()
        info = await bot.webhook_info()
        return text("Hello! My name is {} and my webhook info is {}".format(me['result']['username'], str(info)))

    async def post(self, request):
        logging.info('%s %s %s', request.url, request.method, request.json)
        update = request.json
        await bot.process_update(update)
        return text("ok")

    async def put(self, request):
        res1, res2 = await bot.reset_webhook()
        return text('reset. response is {}, {}'.format(res1, res2))


app.add_route(TelegramRoute(), '/telegram')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000, after_start=[startup], after_stop=[cleanup], debug=config.DEBUG)
