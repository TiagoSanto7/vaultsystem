"""Login de pessoas pelo AD e sessão da tela (DV-547).

Duas portas: pessoas entram pela tela com o login da empresa (AD); agentes
entram pela API com a credencial `pv_`. Aqui é a das pessoas. Adaptado do
painel do Petro Observer (painel/app/servicos/ldap.py e rotas/auth.py), sem
importar código de lá:

- bind no AD por LDAPS (porta 636), certificado validado pela CA da Petrovina
  (api/certs/ad-ca.pem); a tela não guarda senha;
- login ou senha vazios nunca tentam o bind (bind "não autenticado" do AD);
- 5 erros em 5 min por usuário ou por IP bloqueiam por 5 min (em memória);
- na fase 1 só entram os logins de VAULT_ADMINS; outro usuário do AD recebe
  "Sem acesso a esta ferramenta" (a fase 2 muda isso);
- sessão em cookie assinado (VAULT_SESSAO_SEGREDO), 12 h.
"""
import logging
import os
import re
import ssl
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger("petro_vault.sessao")
LOGIN_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
CA_PADRAO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "certs", "ad-ca.pem")
JANELA, LIMITE = 300, 5
_erros: dict = defaultdict(deque)


class AdIndisponivel(Exception):
    """Nenhum controlador de domínio respondeu."""


@dataclass
class Usuario:
    login: str
    nome: str


def normalizar(login):
    """Aceita "fulano", "PETROVINA\\fulano" ou "fulano@petrovina.local"; devolve "fulano"."""
    login = (login or "").strip().split("\\")[-1].split("@")[0].lower()
    return login if LOGIN_VALIDO.match(login) else None


def administradores():
    return {normalizar(l) for l in os.environ.get("VAULT_ADMINS", "").split(",") if normalizar(l)}


def segredo_da_sessao():
    """Segredo do cookie; vazio ou curto: a tela fica desligada (a API dos agentes não)."""
    s = os.environ.get("VAULT_SESSAO_SEGREDO", "")
    return s if len(s) >= 32 else None


class Ldap:
    def __init__(self, servidores: List[str], dominio: str, ca: str, timeout: int = 5):
        from ldap3 import FIRST, Server, ServerPool, Tls
        tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=ca, version=ssl.PROTOCOL_TLS_CLIENT)
        self.pool = ServerPool([Server(s, port=636, use_ssl=True, tls=tls, connect_timeout=timeout)
                                for s in servidores], FIRST, active=1, exhaust=True)
        self.dominio = dominio
        self.base = ",".join(f"DC={p}" for p in dominio.split("."))
        self.timeout = timeout

    def autenticar(self, login: str, senha: str) -> Optional[Usuario]:
        from ldap3 import SIMPLE, Connection
        from ldap3.core.exceptions import LDAPException
        from ldap3.utils.conv import escape_filter_chars
        login = normalizar(login)
        if not login or not senha:
            return None
        conn = Connection(self.pool, user=f"{login}@{self.dominio}", password=senha,
                          authentication=SIMPLE, receive_timeout=self.timeout, raise_exceptions=False)
        try:
            if not conn.bind():
                return None
            nome = login
            conn.search(self.base, f"(sAMAccountName={escape_filter_chars(login)})", attributes=["displayName"])
            if conn.entries and conn.entries[0].displayName.value:
                nome = str(conn.entries[0].displayName.value)
            return Usuario(login=login, nome=nome)
        except LDAPException as e:
            logger.error("AD indisponível: %s", e)
            raise AdIndisponivel(str(e)) from e
        finally:
            conn.unbind()


def ldap_do_ambiente():
    servidores = [s.strip() for s in os.environ.get("LDAP_SERVERS", "").split(",") if s.strip()]
    dominio = os.environ.get("LDAP_DOMAIN", "")
    if not servidores or not dominio:
        return None
    return Ldap(servidores, dominio, os.environ.get("LDAP_CA_FILE", CA_PADRAO))


def _bloqueado(chave):
    fila, agora = _erros[chave], time.monotonic()
    while fila and agora - fila[0] > JANELA:
        fila.popleft()
    return len(fila) >= LIMITE


def entrar(request: Request, ldap, login: str, senha: str):
    """Valida e abre a sessão. Devolve o usuário ou levanta HTTPException com
    a mensagem que a tela mostra (401, 403, 429, 503)."""
    ip = request.client.host if request.client else "?"
    quem = normalizar(login) or "?"
    chaves = (f"ip:{ip}", f"usuario:{quem}")
    if any(_bloqueado(c) for c in chaves):
        logger.warning("login bloqueado por excesso de tentativas: %s de %s", quem, ip)
        raise HTTPException(429, "Muitas tentativas. Aguarde 5 minutos e tente de novo.")
    if ldap is None:
        raise HTTPException(503, "Login desligado: LDAP_SERVERS e LDAP_DOMAIN não configurados.")
    try:
        usuario = ldap.autenticar(login, senha)
    except AdIndisponivel:
        raise HTTPException(503, "Não foi possível falar com o AD agora. Tente de novo em instantes.")
    if not usuario:
        for c in chaves:
            _erros[c].append(time.monotonic())
        logger.info("login recusado: %s de %s", quem, ip)
        raise HTTPException(401, "Usuário ou senha inválidos.")
    for c in chaves:
        _erros.pop(c, None)
    if usuario.login not in administradores():
        logger.info("login sem acesso (não é administrador): %s de %s", usuario.login, ip)
        raise HTTPException(403, "Sem acesso a esta ferramenta.")
    request.session.clear()
    request.session.update({"login": usuario.login, "nome": usuario.nome, "papel": "administrador"})
    logger.info("login: %s de %s", usuario.login, ip)
    return usuario


def administrador(request: Request):
    """Dependência das rotas da tela: sessão válida de administrador, senão 401.
    A lista de administradores é relida a cada pedido (tirar alguém do .env
    corta o acesso na hora)."""
    if "session" not in request.scope:
        raise HTTPException(503, "Tela desligada: VAULT_SESSAO_SEGREDO não configurado.")
    login = request.session.get("login")
    if not login:
        raise HTTPException(401, "Sua sessão expirou. Entre de novo.")
    if login not in administradores():
        request.session.clear()
        raise HTTPException(403, "Sem acesso a esta ferramenta.")
    return {"login": login, "nome": request.session.get("nome", login)}
