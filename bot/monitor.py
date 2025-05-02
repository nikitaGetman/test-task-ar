from bot.settings import settings
from bot.logger import Logger
from bot.binance_client import AsyncClient, BinanceWsQueueClient
from bot.binance_client.websocket_parser import parse_symbol_price_message
from bot.type import ApiAccount, ApiAccountBalance
import asyncio
import traceback


async def get_user_symbol_balance(
    binance_client: AsyncClient, symbol: str
) -> ApiAccountBalance | None:
    """
    Получает баланс пользователя для указанного символа.
    """
    try:
        account_data = await binance_client.get_account()
        account = ApiAccount(**account_data)

        base_asset = symbol[:-4]  # e.g. BTCUSDT -> BTC

        for balance in account.balances:
            if balance.asset == base_asset:
                return balance
    except Exception as e:
        raise RuntimeError(f"Failed to fetch user balance: {e}")

    return None


async def monitor_balance_and_price(logger: Logger, binance_client: AsyncClient):
    """
    Мониторит баланс пользователя и текущую цену символа.
    """
    market_stream = BinanceWsQueueClient(
        logger=logger,
        api_client=binance_client,
        symbols=[settings.SYMBOL],
        streams=["kline_1m"],
    )

    asyncio.create_task(market_stream.run_forever())

    while True:
        try:
            await market_stream.prune_queue()

            latest_price_task = market_stream.queue.get()
            user_balance_task = get_user_symbol_balance(binance_client, settings.SYMBOL)

            latest_price_msg, user_balance = await asyncio.gather(
                latest_price_task, user_balance_task
            )

            symbol_price = parse_symbol_price_message(latest_price_msg)
            free_balance = user_balance.free if user_balance else 0
            locked_balance = user_balance.locked if user_balance else 0

            logger.info(
                f"User balance for {settings.SYMBOL}: {free_balance} free, {locked_balance} locked. Current price: {symbol_price.price}"
            )

            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Error in monitor_balance_and_price: {e}")
            logger.warning(traceback.format_exc())
