from .exceptions import (
    BinanceAPIException,
    BinanceRequestException,
    BinanceWebsocketUnableToConnect,
)
from bot.logger import Logger
import asyncio
import urllib.parse
import hashlib
import hmac
import time
import base64
from enum import Enum
from Crypto.PublicKey import RSA, ECC
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import aiohttp
import traceback
from datetime import datetime


class AsyncClient:
    API_URL = "https://api.binance.com/api"
    API_TESTNET_URL = "https://testnet.binance.vision/api"
    WS_API_URL = "wss://ws-api.binance.com/ws-api/v3"
    WS_API_TESTNET_URL = "wss://ws-api.testnet.binance.vision/ws-api/v3"

    REQUEST_RECVWINDOW: int = 10_000  #
    RETRY_DELAY = 0.2
    RETRY_ATTEMPTS = 5

    VERSION_1 = "v1"
    VERSION_2 = "v2"
    VERSION_3 = "v3"

    def __init__(
        self,
        logger: Logger,
        api_key: str | None = None,
        hmac_secret: str | None = None,
        rsa_secret: str | None = None,
        ed_secret: str | None = None,
        is_testnet: bool = True,
        private_key_pass: str | None = None,
    ):
        self.logger = logger.create_prefix("BinanceRestClient")

        self.api_key = api_key

        self.hmac_private_key = self._load_hmac_private_key(hmac_secret, private_key_pass)
        self.rsa_private_key = self._load_rsa_private_key(rsa_secret, private_key_pass)
        self.ed_private_key = self._load_ed_private_key(ed_secret, private_key_pass)

        self.is_testnet = is_testnet
        self.timestamp_offset = 0

        # self.ws_api = None
        self._is_api_timeout = False

        self.loop = asyncio.get_event_loop()

        self.session = self._init_session()

    def _is_pem_key(self, private_key: str) -> bool:
        return "-----BEGIN" in private_key and "-----END" in private_key

    def _load_pem_key(
        self,
        private_key: str,
        private_key_pass: str | None = None,
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
    ):
        # Если ключ в PEM формате, извлекаем содержимое
        try:
            private_key_obj = load_pem_private_key(
                private_key.encode("utf-8"),
                password=private_key_pass.encode("utf-8") if private_key_pass else None,
                backend=default_backend(),
            )
            return private_key_obj.private_bytes(
                encoding=encoding,
                format=format,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")

        except Exception as e:
            raise ValueError(f"Failed to parse key in PEM format: {e}")

    def _load_hmac_private_key(self, private_key: str | None, private_key_pass: str | None = None):
        if not private_key:
            return

        if self._is_pem_key(private_key):
            try:
                private_key = self._load_pem_key(private_key, private_key_pass)
            except Exception as e:
                raise ValueError(f"Failed to parse HMAC key in PEM format: {e}")

        return private_key.strip()

    def _load_rsa_private_key(self, private_key: str | None, private_key_pass: str | None = None):
        if not private_key:
            return

        if self._is_pem_key(private_key):
            try:
                private_key = self._load_pem_key(private_key, private_key_pass)
            except Exception as e:
                raise ValueError(f"Failed to parse RSA key in PEM format: {e}")

        return RSA.import_key(private_key, passphrase=private_key_pass)

    def _load_ed_private_key(self, private_key: str | None, private_key_pass: str | None = None):
        if not private_key:
            return
        # TODO

    #     if self._is_pem_key(private_key):
    #         try:
    #             private_key = self._load_pem_key(private_key, private_key_pass)
    #         except Exception as e:
    #             raise ValueError(f"Failed to parse Ed25519 key in PEM format: {e}")

    #     private_key_bytes = base64.b64decode(private_key)
    #     return Ed25519PrivateKey.from_private_bytes(private_key_bytes)

    def _init_session(self) -> aiohttp.ClientSession:
        headers = {
            # "Accept": "application/json",
            "Content-Type": "application/json;charset=utf-8",
        }
        if self.api_key:
            headers["X-MBX-APIKEY"] = self.api_key

        session = aiohttp.ClientSession(loop=self.loop, headers=headers)
        return session

    def _rsa_signature(self, query_string: str):
        if not self.rsa_private_key:
            raise ValueError("RSA Private key required for private endpoints")

        h = SHA256.new(query_string.encode("utf-8"))
        signature = pkcs1_15.new(self.rsa_private_key).sign(h)
        res = base64.b64encode(signature).decode("utf-8")
        return res

    def _ed25519_signature(self, query_string: str):
        if not self.ed_private_key or not isinstance(self.ed_private_key, Ed25519PrivateKey):
            raise ValueError("Ed25519 Private key required for private endpoints")

        return self.ed_private_key.sign(query_string.encode("utf-8")).decode("utf-8")

    def _hmac_signature(self, query_string: str) -> str:
        if not self.hmac_private_key:
            raise ValueError("HMAC Private key required for private endpoints")

        return hmac.new(
            self.hmac_private_key.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _generate_signature(self, params: dict) -> str:
        if self.rsa_private_key:
            sig_func = self._rsa_signature
        elif self.ed_private_key:
            sig_func = self._ed25519_signature
        elif self.hmac_private_key:
            sig_func = self._hmac_signature
        else:
            raise ValueError("No private key or API secret provided")

        payload = "&".join([f"{param}={value}" for param, value in params.items()])
        res = sig_func(payload)
        return res

    @classmethod
    async def create(
        cls,
        logger: Logger,
        api_key: str,
        hmac_secret: str | None = None,
        rsa_secret: str | None = None,
        ed_secret: str | None = None,
        is_testnet: bool = False,
        private_key_pass: str | None = None,
    ):
        self = cls(
            logger=logger,
            api_key=api_key,
            hmac_secret=hmac_secret,
            rsa_secret=rsa_secret,
            ed_secret=ed_secret,
            is_testnet=is_testnet,
            private_key_pass=private_key_pass,
        )

        try:
            await self.ping()

            res = await self.get_server_time()
            self.timestamp_offset = res["serverTime"] - int(time.time() * 1000)

            return self
        except Exception:
            await self.close_connection()
            raise

    async def close_connection(self):
        if self.session:
            await self.session.close()
        # if self.ws_api:
        #     await self.ws_api.close()
        #     self.ws_api = None

    def _get_timestamp(self) -> int:
        return int(time.time() * 1000) + self.timestamp_offset

    async def _parse_response(self, response: aiohttp.ClientResponse) -> dict:
        if not str(response.status).startswith("2"):
            raise BinanceAPIException(response, response.status, await response.text())
        try:
            return await response.json()
        except ValueError:
            txt = await response.text()
            raise BinanceRequestException(f"Invalid Response: {txt}")

    async def _send_request(
        self, http_method: str, uri: str, payload: dict | None = None, signed: bool = False
    ):
        if payload is None:
            payload = {}

        for key, value in payload.items():
            if isinstance(value, bool):
                payload[key] = "true" if value else "false"
            if isinstance(value, Enum):
                payload[key] = value.value

        if signed:
            payload["recvWindow"] = self.REQUEST_RECVWINDOW
            payload["timestamp"] = self._get_timestamp()

        if signed:
            signature = self._generate_signature(payload)
            payload["signature"] = signature

        if http_method.upper() in ["POST", "PUT", "DELETE"]:
            params = {"url": uri, "data": payload}
        else:
            query_string = urllib.parse.urlencode(payload, True)
            uri = f"{uri}?{query_string}"
            params = {"url": uri, "params": {}}

        method = getattr(self.session, http_method)

        response = await self._retry_async(func=method, retries=self.RETRY_ATTEMPTS, **params)
        return await self._parse_response(response)

    async def _set_api_timeout(self, reason: str, timeout: float):
        if not self._is_api_timeout:
            self._is_api_timeout = True
            self.logger.warning(
                f"Setting timeout for api requests for {timeout} secs.\nReason: {reason}",
                notify=True,
            )
            await asyncio.sleep(timeout)
            self._is_api_timeout = False
            self.logger.info("Release pause, continue to send api requests", notify=True)

    async def _retry_async(self, func, retries=RETRY_ATTEMPTS, *args, **kwargs):
        """Повторяет вызов 'func' при возникновении BinanceAPIException или других ошибок."""
        for attempt in range(1, retries + 1):
            try:
                while self._is_api_timeout:
                    await asyncio.sleep(self.RETRY_DELAY)

                if attempt > 1:
                    await asyncio.sleep(self.RETRY_DELAY)

                res = await func(*args, **kwargs)
                return res

            except asyncio.TimeoutError as e:
                self.logger.warning(f"Timeout Error (attempt {attempt}): {e}", notify=True)
            except BinanceWebsocketUnableToConnect as e:
                if "timed out" in str(e):
                    self.logger.warning(
                        f"Websocket Timeout Error (attempt {attempt}): {e}", notify=True
                    )
                else:
                    raise e

            except BinanceAPIException as e:
                # Not errors:
                # -2011 - Unknown order sent
                # -2013 - Order does not exist.
                if e.code == -2013 or e.code == -2011:
                    return e

                self.logger.warning(f"BinanceApi Error: {e}")
                if attempt == 1:
                    self.logger.warning(traceback.format_exc())

                # -1022 - Signature for this request is not valid.
                # -1121 - Invalid symbol
                # -1130 - Data sent is not valid.
                # -2025 - Reach max open order limit
                # or last iteration
                error_str = str(e)
                if (
                    "-1022" in error_str
                    or "-1121" in error_str
                    or "-1130" in error_str
                    or "-2025" in error_str
                    or attempt == retries
                ):
                    raise e

                # Обработка лимитов (429 / -1003 / x-mbx-used-weight-1m)
                # Too many requests
                status_code = getattr(e, "status_code", None)
                if (
                    status_code == 429
                    or status_code == 418
                    or "-1003" in error_str
                    or "x-mbx-used-weight-1m" in error_str
                ):
                    self.logger.debug(
                        f"Request weight limit: {func.__name__}({args=:}, {kwargs=:})"
                    )
                    self.logger.debug(traceback.format_stack())
                    response = getattr(e, "response", None)
                    headers = getattr(response, "headers", {}) if response else {}
                    retry_after = headers.get("Retry-After")

                    default_retry_after = 60 - datetime.now().second  # секунды до конца минуты
                    timeout_sec = int(retry_after) if retry_after else default_retry_after
                    await self._set_api_timeout(reason=str(e), timeout=timeout_sec)

                    if status_code == 418:
                        self.logger.warning(
                            f"IP banned for {timeout_sec} seconds. Reason: {e.message}", notify=True
                        )

            except Exception as e:
                # Ловим все остальные непредвиденные ошибки
                self.logger.error(f"Unexpected Error (attempt {attempt}): {e}", notify=True)
                self.logger.warning(traceback.format_exc())
                raise e

        raise TimeoutError("Can not fetch request, exceeded max retries count. Request timed out")

    def _create_api_uri(self, path: str, version: str) -> str:
        url = self.API_TESTNET_URL if self.is_testnet else self.API_URL
        return url + "/" + version + "/" + path

    async def _request_api(
        self,
        method: str,
        path: str,
        signed: bool = False,
        version: str = VERSION_1,
        payload: dict | None = None,
    ):
        uri = self._create_api_uri(path, version)
        return await self._send_request(http_method=method, uri=uri, signed=signed, payload=payload)

    async def _get(self, *args, **kwargs):
        return await self._request_api("get", *args, **kwargs)

    async def _post(self, *args, **kwargs):
        return await self._request_api("post", *args, **kwargs)

    async def _put(self, *args, **kwargs):
        return await self._request_api("put", *args, **kwargs)

    async def _delete(self, *args, **kwargs):
        return await self._request_api("delete", *args, **kwargs)

    # ----------- API methods ----------- #
    async def ping(self) -> dict:
        # GET /api/v3/ping
        return await self._get("ping", version=self.VERSION_3)

    async def get_server_time(self) -> dict:
        # GET /api/v3/time
        return await self._get("time", version=self.VERSION_3)

    async def get_exchange_info(self, symbol: str | None = None) -> dict:
        # GET /api/v3/exchangeInfo
        return await self._get("exchangeInfo", version=self.VERSION_3, payload={"symbol": symbol})

    async def get_account(self, omit_zero_balances=False) -> dict:
        # GET /api/v3/account
        return await self._get(
            "account",
            version=self.VERSION_3,
            signed=True,
            payload={"omitZeroBalances": omit_zero_balances},
        )

    async def set_order(self, payload: dict) -> dict:
        # POST /api/v3/order
        return await self._post("order", version=self.VERSION_3, signed=True, payload=payload)

    async def set_oco_orders(self, payload: dict) -> dict:
        # POST /api/v3/orderList/oco
        return await self._post(
            "orderList/oco", version=self.VERSION_3, signed=True, payload=payload
        )

    async def cancel_symbol_orders(self, symbol: str) -> dict:
        # DELETE /api/v3/openOrders
        return await self._delete(
            "openOrders", version=self.VERSION_3, signed=True, payload={"symbol": symbol}
        )

    async def create_listen_key(self) -> str:
        # POST /api/v3/userDataStream
        data = await self._post(
            "userDataStream",
            signed=False,
            version=self.VERSION_3,
        )
        if "listenKey" not in data:
            raise BinanceRequestException("listenKey not found in response")

        return data["listenKey"]

    async def keep_listen_key_alive(self, listen_key: str) -> None:
        # PUT /api/v3/userDataStream
        await self._put(
            "userDataStream",
            signed=False,
            version=self.VERSION_3,
            payload={"listenKey": listen_key},
        )
