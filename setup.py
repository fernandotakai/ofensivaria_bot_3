from setuptools import setup, find_packages

setup(
    name="ofensivaria-bot",
    version="0.1",

    description="A dumb bot for telegram",

    author="Fernando Takai",
    author_email="fernando.takai@gmail.com",

    url="https://bitbucket.org/fernandotakai/ofensivaria-bot-3/",

    Platforms=["Any"],

    scripts=[],

    provides=['ofensivaria'],

    packages=find_packages(),
    include_package_data=True,

    entry_points={
        'ofensivaria.bot.commands': [
            'ping = ofensivaria.commands:Ping',
            'title = ofensivaria.commands:Title',
            'either_or = ofensivaria.commands:EitherOr',
            'help = ofensivaria.commands:Help',
            'archive_url = ofensivaria.commands:ArchiveUrl',
            'google = ofensivaria.commands:Google',
            'dance_gif = ofensivaria.commands:DanceGif',
            'message_to_gif = ofensivaria.commands:MessageToGif',
            'convert_currency = ofensivaria.commands:ConvertCurrency',
            'sandstorm = ofensivaria.commands:Sandstorm',
            'imgur = ofensivaria.commands:Imgur',
            'flip_table = ofensivaria.commands:FlipTable',
            'square_meme = ofensivaria.commands:SquareMeme',
            'shrug = ofensivaria.commands:Shrug',
        ],
    },

    zip_safe=False,
)
