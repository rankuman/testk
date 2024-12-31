import asyncio
import discord
import yt_dlp as youtube_dl
from discord.ext import commands
from discord.ext.commands import Bot
from threading import Thread
from flask import Flask

# 봇의 토큰을 코드에 직접 작성합니다.
TOKEN = "MTMyMDU2MDU2ODc5NjU3NzgxNQ.GO54Hy.TtID57Z-hUr0I8IbnFTuXJhf_DqIzZsmq9P-A8"  # 여기에 실제 봇 토큰을 입력하세요.

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda: ''

# Flask 서버 설정
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord Bot is Running!"

# Youtube-DL 설정
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # bind to ipv4
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.current_player = None
        self.max_queue_size = 10  # 대기열 최대 길이 설정

    @commands.command(aliases=["입장"])
    async def join(self, ctx):
        """음성 채널에 입장합니다"""
        if not ctx.author.voice:
            await ctx.send("음성 채널에 먼저 입장해주세요.")
            return

        channel = ctx.author.voice.channel
        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()
        await ctx.send(f"{channel} 채널에 입장했습니다.")

    async def play_next(self, ctx):
        """다음 곡을 자동으로 재생합니다"""
        if len(self.queue) > 0:
            await self.skip(ctx)

    @commands.command(aliases=["다음"])
    async def skip(self, ctx):
        """대기열에서 다음 곡을 재생합니다"""
        if not ctx.voice_client:
            await ctx.send("봇이 음성 채널에 연결되어 있지 않습니다.")
            return

        if not self.queue:
            await ctx.send("다음 재생할 곡이 대기열에 없습니다.\n음악을 계속 재생하시려면 음악을 추가해주세요.")
            return

        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        try:
            current_url, current_title = self.queue.pop(0)

            async with ctx.typing():
                self.current_player = await YTDLSource.from_url(current_url, loop=self.bot.loop, stream=True)
                ctx.voice_client.play(self.current_player, after=lambda _: asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop))

                await ctx.send(f'지금 재생 중: {self.current_player.title}')

        except Exception as e:
            await ctx.send(f"재생 중 오류가 발생했습니다: {str(e)}")
            print(f"재생 오류: {e}")
            if current_url and current_title:
                self.queue.insert(0, (current_url, current_title))

    @commands.command(aliases=["재생"])
    async def play(self, ctx, *, url):
        """URL에서 음악을 재생하고 대기열에 추가합니다"""

        try:
            if not ctx.author.voice:
                await ctx.send("음성 채널에 먼저 입장해주세요.")
                return

            if not ctx.voice_client:
                await ctx.author.voice.channel.connect()

            if len(self.queue) >= self.max_queue_size:
                await ctx.send(f"대기열이 가득 찼습니다. 최대 {self.max_queue_size}곡까지만 추가할 수 있습니다.")
                return

            async with ctx.typing():
                player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                self.queue.append((url, player.title))
                if not ctx.voice_client.is_playing():
                    await self.skip(ctx)
                else:
                    queue_info = f'대기열에 "{player.title}" 노래가 추가되었습니다.\n현재 대기열 ({len(self.queue)}곡):\n'
                    for i, (_, title) in enumerate(self.queue, 1):
                        queue_info += f"{i}. {title}\n"
                    await ctx.send(queue_info)

        except Exception as e:
            await ctx.send(f"음악을 추가하는 중 오류가 발생했습니다: {str(e)}")
            print(f"재생 오류: {e}")

    @commands.command()
    async def stop(self, ctx):
        """재생을 멈추고 음성 채널에서 나갑니다"""
        if not ctx.voice_client:
            await ctx.send("봇이 음성 채널에 연결되어 있지 않습니다.")
            return

        self.queue.clear()
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("재생을 멈추고 채널에서 나갔습니다.")

    # 추가된 명령어들 (예: volume, pause, resume 등)...

    @play.before_invoke
    @skip.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("음성 채널에 먼저 입장해주세요.")
                raise commands.CommandError("사용자가 음성 채널에 연결되어 있지 않습니다.")

# Flask 서버를 실행하는 함수
def run_flask():
    app.run(host='0.0.0.0', port=5000)

async def run_bot():
    await bot.start(TOKEN)  # 여기서 TOKEN을 사용하여 봇을 시작합니다.

def start():
    # Flask를 별도의 스레드에서 실행합니다.
    flask_thread = Thread(target=run_flask)
    flask_thread.start()
    # Discord 봇을 실행합니다.
    asyncio.run(run_bot())

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"),
    description='토뭉이 사용 명령어 입니다.',
    intents=intents,
)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

bot.add_cog(Music(bot))  # 봇에 음악 기능 추가

start()  # Flask 서버와 봇을 동시에 실행
