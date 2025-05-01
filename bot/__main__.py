from bot.settings import settings
from bot.logger import Logger
from bot.binance_client import AsyncClient, BinanceWsQueueClient
from bot.binance_client.websocket_parser import parse_symbol_price_message
from bot.type import ApiAccount, ApiAccountBalance
from bot.strategy import Strategy
import asyncio
import traceback


async def get_user_symbol_balance(
    binance_client: AsyncClient, symbol: str
) -> ApiAccountBalance | None:
    account = await binance_client.get_account()
    account = ApiAccount(**account)

    base_asset = symbol[:-4]  # e.g. BTCUSDT -> BTC

    for balance in account.balances:
        if balance.asset == base_asset:
            return balance
    return None


async def monitor_balance_and_price(logger: Logger, binance_client: AsyncClient):
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
            # Получаем данные о цене и балансе параллельно
            symbol_price_msg = market_stream.queue.get()
            get_user_symbol_balance_task = get_user_symbol_balance(binance_client, settings.SYMBOL)

            symbol_price_msg, user_balance = await asyncio.gather(
                symbol_price_msg, get_user_symbol_balance_task
            )

            symbol_price = parse_symbol_price_message(symbol_price_msg)
            free_balance = user_balance.free if user_balance else 0
            locked_balance = user_balance.locked if user_balance else 0

            logger.info(
                f"User balance for {settings.SYMBOL}: {free_balance} free, {locked_balance} locked. Current price: {symbol_price.price}"
            )

            await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Error in monitor_balance_and_price: {e}")
            logger.warning(traceback.format_exc())


async def main():
    logger = Logger(
        service_name=settings.APP_NAME,
        console_log_enabled=True,
        console_log_level="TRACE",
        file_log_enabled=True,
        file_log_level="TRACE",
    )

    try:
        binance_client = await AsyncClient.create(
            logger=logger,
            api_key=settings.BINANCE_KEY,
            hmac_secret=settings.BINANCE_HMAC_SECRET,
            rsa_secret=settings.BINANCE_RSA_SECRET,
            # ed_secret=settings.BINANCE_ED_SECRET,
            private_key_pass=settings.PRIVATE_KEY_PASSPHRASE,
            is_testnet=True,
        )

        # Проверяем подключение к API
        try:
            account = await binance_client.get_account()
            logger.success(f"Binance API connected")

            account = ApiAccount(**account)
            for balance in account.balances:
                if balance.asset in settings.SYMBOL and len(balance.asset) > 1:
                    logger.info(f"User balance for {balance.asset}: {balance.free}")

        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            logger.warning(traceback.format_exc())
            return

        # Запускаем стратегию
        strategy = Strategy(
            logger=logger,
            api_client=binance_client,
            symbol=settings.SYMBOL,
            amount=settings.AMOUNT,
            stop_loss=settings.STOP_LOSS_PERCENT,
            take_profit=settings.TAKE_PROFIT_PERCENT,
            max_delay=settings.TIMEOUT_SEC,
            interval=settings.DELAY_BETWEEN_TRADES_SEC,
        )

        strategy_task = asyncio.create_task(strategy.run())
        monitor_task = asyncio.create_task(monitor_balance_and_price(logger, binance_client))

        done, pending = await asyncio.wait(
            [strategy_task, monitor_task], return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        if strategy_task in done and strategy_task.exception():
            logger.error(f"Strategy failed with error: {strategy_task.exception()}")

    except Exception as e:
        logger.error(f"Error during bot main loop: {e}")
        logger.warning(traceback.format_exc())
    finally:
        if binance_client:
            await binance_client.close_connection()

        logger.info("Bot is stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
