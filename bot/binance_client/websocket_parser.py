from bot.type import SymbolPriceWebsocketMessage, ExecutionReportWebsocketMessage


def parse_symbol_price_message(msg: dict) -> SymbolPriceWebsocketMessage:
    #   "e": "kline",         // Event type
    #   "E": 1672515782136,   // Event time
    #   "s": "BNBBTC",        // Symbol
    #   "k": {
    #     "t": 1672515780000, // Kline start time
    #     "T": 1672515839999, // Kline close time
    #     "s": "BNBBTC",      // Symbol
    #     "i": "1m",          // Interval
    #     "f": 100,           // First trade ID
    #     "L": 200,           // Last trade ID
    #     "o": "0.0010",      // Open price
    #     "c": "0.0020",      // Close price
    #     "h": "0.0025",      // High price
    #     "l": "0.0015",      // Low price
    #     "v": "1000",        // Base asset volume
    #     "n": 100,           // Number of trades
    #     "x": false,         // Is this kline closed?
    #     "q": "1.0000",      // Quote asset volume
    #     "V": "500",         // Taker buy base asset volume
    #     "Q": "0.500",       // Taker buy quote asset volume
    #     "B": "123456"       // Ignore

    return SymbolPriceWebsocketMessage(
        symbol=msg["s"],
        price=float(msg["k"]["c"]),
        open=float(msg["k"]["o"]),
        high=float(msg["k"]["h"]),
        low=float(msg["k"]["l"]),
        volume=float(msg["k"]["v"]),
        close_time=msg["k"]["T"],
        trades=msg["k"]["n"],
    )


def parse_execution_report_message(msg: dict) -> ExecutionReportWebsocketMessage:
    #   "e": "executionReport",        // Event type
    #   "E": 1499405658658,            // Event time
    #   "s": "ETHBTC",                 // Symbol
    #   "c": "mUvoqJxFIILMdfAW5iGSOW", // Client order ID
    #   "S": "BUY",                    // Side
    #   "o": "LIMIT",                  // Order type
    #   "f": "GTC",                    // Time in force
    #   "q": "1.00000000",             // Order quantity
    #   "p": "0.10264410",             // Order price
    #   "P": "0.00000000",             // Stop price
    #   "F": "0.00000000",             // Iceberg quantity
    #   "g": -1,                       // OrderListId
    #   "C": "",                       // Original client order ID; This is the ID of the order being canceled
    #   "x": "NEW",                    // Current execution type
    #   "X": "NEW",                    // Current order status
    #   "r": "NONE",                   // Order reject reason; Please see Order Reject Reason (below) for more information.
    #   "i": 4293153,                  // Order ID
    #   "l": "0.00000000",             // Last executed quantity
    #   "z": "0.00000000",             // Cumulative filled quantity
    #   "L": "0.00000000",             // Last executed price
    #   "n": "0",                      // Commission amount
    #   "N": null,                     // Commission asset
    #   "T": 1499405658657,            // Transaction time
    #   "t": -1,                       // Trade ID
    #   "v": 3,                        // Prevented Match Id; This is only visible if the order expired due to STP
    #   "I": 8641984,                  // Execution Id
    #   "w": true,                     // Is the order on the book?
    #   "m": false,                    // Is this trade the maker side?
    #   "M": false,                    // Ignore
    #   "O": 1499405658657,            // Order creation time
    #   "Z": "0.00000000",             // Cumulative quote asset transacted quantity
    #   "Y": "0.00000000",             // Last quote asset transacted quantity (i.e. lastPrice * lastQty)
    #   "Q": "0.00000000",             // Quote Order Quantity
    #   "W": 1499405658657,            // Working Time; This is only visible if the order has been placed on the book.
    #   "V": "NONE"                    // SelfTradePreventionMode

    return ExecutionReportWebsocketMessage(
        symbol=msg["s"],
        orderId=msg["i"],
        cumulativeQuoteQty=float(msg["Z"]),
        cumulativeFilledQty=float(msg["z"]),
        lastExecutedPrice=float(msg["L"]),
        lastExecutedQuantity=float(msg["l"]),
        lastExecutedTime=msg["T"],
        orderListId=msg["g"],
        status=msg["X"],
        side=msg["S"],
        type=msg["o"],
    )
