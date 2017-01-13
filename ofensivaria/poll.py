import asyncio
import uvloop

from ofensivaria.bot import TelegramBot

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


async def main(bot):
    await bot.setup()
    await bot.polling()

if __name__ == "__main__":
    bot = TelegramBot()
    loop = asyncio.get_event_loop()

    try:
        loop.run_until_complete(main(bot))
    except KeyboardInterrupt:
        print('Closing')
    finally:
        loop.run_until_complete(bot.cleanup())
        loop.close()
