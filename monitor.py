#!/usr/bin/env python3
"""
Monitor de Concursos Públicos - UNICAMP SIARH
https://www.siarh.unicamp.br/concurso/InscricoesAbertas.jsf

Uso:
  python monitor.py               # loop contínuo (padrão: a cada 60 min)
  python monitor.py --run-once    # executa uma vez e sai (ideal para cron)
  python monitor.py --interval 30 # loop a cada 30 minutos
  python monitor.py --test-email  # testa as configurações de e-mail
"""

import os
import re
import sys
import json
import time
import hashlib
import smtplib
import logging
import argparse
import requests
import schedule
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ── Configuração ──────────────────────────────────────────────────────────────

URL = "https://www.siarh.unicamp.br/concurso/InscricoesAbertas.jsf"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "60"))

SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
EMAIL_FROM     = os.getenv("EMAIL_FROM", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO       = os.getenv("EMAIL_TO", "")  # separe múltiplos destinatários com vírgula

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor.log"),
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Timestamp dinâmico que a página exibe (ex.: "28/05/2026 11:56 - UNICAMP")
# Precisa ser removido antes de calcular o hash para evitar falsos positivos.
_TIMESTAMP_RE = re.compile(
    r"\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}(?::\d{2})?\s*[-–]\s*UNICAMP",
    re.IGNORECASE,
)

# ── Funções de scraping ───────────────────────────────────────────────────────

def fetch_page() -> str:
    """Faz o download da página e retorna o HTML."""
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def extract_content(html: str) -> str:
    """
    Extrai o conteúdo relevante da página removendo elementos dinâmicos
    (timestamp, scripts, estilos) para evitar falsos positivos no hash.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove scripts e estilos
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # Tenta localizar a seção principal de concursos
    content_text = None
    for candidate in soup.find_all(["h4", "h3", "h2"]):
        if "Inscrições Abertas" in candidate.get_text():
            # Sobe para o container pai que engloba a listagem
            parent = candidate.find_parent(["div", "section", "main", "form", "article"])
            if parent:
                content_text = parent.get_text(separator="\n", strip=True)
                break

    if not content_text:
        # Fallback: corpo inteiro da página
        body = soup.find("body")
        content_text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

    # Remove timestamp dinâmico
    content_text = _TIMESTAMP_RE.sub("", content_text)

    # Normaliza linhas em branco consecutivas
    content_text = re.sub(r"\n{3,}", "\n\n", content_text).strip()
    return content_text


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# ── Estado persistente ────────────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

# ── Notificação por e-mail ────────────────────────────────────────────────────

def _validate_email_config() -> bool:
    missing = [v for v in ("EMAIL_FROM", "EMAIL_PASSWORD", "EMAIL_TO") if not os.getenv(v)]
    if missing:
        log.error(
            "Variáveis de e-mail não configuradas: %s. Verifique o arquivo .env",
            ", ".join(missing),
        )
        return False
    return True


def send_notification(old_content: str, new_content: str, subject_prefix: str = "") -> None:
    """Envia e-mail de notificação comparando conteúdo anterior e atual."""
    if not _validate_email_config():
        return

    recipients = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]
    if not recipients:
        raise ValueError("EMAIL_TO não contém nenhum destinatário válido.")

    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    subject = f"{subject_prefix}🔔 Atualização nos Concursos Públicos da UNICAMP"
    log.info("Preparando e-mail via %s:%s", SMTP_HOST, SMTP_PORT)
    log.info("Remetente configurado: %s", EMAIL_FROM)
    log.info("Destinatários configurados: %s", ", ".join(recipients))

    text_body = f"""Atualização detectada — Concursos Públicos UNICAMP

Página monitorada:
{URL}

Conteúdo atual:
{new_content}

Conteúdo anterior:
{old_content or "(sem estado anterior registrado)"}

Verificação realizada em {now_str}
"""

    html_body = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px">
  <h2 style="color:#1d5c9b">Atualização detectada — Concursos Públicos UNICAMP</h2>
  <p>
    Foi detectada uma mudança na página de inscrições abertas:<br>
    <a href="{URL}">{URL}</a>
  </p>
  <hr>
  <h3 style="color:#155724;background:#d4edda;padding:8px;border-radius:4px">✅ Conteúdo Atual</h3>
  <pre style="background:#f8f9fa;padding:14px;border-radius:4px;white-space:pre-wrap;font-size:13px">{new_content}</pre>
  <hr>
  <h3 style="color:#856404;background:#fff3cd;padding:8px;border-radius:4px">📋 Conteúdo Anterior</h3>
  <pre style="background:#fff3cd;padding:14px;border-radius:4px;white-space:pre-wrap;font-size:13px">{old_content or "(sem estado anterior registrado)"}</pre>
  <hr>
  <small style="color:#6c757d">Verificação realizada em {now_str}</small>
</body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())
        log.info("E-mail enviado para: %s", ", ".join(recipients))
    except smtplib.SMTPAuthenticationError:
        log.error(
            "Falha de autenticação SMTP. "
            "Para Gmail, use uma Senha de App: https://myaccount.google.com/apppasswords"
        )
        raise
    except Exception as exc:
        log.error("Falha ao enviar e-mail: %s", exc)
        raise

# ── Lógica principal de verificação ──────────────────────────────────────────

def check_for_updates() -> None:
    """Verifica se houve atualização na página e notifica se necessário."""
    log.info("Verificando: %s", URL)

    try:
        html = fetch_page()
    except requests.exceptions.ConnectionError:
        log.warning("Sem conexão com a internet. Tentará novamente no próximo ciclo.")
        return
    except requests.exceptions.HTTPError as exc:
        log.error("Erro HTTP ao acessar a página: %s", exc)
        return
    except requests.exceptions.Timeout:
        log.warning("Timeout ao acessar a página. Tentará novamente no próximo ciclo.")
        return

    content      = extract_content(html)
    current_hash = compute_hash(content)
    state        = load_state()
    old_hash     = state.get("hash")

    if old_hash is None:
        log.info("Primeira execução — estado inicial salvo.")
        save_state({
            "hash":        current_hash,
            "content":     content,
            "last_check":  datetime.now().isoformat(),
            "last_change": None,
        })
        return

    if current_hash != old_hash:
        log.info("*** MUDANÇA DETECTADA! Enviando notificação por e-mail... ***")
        try:
            send_notification(old_content=state.get("content", ""), new_content=content)
        except Exception:
            log.error("Notificação não enviada, mas o estado será atualizado mesmo assim.")
        save_state({
            "hash":        current_hash,
            "content":     content,
            "last_check":  datetime.now().isoformat(),
            "last_change": datetime.now().isoformat(),
        })
    else:
        log.info("Sem mudanças detectadas.")
        state["last_check"] = datetime.now().isoformat()
        save_state(state)


def test_email() -> None:
    """Envia um e-mail de teste para validar as configurações."""
    log.info("Enviando e-mail de teste...")
    send_notification(
        old_content="(conteúdo de exemplo — conteúdo anterior)",
        new_content="(conteúdo de exemplo — conteúdo novo)\n\nIsso é apenas um teste.",
        subject_prefix="[TESTE] ",
    )
    log.info("E-mail de teste enviado com sucesso!")

# ── Ponto de entrada ──────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor de Concursos Públicos da UNICAMP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Executa uma única verificação e encerra (ideal para uso com cron)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=CHECK_INTERVAL_MINUTES,
        metavar="MINUTOS",
        help=f"Intervalo entre verificações em minutos (padrão: {CHECK_INTERVAL_MINUTES})",
    )
    parser.add_argument(
        "--test-email",
        action="store_true",
        help="Envia um e-mail de teste e encerra",
    )
    args = parser.parse_args()

    if args.test_email:
        test_email()
        return

    if args.run_once:
        check_for_updates()
        return

    log.info("Monitor iniciado. Verificando a cada %d minuto(s).", args.interval)
    log.info("Pressione Ctrl+C para encerrar.")
    check_for_updates()  # executa imediatamente na inicialização
    schedule.every(args.interval).minutes.do(check_for_updates)
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Monitor encerrado pelo usuário.")


if __name__ == "__main__":
    main()
