import json
import aiohttp


class BinanceAPIException(Exception):
    def __init__(self, response: aiohttp.ClientResponse, status_code: int, text: str):
        self.code = 0
        try:
            json_res = json.loads(text)
        except ValueError:
            self.message = f"Invalid JSON error message from Binance: {text}"
        else:
            self.code = json_res.get("code")
            self.message = json_res.get("msg")
        self.status_code = status_code
        self.response = response
        self.request = getattr(response, "request", None)

    def __str__(self):
        return f"APIError(status={self.status_code}, code={self.code}): {self.message}"


class BinanceRequestException(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return f"BinanceRequestException: {self.message}"


class BinanceWebsocketUnableToConnect(Exception):
    pass
