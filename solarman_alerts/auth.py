from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass

import httpx

from .config import SECRETS_DIR, STORAGE_STATE_PATH, Config

logger = logging.getLogger(__name__)

TOKEN_ENDPOINT = "/oauth2-s/oauth/token"
LOGIN_PATH = "/login"

# client_id fixo usado pelo próprio app web ("test") — não é secreto, é público
# no bundle JS servido ao navegador.
OAUTH_CLIENT_ID = "test"


class LoginError(RuntimeError):
    pass


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str
    expires_in: int | None = None
    obtained_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.obtained_at:
            self.obtained_at = time.time()

    @property
    def expires_at(self) -> float:
        exp = _jwt_exp(self.access_token)
        if exp is not None:
            return exp
        if self.expires_in is not None:
            return self.obtained_at + self.expires_in
        # sem informação de expiração: assume vida curta para forçar refresh cedo
        return self.obtained_at + 300

    def is_expired(self, safety_margin_seconds: int = 60) -> bool:
        return time.time() >= (self.expires_at - safety_margin_seconds)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
            "obtained_at": self.obtained_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TokenSet":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=data.get("expires_in"),
            obtained_at=data.get("obtained_at", 0.0),
        )


def _jwt_exp(token: str) -> float | None:
    try:
        payload_b64 = token.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        return float(payload["exp"])
    except Exception:
        return None


def refresh_tokens(config: Config, refresh_token: str) -> TokenSet:
    """Renova o access_token via HTTP puro (sem browser).

    Endpoint e payload reverse-engineered do bundle JS público do app
    (não documentado oficialmente) — pode quebrar se a Solarman mudar o
    contrato da API.
    """
    with httpx.Client(base_url=config.base_url, timeout=20) as client:
        response = client.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": OAUTH_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.status_code != 200:
        raise LoginError(f"Falha ao renovar sessão (HTTP {response.status_code}): {response.text[:300]}")
    data = response.json()
    if "access_token" not in data:
        raise LoginError(f"Resposta inesperada ao renovar sessão: {data}")
    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token", refresh_token),
        expires_in=data.get("expires_in"),
    )


class SliderCaptchaRequired(LoginError):
    pass


def http_password_login(config: Config) -> TokenSet:
    """Tenta logar via HTTP puro, sem browser.

    Payload (`grant_type=mdc_password`, `clear_text_pwd`, `identity_type`)
    reverse-engineered de um chunk JS lazy-loaded do app (não documentado
    oficialmente). Na prática a Solarman costuma exigir um captcha de slider
    (`AUTH_SLIDE_ERROR`) antes de aceitar o login, o que barra esse caminho —
    nesse caso, use browser_login/interactive_browser_login.
    """
    if not config.has_credentials:
        raise LoginError("SOLARMAN_USERNAME/SOLARMAN_PASSWORD não configurados no .env.")

    identity_type = 2 if "@" in config.username else 3

    with httpx.Client(base_url=config.base_url, timeout=20) as client:
        response = client.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "mdc_password",
                "username": config.username,
                "clear_text_pwd": config.password,
                "identity_type": identity_type,
                "client_id": OAUTH_CLIENT_ID,
                "system": "SOLARMAN",
                "area": "",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code != 200:
        body = response.text[:300]
        if "SLIDE" in body.upper():
            raise SliderCaptchaRequired(
                "O login exige resolver um captcha de slider (AUTH_SLIDE_ERROR); "
                "não dá para completar via HTTP puro. Rode scripts/login_browser.py "
                "em uma máquina com acesso normal à internet para logar manualmente "
                "uma vez."
            )
        raise LoginError(f"Falha no login HTTP (HTTP {response.status_code}): {body}")

    data = response.json()
    if "access_token" not in data:
        raise LoginError(f"Resposta inesperada no login HTTP: {data}")
    logger.info("Login via HTTP puro concluído com sucesso.")
    return TokenSet(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        expires_in=data.get("expires_in"),
    )


