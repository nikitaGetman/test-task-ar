from bot.logger import Logger
from .async_client import AsyncClient
import asyncio
import json
import time
from typing import Sequence, Dict, Any
import websockets


class BinanceWsQueueClient:
    WS_BASE = "wss://stream.binance.com:9443"
    WS_BASE_TESTNET = "wss://stream.testnet.binance.vision:9443"

    def __init__(
        self,
        logger: Logger,
        api_client: AsyncClient,
        queue_size: int = 10_000,
        silence_timeout: int = 60,
        reconnect_delay: int = 0,
        symbols: Sequence[str] | None = None,  # ["BTCUSDT", "ETHUSDT"]
        streams: Sequence[str] | None = None,  # ["aggTrade","depth@100ms"]
        listen_key: str | None = None,
        keep_alive_interval: int = 1_800,  # 30 min
    ) -> None:
        self.logger = logger.create_prefix(
            f"BinanceWsQueueClient-{','.join(streams) if streams else 'user'}"
        )

        self.api_client = api_client
        self.is_testnet = api_client.is_testnet

        self.base_url = self.WS_BASE_TESTNET if self.is_testnet else self.WS_BASE

        self.queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(queue_size)

        self.silence_timeout = silence_timeout
        self.reconnect_delay = reconnect_delay

        self.symbols = [s.lower() for s in symbols] if symbols else []
        self.streams = streams

        self.listen_key = listen_key
        self.keep_alive_interval = keep_alive_interval

        self._ws = None
        self._last_ts: float = 0.0
        self._heartbeat_task: asyncio.Task | None = None
        self._keepalive_task: asyncio.Task | None = None

    async def run_forever(self) -> None:
        """
        Блокирующий метод: держит соединение и переподключается при обрыве.
        """
        while True:
            try:
                url = await self._prepare_stream()
                await self._connect(url)

                await asyncio.gather(
                    self._listen_loop(),
                    self._heartbeat_loop(),
                )
            except (asyncio.CancelledError, KeyboardInterrupt):
                raise
            except Exception as e:
                self.logger.warning(f"Error: {e} — reconnecting in {self.reconnect_delay}s")
                await asyncio.sleep(self.reconnect_delay)
            finally:
                if self._ws:
                    await self._ws.close()
                    self._ws = None
                if self._keepalive_task and not self._keepalive_task.done():
                    self._keepalive_task.cancel()

    async def _prepare_stream(self) -> str:
        # --- USER STREAM --- #
        if self.symbols == []:
            if not self.listen_key:
                self.listen_key = await self.api_client.create_listen_key()
            # фоновое продление listenKey
            self._keepalive_task = asyncio.create_task(self._keep_listen_key_alive())
            return f"{self.base_url}/ws/{self.listen_key}"

        # --- MARKET STREAM --- #
        if not self.symbols or not self.streams:
            raise RuntimeError("symbols and streams are required for market stream")
        stream_names = [f"{sym.lower()}@{st}" for sym in self.symbols for st in self.streams]
        joined = "/".join(stream_names)
        return f"{self.base_url}/stream?streams={joined}"

    async def _connect(self, url: str) -> None:
        self.logger.debug(f"Connecting: {url}")
        self._ws = await websockets.connect(url, ping_interval=None)
        self._last_ts = time.time()
        self.logger.debug(f"Stream connected: {url}")

    async def prune_queue(self) -> None:
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _listen_loop(self) -> None:
        assert self._ws
        async for raw in self._ws:
            self._last_ts = time.time()
            try:
                payload = json.loads(raw)
                if "data" in payload:
                    payload = payload["data"]
            except json.JSONDecodeError:
                continue

            # self.logger.trace(f"Received message: {payload}")
            await self.queue.put(payload)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.silence_timeout / 2)
            if time.time() - self._last_ts > self.silence_timeout:
                try:
                    assert self._ws
                    await self._ws.ping()
                    self.logger.debug("sending Ping")
                except Exception:
                    self.logger.warning("Ping error - reconnecting")
                    break

    async def _keep_listen_key_alive(self) -> None:
        while True:
            await asyncio.sleep(self.keep_alive_interval)
            try:
                if self.listen_key is None:
                    self.logger.warning("listen_key is None")
                    return
                await self.api_client.keep_listen_key_alive(self.listen_key)
                self.logger.debug("Keep alive success")
            except Exception as e:
                self.logger.warning(f"Keep alive error: {e}")
                # дадим run_forever упасть — он пересоздаст listenKey
