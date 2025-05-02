from bot.binance_client import AsyncClient
from bot.binance_client.ws_client import BinanceWsQueueClient
from bot.binance_client.websocket_parser import parse_execution_report_message
from bot.binance_client.utils import round_step_size
from bot.logger import Logger
from bot.type import (
    SideEnum,
    OrderTypeEnum,
    OrderRespEnum,
    ApiExchangeInfo,
    ApiOrderResult,
    SymbolPriceFilterType,
    SymbolMarketLotSizeFilterType,
)
import asyncio
import traceback


def get_order_average_price(cumQuoteQty: float, filledQty: float) -> float:
    if filledQty > 0:
        return cumQuoteQty / filledQty
    else:
        return 0.0


class Strategy:
    def __init__(
        self,
        logger: Logger,
        api_client: AsyncClient,
        symbol: str,
        amount: float,
        stop_loss: float,
        take_profit: float,
        max_delay: int,  # сколько ждем после открытия позиции
        interval: int,  # сколько ждем после закрытия
    ):

        self.logger = logger.create_prefix(f"Strategy-{symbol}")

        self.api_client = api_client

        self.symbol = symbol
        self.amount = amount
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.max_delay = max_delay
        self.interval = interval

        self.market_lot_size_filter: SymbolMarketLotSizeFilterType
        self.price_filter: SymbolPriceFilterType
        self.order_list_id: int | None = None

        self.user_stream = BinanceWsQueueClient(
            logger=self.logger,
            api_client=self.api_client,
        )

        asyncio.create_task(self.user_stream.run_forever())

        self.logger.info(f"Strategy has been created for {self.symbol}")

    async def initialize(self):
        exchange_info = await self.api_client.get_exchange_info(symbol=self.symbol)
        exchange_info = ApiExchangeInfo(**exchange_info)
        symbol_info = next((s for s in exchange_info.symbols if s.symbol == self.symbol), None)

        if symbol_info:
            for f in symbol_info.filters:
                if f["filterType"] == "PRICE_FILTER":
                    self.price_filter = SymbolPriceFilterType(**f)
                elif f["filterType"] == "MARKET_LOT_SIZE":
                    self.market_lot_size_filter = SymbolMarketLotSizeFilterType(**f)

            self.logger.info(f"Market lot size filter: {self.market_lot_size_filter}")
            self.logger.info(f"Price filter: {self.price_filter}")
        else:
            self.logger.error(f"Symbol {self.symbol} not found in exchange info.")

        if not self.price_filter or not self.market_lot_size_filter:
            raise ValueError("Price filter or market lot size filter not found.")

        if self.market_lot_size_filter:
            self.amount = round_step_size(
                self.amount,
                self.market_lot_size_filter.stepSize,
            )

            if self.amount < self.market_lot_size_filter.minQty:
                raise ValueError(
                    f"Amount {self.amount} is less than minimum quantity {self.market_lot_size_filter.minQty}"
                )
            if self.amount > self.market_lot_size_filter.maxQty:
                raise ValueError(
                    f"Amount {self.amount} is greater than maximum quantity {self.market_lot_size_filter.maxQty}"
                )

    async def set_market_order(self, side: SideEnum, symbol: str, amount: float) -> ApiOrderResult:
        self.logger.info(f"Placing market order: {side.value} {amount} {symbol}")

        payload = {
            "symbol": symbol,
            "side": side,
            "type": OrderTypeEnum.MARKET,
            "quantity": amount,
            "newOrderRespType": OrderRespEnum.RESULT,
        }

        order = await self.api_client.set_order(payload)
        order = ApiOrderResult(**order)

        if order:
            self.logger.trace(f"Market order placed: {order.model_dump_json()}")
        else:
            self.logger.error(f"Failed to place order: {order}")

        return order

    async def set_sl_tp_orders(self, buy_price: float, symbol: str, amount: float):
        stop_loss_price = buy_price * (1 - self.stop_loss / 100)
        take_profit_price = buy_price * (1 + self.take_profit / 100)

        stop_loss_price = round_step_size(stop_loss_price, self.price_filter.tickSize)
        take_profit_price = round_step_size(take_profit_price, self.price_filter.tickSize)

        self.logger.info(
            f"Placing OCO TP/SL orders: {amount} {symbol}, SL={stop_loss_price}, TP={take_profit_price}"
        )

        payload = {
            "symbol": symbol,
            "side": SideEnum.SELL,
            "quantity": amount,
            "aboveType": OrderTypeEnum.TAKE_PROFIT,
            "aboveStopPrice": take_profit_price,
            "belowType": OrderTypeEnum.STOP_LOSS,
            "belowStopPrice": stop_loss_price,
            "newOrderRespType": OrderRespEnum.RESULT,
        }

        orders = await self.api_client.set_oco_orders(payload)

        self.order_list_id = orders.get("orderListId")
        self.logger.info(f"OCO SL/TP Orders set up: list_id={self.order_list_id}")

        return orders

    async def wait_for_order_or_timeout(self, timeout: int):
        async def wait_for_order():
            while True:
                message = await self.user_stream.queue.get()
                if message and message.get("e") == "executionReport":
                    event = parse_execution_report_message(message)
                    if event.status == "FILLED" and event.orderListId == self.order_list_id:
                        self.logger.info(f"OCO Order executed: {event}")
                        return event

        order_task = asyncio.create_task(wait_for_order())
        timeout_task = asyncio.create_task(asyncio.sleep(timeout))

        done, pending = await asyncio.wait(
            [order_task, timeout_task], return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        # Возвращаем результат выполненной задачи
        if order_task in done:
            return order_task.result()
        else:
            return None

    async def cancel_all_open_orders(self):
        self.logger.debug(f"Cancelling all orders for {self.symbol}")
        try:
            await self.api_client.cancel_symbol_orders(self.symbol)
            self.logger.info(f"All orders cancelled for {self.symbol}")
        except Exception as e:
            if "Unknown order sent" in str(e):
                self.logger.debug(f"No open orders to cancel for {self.symbol}")
            else:
                self.logger.error(f"Error cancelling orders: {e}")

    async def run(self):
        try:
            await self.initialize()
            await self.cancel_all_open_orders()

            self.logger.info(f"Strategy has been started")

            while True:
                # Покупаем криптовалюту
                order = await self.set_market_order(SideEnum.BUY, self.symbol, self.amount)

                buy_price = get_order_average_price(order.cummulativeQuoteQty, order.executedQty)

                self.logger.info(f"Buy order executed at price: {buy_price}")

                await self.set_sl_tp_orders(buy_price, self.symbol, self.amount)

                result = await self.wait_for_order_or_timeout(self.max_delay)

                if result:
                    self.logger.info(f"Order event handled. Proceeding to next iteration.")
                    sell_price = get_order_average_price(
                        result.cumulativeQuoteQty, result.cumulativeFilledQty
                    )

                else:
                    self.logger.warning("Timeout reached. Selling position.")
                    await self.cancel_all_open_orders()
                    sell_order = await self.set_market_order(
                        SideEnum.SELL, self.symbol, self.amount
                    )
                    sell_price = get_order_average_price(
                        sell_order.cummulativeQuoteQty, sell_order.executedQty
                    )

                pnl = (sell_price - buy_price) * self.amount
                if pnl >= 0:
                    self.logger.success(f"Profit: {pnl} ({buy_price} -> {sell_price})")
                else:
                    self.logger.error(f"Loss: {pnl} ({buy_price} -> {sell_price})")

                self.logger.info(f"Waiting for {self.interval} seconds before next trade.")
                await asyncio.sleep(self.interval)
                await self.user_stream.prune_queue()

        except Exception as e:
            self.logger.error(f"Error: {e}")
            self.logger.warning(traceback.format_exc())
