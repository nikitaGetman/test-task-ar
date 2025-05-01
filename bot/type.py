from pydantic import BaseModel
from enum import Enum
from typing_extensions import Literal


class SideEnum(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class RateLimitTypeEnum(str, Enum):
    ORDERS = "ORDERS"
    REQUEST_WEIGHT = "REQUEST_WEIGHT"
    RAW_REQUESTS = "RAW_REQUESTS"


class OrderTypeEnum(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"


class IntervalEnum(str, Enum):
    SECOND = "SECOND"
    MINUTE = "MINUTE"
    HOUR = "HOUR"
    DAY = "DAY"


class OrderRespEnum(str, Enum):
    ACK = "ACK"  # default
    RESULT = "RESULT"
    FULL = "FULL"


class SymbolFilterTypeEnum(str, Enum):
    PRICE_FILTER = "PRICE_FILTER"
    PERCENT_PRICE = "PERCENT_PRICE"
    PERCENT_PRICE_BY_SIDE = "PERCENT_PRICE_BY_SIDE"
    LOT_SIZE = "LOT_SIZE"
    MIN_NOTIONAL = "MIN_NOTIONAL"
    NOTIONAL = "NOTIONAL"
    ICEBERG_PARTS = "ICEBERG_PARTS"
    MARKET_LOT_SIZE = "MARKET_LOT_SIZE"
    MAX_NUM_ORDERS = "MAX_NUM_ORDERS"
    MAX_NUM_ALGO_ORDERS = "MAX_NUM_ALGO_ORDERS"
    MAX_NUM_ICEBERG_ORDERS = "MAX_NUM_ICEBERG_ORDERS"
    MAX_POSITION = "MAX_POSITION"
    TRAILING_DELTA = "TRAILING_DELTA"


class SymbolPriceFilterType(BaseModel):
    filterType: Literal[SymbolFilterTypeEnum.PRICE_FILTER]
    maxPrice: float
    minPrice: float
    tickSize: float


class SymbolLotSizeFilterType(BaseModel):
    filterType: Literal[SymbolFilterTypeEnum.LOT_SIZE]
    maxQty: float
    minQty: float
    stepSize: float


class SymbolMarketLotSizeFilterType(BaseModel):
    filterType: Literal[SymbolFilterTypeEnum.MARKET_LOT_SIZE]
    maxQty: float
    minQty: float
    stepSize: float


class ApiAccountBalance(BaseModel):
    asset: str
    free: float
    locked: float

    @property
    def total(self) -> float:
        return self.free + self.locked


class ApiAccount(BaseModel):
    makerCommission: int
    takerCommission: int
    buyerCommission: int
    sellerCommission: int
    canTrade: bool
    canWithdraw: bool
    canDeposit: bool
    updateTime: int
    accountType: str
    balances: list[ApiAccountBalance]
    permissions: list[str]
    uid: int


class ApiResponse(BaseModel):
    code: int
    msg: str

    @property
    def is_error(self) -> bool:
        return self.code < 0


class ApiRateLimit(BaseModel):
    interval: IntervalEnum
    intervalNum: int
    limit: int
    rateLimitType: RateLimitTypeEnum


class ApiSymbolInfo(BaseModel):
    symbol: str
    filters: list[dict]


class ApiExchangeInfo(BaseModel):
    rateLimits: list[ApiRateLimit]
    symbols: list[ApiSymbolInfo]


class Trade(BaseModel):
    price: float
    qty: float
    commission: float
    commissionAsset: str
    tradeId: int


class ApiOrderResult(BaseModel):
    symbol: str
    orderId: int
    orderListId: int
    clientOrderId: str
    transactTime: int
    price: float
    origQty: float
    executedQty: float
    origQuoteOrderQty: float
    cummulativeQuoteQty: float
    status: str
    timeInForce: str
    type: OrderTypeEnum
    side: SideEnum
    workingTime: int
    selfTradePreventionMode: str
    fills: list[Trade] | None = None


class SymbolPriceWebsocketMessage(BaseModel):
    symbol: str
    price: float
    open: float
    high: float
    low: float
    volume: float
    close_time: int
    trades: int


class ExecutionReportWebsocketMessage(BaseModel):
    symbol: str
    orderId: int
    orderListId: int
    cumulativeQuoteQty: float
    cumulativeFilledQty: float
    lastExecutedPrice: float
    lastExecutedQuantity: float
    lastExecutedTime: int
    status: str
    side: str
    type: str
