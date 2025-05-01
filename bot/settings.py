from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, field_validator, ValidationError
from typing_extensions import Self
from pathlib import Path
import argparse


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    APP_NAME: str = "trading-bot"
    APP_VERSION: str = "0.1.0"

    BINANCE_KEY: str
    IS_TESTNET: bool = True

    BINANCE_HMAC_SECRET: str | None = None
    BINANCE_RSA_SECRET: str | None = None
    BINANCE_ED_SECRET: str | None = None
    PRIVATE_KEY_PASSPHRASE: str | None = None

    SYMBOL: str  # название пары для покупки
    AMOUNT: float  # кол-во токенов для покупки

    STOP_LOSS_PERCENT: float
    TAKE_PROFIT_PERCENT: float

    # Если в течение 1 минуты ничего не произошло, то вся криптовалюта должна быть продана
    TIMEOUT_SEC: int = 60
    # После каждой продажи через некоторое время скрипт закупается опять и ждёт заданный интервал.
    DELAY_BETWEEN_TRADES_SEC: int = 30

    @field_validator(
        "BINANCE_HMAC_SECRET", "BINANCE_RSA_SECRET", "BINANCE_ED_SECRET", mode="before"
    )
    def validate_secret_keys(cls, value):
        """
        Если передан путь к файлу, открывает файл и считывает содержимое.
        """
        if isinstance(value, str):
            value = value.strip()
            if Path(value).is_file():
                try:
                    with open(value, "r") as f:
                        return f.read().strip()
                except Exception as e:
                    raise ValidationError(f"Failed to read secret key from file: {e}")
            return value

    @model_validator(mode="after")
    def validate_model(self) -> Self:
        if not any(
            [
                self.BINANCE_HMAC_SECRET,
                self.BINANCE_RSA_SECRET,
                self.BINANCE_ED_SECRET,
            ]
        ):
            raise ValidationError("At least one secret key must be provided.")
        return self


def parse_args():
    parser = argparse.ArgumentParser(description="Trading Bot Settings")
    parser.add_argument("--BINANCE_KEY", type=str, help="Binance API Key")
    parser.add_argument("--BINANCE_HMAC_SECRET", type=str, help="Binance HMAC API Secret")
    parser.add_argument("--BINANCE_RSA_SECRET", type=str, help="Binance RSA API Secret")
    parser.add_argument("--BINANCE_ED_SECRET", type=str, help="Binance ED255519 API Secret")
    parser.add_argument("--PRIVATE_KEY_PASSPHRASE", type=str, help="Passphrase for private key")
    parser.add_argument("--IS_TESTNET", type=bool, help="Testnet flag")
    parser.add_argument("--SYMBOL", type=str, help="Trading pair symbol")
    parser.add_argument("--AMOUNT", type=float, help="Amount of tokens to buy")
    parser.add_argument("--STOP_LOSS_PERCENT", type=float, help="Stop loss percentage")
    parser.add_argument("--TAKE_PROFIT_PERCENT", type=float, help="Take profit percentage")
    parser.add_argument("--TIMEOUT_SEC", type=int, help="Timeout in seconds")
    parser.add_argument(
        "--DELAY_BETWEEN_TRADES_SEC", type=int, help="Delay between trades in seconds"
    )
    return vars(parser.parse_args())


cli_args = parse_args()
settings = Settings(**{k: v for k, v in cli_args.items() if v is not None})
