# solarman2u

Monitoramento da geração de energia solar via [home.solarmanpv.com](https://home.solarmanpv.com/login),
com alertas automáticos de **início e fim de produção elétrica diária**.

Hoje os alertas são enviados por **e-mail**. A arquitetura já isola o envio
atrás de uma interface (`solarman_alerts/notifiers/`) para facilitar adicionar
WhatsApp/Telegram depois sem tocar na lógica de detecção.

## Como funciona

1. **Login**: a Solarman não publica uma API pública para login de conta
   pessoal (o app web usa endpoints internos, alguns com uma camada extra de
   criptografia RSA+AES). Por isso o login é feito automatizando o navegador
   real (Playwright) — assim o próprio JS do site cuida da parte sensível.
   Depois do login, o token de acesso (JWT) é reaproveitado via chamadas HTTP
   simples até expirar, e renovado via `refresh_token` (endpoint OAuth2 puro,
   confirmado e sem criptografia extra) sem precisar abrir navegador de novo.
2. **Coleta de dados**: com o token válido, `SolarmanClient` chama os
   endpoints internos de listagem de usinas e status/potência atual.
3. **Detecção de início/fim**: `production_monitor.py` guarda em
   `data/state.json` o estado do dia por usina e dispara no máximo um alerta
   de início e um de fim por dia, com um filtro de confirmações consecutivas
   para não confundir uma nuvem passageira com o fim da geração.
4. **Notificação**: hoje via SMTP (`solarman_alerts/notifiers/email.py`).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env
# edite o .env com usuário/senha da Solarman e dados do SMTP
```

O `.env` e a pasta `.secrets/` (sessão do navegador) e `data/` (tokens,
estado diário, logs) **nunca são versionados** — já estão no `.gitignore`.

### Primeiro login

Duas formas, como pedido:

**a) Usuário/senha do `.env`** (automático, mas pode falhar se a Solarman
exigir captcha/verificação extra no seu login):

```bash
python scripts/check_production.py
```

Na primeira execução, se não houver sessão salva, ele tenta logar sozinho
usando `SOLARMAN_USERNAME`/`SOLARMAN_PASSWORD` do `.env`.

**b) Login manual no navegador** (recomendado se aparecer captcha, ou se
você preferir não guardar a senha em texto no `.env`):

```bash
python scripts/login_browser.py
```

Abre um Chromium visível, você loga normalmente (inclusive captcha/2FA), e a
sessão fica salva em `.secrets/storage_state.json` / `data/tokens.json` para
ser reaproveitada. O sistema tenta renovar essa sessão sozinho antes dela
expirar (`refresh_token`); se a renovação falhar, ele tenta o login
automático do `.env` e, faltando isso, é preciso rodar o login manual de novo.

### Conferir os nomes reais dos campos da API

Os endpoints internos usados (`maintain-s/...`) foram identificados via
engenharia reversa do bundle JS do site — não são documentados oficialmente.
Depois do primeiro login, rode:

```bash
python scripts/dump_station_data.py
```

e confira no JSON impresso qual campo representa a potência instantânea (W)
da sua conta. Se não bater com nenhum candidato em
`POWER_FIELD_CANDIDATES` (em `solarman_alerts/client.py`), adicione o nome
correto na lista.

### Rodando periodicamente (cron)

```
*/5 6-20 * * * cd /caminho/do/projeto && .venv/bin/python scripts/check_production.py >> data/cron.log 2>&1
```

A cada execução ele verifica a potência atual de cada usina e decide se deve
disparar o alerta de início ou de fim do dia (o estado fica em
`data/state.json`, reiniciado automaticamente à meia-noite local).

## Configuração (`.env.example`)

| Variável | Descrição |
|---|---|
| `SOLARMAN_USERNAME` / `SOLARMAN_PASSWORD` | credenciais da conta Solarman |
| `SOLARMAN_STATION_IDS` | IDs das usinas a monitorar (vazio = todas) |
| `PRODUCTION_START_THRESHOLD_W` | potência mínima para considerar "começou a gerar" |
| `PRODUCTION_END_THRESHOLD_W` | potência abaixo da qual conta como "parou" |
| `PRODUCTION_END_CONFIRMATIONS` | leituras consecutivas abaixo do limiar para confirmar o fim |
| `PRODUCTION_END_NOT_BEFORE` | não considera fim de produção antes desse horário (evita falso positivo de manhã) |
| `SMTP_*`, `ALERT_EMAIL_*` | envio do e-mail de alerta |
| `LOCAL_TIMEZONE` | fuso usado nos horários exibidos e no reset diário |

## Limitações conhecidas

- Os endpoints usados não são uma API pública/oficial — podem mudar sem
  aviso. Se algo parar de funcionar, o primeiro passo é rodar
  `scripts/dump_station_data.py` e comparar com o que o site mostra no
  DevTools do navegador.
- Login automático por usuário/senha pode ser bloqueado por captcha; nesse
  caso use `scripts/login_browser.py`.
- Os nomes de campo de potência (`POWER_FIELD_CANDIDATES`) são um melhor
  esforço e podem precisar de ajuste manual na primeira execução real.

## Próximos passos sugeridos

- Adicionar notificador de WhatsApp/Telegram implementando `Notifier`
  (`solarman_alerts/notifiers/base.py`) e plugando em
  `scripts/check_production.py`.
- Usar `maintain-s/history/power/{id}/record` (curva de potência do dia) para
  enriquecer o alerta de fim de dia com energia total gerada (kWh).