def browser_login(config: Config, headless: bool = True, timeout_seconds: int = 60) -> TokenSet:
    """Realiza login preenchendo usuário/senha em um browser real (Playwright).

    Usar um browser de verdade evita ter que reimplementar a camada de
    criptografia (RSA+AES) usada por algumas rotas sensíveis do app, e lida
    melhor com eventuais captchas do que uma chamada HTTP crua.
    """
    if not config.has_credentials:
        raise LoginError(
            "SOLARMAN_USERNAME/SOLARMAN_PASSWORD não configurados no .env. "
            "Use scripts/login_browser.py para logar manualmente, ou preencha o .env."
        )

    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    captured: dict = {}

    def handle_response(response) -> None:
        if response.request.method != "POST" or TOKEN_ENDPOINT not in response.url:
            return
        try:
            body = response.json()
        except Exception:
            return
        if "access_token" in body:
            captured["tokens"] = body

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.on("response", handle_response)
        page.goto(f"{config.base_url}{LOGIN_PATH}", wait_until="networkidle")

        try:
            username_input = page.locator(
                'input[type="text"], input[type="email"], input[name="username"]'
            ).first
            username_input.wait_for(state="visible", timeout=timeout_seconds * 1000)
            username_input.fill(config.username)

            password_input = page.locator('input[type="password"]').first
            password_input.fill(config.password)
            password_input.press("Enter")
        except PlaywrightTimeoutError as exc:
            browser.close()
            raise LoginError(
                "Não encontrei os campos de usuário/senha na página de login. "
                "O layout do site pode ter mudado, ou pode haver captcha/verificação "
                "extra — nesse caso rode scripts/login_browser.py com --headed para "
                "logar manualmente uma vez."
            ) from exc

        deadline = time.time() + timeout_seconds
        while time.time() < deadline and "tokens" not in captured:
            page.wait_for_timeout(500)

        if "tokens" not in captured:
            browser.close()
            raise LoginError(
                "Login não concluído a tempo (possível captcha/verificação em duas "
                "etapas). Rode scripts/login_browser.py com --headed para logar "
                "manualmente uma vez e reaproveitar a sessão."
            )

        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(STORAGE_STATE_PATH))
        browser.close()

    body = captured["tokens"]
    logger.info("Login via browser concluído com sucesso.")
    return TokenSet(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        expires_in=body.get("expires_in"),
    )


def interactive_browser_login(config: Config, timeout_seconds: int = 600) -> TokenSet:
    """Abre um browser visível para o usuário logar manualmente (com captcha, 2FA etc).

    Usado por scripts/login_browser.py. Mantém a sessão salva em
    .secrets/storage_state.json para reaproveitar depois.
    """
    from playwright.sync_api import sync_playwright

    captured: dict = {}

    def handle_response(response) -> None:
        if response.request.method != "POST" or TOKEN_ENDPOINT not in response.url:
            return
        try:
            body = response.json()
        except Exception:
            return
        if "access_token" in body:
            captured["tokens"] = body

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.on("response", handle_response)
        page.goto(f"{config.base_url}{LOGIN_PATH}")

        print(f"Faça login normalmente na janela do navegador (timeout: {timeout_seconds}s)...")
        deadline = time.time() + timeout_seconds
        while time.time() < deadline and "tokens" not in captured:
            page.wait_for_timeout(1000)

        if "tokens" not in captured:
            browser.close()
            raise LoginError("Tempo esgotado esperando o login manual ser concluído.")

        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(STORAGE_STATE_PATH))
        browser.close()

    body = captured["tokens"]
    print("Login manual concluído e sessão salva em", STORAGE_STATE_PATH)
    return TokenSet(
        access_token=body["access_token"],
        refresh_token=body["refresh_token"],
        expires_in=body.get("expires_in"),
    )


def load_saved_tokens() -> TokenSet | None:
    from .config import DATA_DIR

    path = DATA_DIR / "tokens.json"
    if not path.exists():
        return None
    try:
        return TokenSet.from_dict(json.loads(path.read_text()))
    except Exception:
        logger.warning("Não foi possível ler tokens salvos em %s", path)
        return None


def save_tokens(tokens: TokenSet) -> None:
    from .config import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "tokens.json"
    path.write_text(json.dumps(tokens.to_dict()))


def get_valid_tokens(config: Config) -> TokenSet:
    """Retorna um TokenSet válido, renovando ou logando de novo conforme necessário."""
    tokens = load_saved_tokens()

    if tokens is not None and not tokens.is_expired():
        return tokens

    if tokens is not None:
        try:
            logger.info("Access token expirado, tentando renovar via refresh_token...")
            tokens = refresh_tokens(config, tokens.refresh_token)
            save_tokens(tokens)
            return tokens
        except LoginError as exc:
            logger.warning("Refresh falhou (%s), tentando login completo.", exc)

    try:
        logger.info("Tentando login via HTTP puro (sem browser)...")
        tokens = http_password_login(config)
        save_tokens(tokens)
        return tokens
    except SliderCaptchaRequired as exc:
        logger.warning("%s", exc)
    except LoginError as exc:
        logger.warning("Login HTTP falhou (%s), tentando via browser.", exc)

    logger.info("Realizando login completo via browser...")
    tokens = browser_login(config, headless=True)
    save_tokens(tokens)
    return tokens
