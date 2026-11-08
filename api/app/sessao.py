"""Login de pessoas e sessão da tela.

Vault System: o padrão são contas locais do hub (tabela `usuarios`, senha em
PBKDF2-SHA256), criadas com `python -m app.cli usuario <login>` ou, na
primeira subida, por VAULT_ADMIN_LOGIN e VAULT_ADMIN_SENHA. Toda conta local
administra o workspace. O AD continua opcional: só é tentado quando
LDAP_SERVERS e LDAP_DOMAIN estão configurados e o login não é uma conta local.

Duas portas: pessoas entram pela tela com o login da empresa (AD); agentes
entram pela API com a credencial `vs_`. Aqui é a das pessoas. Sem
importar código de lá:

- bind no AD por LDAPS (porta 636), certificado validado pela CA da organização
  (LDAP_CA_FILE); a tela não guarda senha;
- login ou senha vazios nunca tentam o bind (bind "não autenticado" do AD);
- 5 erros em 5 min por usuário ou por IP bloqueiam por 5 min (em memória);
- na fase 1 só entram os logins de VAULT_ADMINS; outro usuário do AD recebe
  "Sem acesso a esta ferramenta" (a fase 2 muda isso);
- sessão em cookie assinado (VAULT_SESSAO_SEGREDO), 12 h.
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
import re
import ssl
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger("vault_system.sessao")
LOGIN_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
CA_PADRAO = None  # AD opcional: a CA vem de LDAP_CA_FILE
JANELA, LIMITE = 300, 5
_erros: dict = defaultdict(deque)


class AdIndisponivel(Exception):
    """Nenhum controlador de domínio respondeu."""


@dataclass
class Usuario:
    login: str
    nome: str


def normalizar(login):
    """Aceita "fulano", "EXEMPLO\\fulano" ou "fulano@exemplo.local"; devolve "fulano"."""
    login = (login or "").strip().split("\\")[-1].split("@")[0].lower()
    return login if LOGIN_VALIDO.match(login) else None


def administradores():
    """Logins com acesso à tela: as contas locais e, para o AD, VAULT_ADMINS."""
    do_ambiente = {normalizar(l) for l in os.environ.get("VAULT_ADMINS", "").split(",") if normalizar(l)}
    from vault_system.estado import conectar
    with conectar() as db:
        locais = {l["login"] for l in db.execute("SELECT login FROM usuarios")}
    return do_ambiente | locais


# --- contas locais ------------------------------------------------------------------

ITERACOES = 310_000


def hash_senha(senha, sal=None, iteracoes=ITERACOES):
    sal = sal or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), sal, iteracoes)
    return f"pbkdf2_sha256${iteracoes}${base64.b64encode(sal).decode()}${base64.b64encode(dk).decode()}"


def conferir_senha(senha, guardado):
    try:
        _, it, sal, dk = guardado.split("$")
        novo = hash_senha(senha, base64.b64decode(sal), int(it)).split("$")[3]
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(novo, dk)


def criar_usuario(login, senha, nome=None):
    """Cria ou troca a senha de uma conta local. Devolve o login normalizado."""
    from vault_system.estado import agora, conectar
    login = normalizar(login)
    if not login:
        raise ValueError("login inválido (use letras, números, ponto, hífen ou sublinhado)")
    if len(senha or "") < 8:
        raise ValueError("a senha precisa de pelo menos 8 caracteres")
    with conectar() as db:
        db.execute("INSERT INTO usuarios (login, nome, hash, criado_em) VALUES (?, ?, ?, ?) "
                   "ON CONFLICT(login) DO UPDATE SET hash = excluded.hash, nome = excluded.nome",
                   (login, nome or login, hash_senha(senha), agora()))
    return login


def usuario_local(login, senha):
    """(existe, Usuario ou None): existe diz se o login é de uma conta local."""
    from vault_system.estado import conectar
    login = normalizar(login)
    if not login:
        return False, None
    with conectar() as db:
        l = db.execute("SELECT login, nome, hash FROM usuarios WHERE login = ?", (login,)).fetchone()
    if not l:
        return False, None
    return True, (Usuario(login=l["login"], nome=l["nome"]) if senha and conferir_senha(senha, l["hash"]) else None)


def garantir_admin_do_ambiente():
    """Primeira subida: VAULT_ADMIN_LOGIN e VAULT_ADMIN_SENHA criam a conta, se ainda não existe."""
    login, senha = os.environ.get("VAULT_ADMIN_LOGIN", ""), os.environ.get("VAULT_ADMIN_SENHA", "")
    if not login or not senha:
        return None
    from vault_system.estado import conectar
    with conectar() as db:
        if db.execute("SELECT 1 FROM usuarios WHERE login = ?", (normalizar(login),)).fetchone():
            return None
    try:
        return criar_usuario(login, senha, os.environ.get("VAULT_ADMIN_NOME") or None)
    except ValueError as e:
        logger.error("VAULT_ADMIN_LOGIN/VAULT_ADMIN_SENHA ignorados: %s", e)
        return None


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
    local, usuario = usuario_local(login, senha)
    if not local:
        if ldap is None:
            usuario = None  # sem AD configurado, só contas locais entram
        else:
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
