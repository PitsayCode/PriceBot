# -*- coding: utf-8 -*-
"""
cofre.py
--------
Cofre de contas criptografado (SQLite). Guarda TODAS as contas usadas pelo
robô e o histórico de acessos de cada uma.

Objetivo de segurança: quem copiar o arquivo dados/cofre.db e abrir num
visualizador de SQLite NÃO descobre nada sobre os acessos — nem e-mails,
nem senhas, nem datas, nem quantas vezes cada conta entrou, nem o tamanho
real dos dados.

Como funciona (envelope encryption):

    senha-mestra ──scrypt(salt, N=2^17, r=8)──▶ KEK (chave de embrulho)
    KEK ──AES-256-GCM──▶ DEK  (chave aleatória de 256 bits, gravada cifrada)
    DEK ──HKDF──┬──▶ chave_dados   → cifra cada conta com AES-256-GCM
                └──▶ chave_indice  → HMAC-SHA256 do e-mail ("índice cego")

    Tabela contas:  id aleatório | índice cego | nonce + dados cifrados

Detalhes que fecham vazamentos laterais:
    - Cada registro usa o próprio id como dado autenticado (AAD): colar o
      conteúdo de uma linha em outra é detectado.
    - O JSON é preenchido até blocos de 4 KB antes de cifrar: todos os
      registros ficam do mesmo tamanho, sem denunciar o tamanho do e-mail,
      da senha ou quantos acessos cada conta já teve.
    - Tabelas WITHOUT ROWID com id aleatório: a ordem física das linhas não
      revela a ordem de cadastro.
    - PRAGMA secure_delete: contas removidas são sobrescritas no arquivo.
    - Trocar a senha-mestra só re-embrulha a DEK; as contas não são tocadas.

Limites honestos: a QUANTIDADE de registros é visível; enquanto o cofre está
desbloqueado as chaves ficam na memória do processo; e sem a senha-mestra
não existe recuperação.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import string
import struct
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import config

VERSAO_FORMATO = "1"
SCRYPT_PARAMETROS = {"n": 2**17, "r": 8, "p": 1}   # ~128 MB de memória por tentativa
# 4 KB comporta o histórico cheio (20 acessos): todo registro fica com o MESMO
# tamanho, então nem o volume de acessos de uma conta aparece no arquivo.
TAMANHO_BLOCO = 4096
MAX_HISTORICO = 20
MAX_DETALHE = 80
MIN_SENHA_MESTRA = 8

_AAD_DEK = b"pricebot/cofre/dek/v1"
_ESQUEMA = """
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor BLOB NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS contas (
    id     TEXT PRIMARY KEY,
    indice TEXT NOT NULL UNIQUE,
    dados  BLOB NOT NULL
) WITHOUT ROWID;
"""


class SenhaMestraIncorreta(ValueError):
    """Senha-mestra errada (ou cabeçalho do cofre adulterado)."""


class CofreBloqueado(RuntimeError):
    """Operação que exige o cofre desbloqueado."""


@dataclass
class Conta:
    id: str
    email: str
    senha: str
    apelido: str = ""
    criada_em: str = ""
    ultimo_login: str | None = None
    total_logins: int = 0
    status: str = "nova"            # nova | ativa | falhou
    historico: list[dict] = field(default_factory=list)   # mais recente primeiro

    def para_json(self) -> bytes:
        dados = asdict(self)
        dados.pop("id")
        return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------------
# utilitários
# ---------------------------------------------------------------------------
def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _caminho(caminho: Path | str | None) -> Path:
    return Path(caminho) if caminho else config.ARQUIVO_COFRE


def mascarar_email(email: str) -> str:
    """'pricebot.123@example.com' -> 'pr••••••@example.com' (bom para logs e vídeos)."""
    local, arroba, dominio = email.partition("@")
    if not arroba:
        return "•••"
    return f"{local[:2]}{'•' * max(3, min(len(local) - 2, 6))}@{dominio}"


def gerar_conta_de_teste() -> tuple[str, str]:
    """E-mail e senha aleatórios para o site de treinamento."""
    email = f"pricebot.{datetime.now():%Y%m%d%H%M%S}.{secrets.token_hex(2)}@example.com"
    alfabeto = string.ascii_letters + string.digits
    return email, "".join(secrets.choice(alfabeto) for _ in range(16))


def _validar_senha_mestra(senha: str) -> None:
    if len(senha) < MIN_SENHA_MESTRA:
        raise ValueError(f"A senha-mestra precisa ter pelo menos {MIN_SENHA_MESTRA} caracteres.")


@contextmanager
def _conectar(caminho: Path) -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(caminho, timeout=15)
    try:
        con.execute("PRAGMA secure_delete = ON")
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def _preencher(dados: bytes) -> bytes:
    corpo = struct.pack(">I", len(dados)) + dados
    tamanho = -(-len(corpo) // TAMANHO_BLOCO) * TAMANHO_BLOCO
    return corpo + bytes(tamanho - len(corpo))


def _remover_preenchimento(bloco: bytes) -> bytes:
    (tamanho,) = struct.unpack(">I", bloco[:4])
    return bloco[4:4 + tamanho]


def _derivar_kek(senha: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(senha.encode("utf-8"))


def _subchave(dek: bytes, rotulo: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"pricebot/cofre/" + rotulo).derive(dek)


def _gravar_envelope(con: sqlite3.Connection, senha: str, dek: bytes) -> None:
    salt = os.urandom(16)
    kek = _derivar_kek(senha, salt, **SCRYPT_PARAMETROS)
    nonce = os.urandom(12)
    dek_cifrada = nonce + AESGCM(kek).encrypt(nonce, dek, _AAD_DEK)
    kdf = json.dumps({"alg": "scrypt", **SCRYPT_PARAMETROS, "salt": salt.hex()})
    con.executemany(
        "INSERT OR REPLACE INTO meta (chave, valor) VALUES (?, ?)",
        [("versao", VERSAO_FORMATO), ("kdf", kdf), ("dek", dek_cifrada)],
    )


def _abrir_envelope(con: sqlite3.Connection, senha: str) -> bytes:
    meta = dict(con.execute("SELECT chave, valor FROM meta").fetchall())
    try:
        kdf = json.loads(meta["kdf"])
        bruto = bytes(meta["dek"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("O arquivo do cofre está corrompido.") from exc
    kek = _derivar_kek(senha, bytes.fromhex(kdf["salt"]), kdf["n"], kdf["r"], kdf["p"])
    try:
        return AESGCM(kek).decrypt(bruto[:12], bruto[12:], _AAD_DEK)
    except InvalidTag:
        raise SenhaMestraIncorreta("Senha-mestra incorreta.") from None


# ---------------------------------------------------------------------------
# cofre
# ---------------------------------------------------------------------------
class Cofre:
    """Use Cofre.criar(...) ou Cofre.abrir(...) — nunca o construtor direto."""

    def __init__(self, caminho: Path, dek: bytes):
        self.caminho = caminho
        self._dek: bytes | None = dek
        self._aes: AESGCM | None = AESGCM(_subchave(dek, b"dados"))
        self._chave_indice: bytes | None = _subchave(dek, b"indice")

    # --- ciclo de vida ------------------------------------------------------
    @staticmethod
    def existe(caminho: Path | str | None = None) -> bool:
        caminho = _caminho(caminho)
        if not caminho.is_file():
            return False
        try:
            with _conectar(caminho) as con:
                return con.execute("SELECT 1 FROM meta WHERE chave = 'dek'").fetchone() is not None
        except sqlite3.DatabaseError:
            return False

    @staticmethod
    def quantidade(caminho: Path | str | None = None) -> int:
        """Número de contas — a única informação que o arquivo não esconde."""
        caminho = _caminho(caminho)
        if not Cofre.existe(caminho):
            return 0
        with _conectar(caminho) as con:
            return con.execute("SELECT COUNT(*) FROM contas").fetchone()[0]

    @classmethod
    def criar(cls, senha_mestra: str, caminho: Path | str | None = None) -> "Cofre":
        caminho = _caminho(caminho)
        _validar_senha_mestra(senha_mestra)
        if cls.existe(caminho):
            raise FileExistsError("Já existe um cofre neste local.")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        dek = AESGCM.generate_key(bit_length=256)
        with _conectar(caminho) as con:
            con.executescript(_ESQUEMA)
            _gravar_envelope(con, senha_mestra, dek)
        return cls(caminho, dek)

    @classmethod
    def abrir(cls, senha_mestra: str, caminho: Path | str | None = None) -> "Cofre":
        caminho = _caminho(caminho)
        if not cls.existe(caminho):
            raise FileNotFoundError("Nenhum cofre de contas foi criado ainda.")
        with _conectar(caminho) as con:
            dek = _abrir_envelope(con, senha_mestra)
        return cls(caminho, dek)

    @property
    def desbloqueado(self) -> bool:
        return self._dek is not None

    def bloquear(self) -> None:
        """Descarta as chaves da memória (o objeto deixa de funcionar)."""
        self._dek = self._aes = self._chave_indice = None

    def trocar_senha_mestra(self, senha_atual: str, nova_senha: str) -> None:
        self._exigir_desbloqueado()
        _validar_senha_mestra(nova_senha)
        with _conectar(self.caminho) as con:
            if not hmac.compare_digest(_abrir_envelope(con, senha_atual), self._dek):
                raise SenhaMestraIncorreta("Senha-mestra atual incorreta.")
            _gravar_envelope(con, nova_senha, self._dek)

    # --- criptografia de registros -------------------------------------------
    def _exigir_desbloqueado(self) -> None:
        if not self.desbloqueado:
            raise CofreBloqueado("O cofre está bloqueado.")

    def _indice(self, email: str) -> str:
        normalizado = email.strip().lower().encode("utf-8")
        return hmac.new(self._chave_indice, normalizado, hashlib.sha256).hexdigest()

    @staticmethod
    def _aad(conta_id: str) -> bytes:
        return b"pricebot/cofre/conta/" + conta_id.encode("ascii")

    def _cifrar(self, conta: Conta) -> bytes:
        nonce = os.urandom(12)
        return nonce + self._aes.encrypt(nonce, _preencher(conta.para_json()), self._aad(conta.id))

    def _decifrar(self, conta_id: str, blob: bytes) -> Conta:
        blob = bytes(blob)
        try:
            plano = self._aes.decrypt(blob[:12], blob[12:], self._aad(conta_id))
        except InvalidTag:
            raise ValueError(f"O registro {conta_id[:8]}… foi adulterado ou não pertence a este cofre.") from None
        dados = json.loads(_remover_preenchimento(plano))
        nomes = {f.name for f in fields(Conta)}
        return Conta(id=conta_id, **{k: v for k, v in dados.items() if k in nomes})

    # --- contas ---------------------------------------------------------------
    def listar(self) -> list[Conta]:
        """Todas as contas, das usadas mais recentemente para as mais antigas."""
        self._exigir_desbloqueado()
        with _conectar(self.caminho) as con:
            linhas = con.execute("SELECT id, dados FROM contas").fetchall()
        contas = [self._decifrar(conta_id, dados) for conta_id, dados in linhas]
        return sorted(contas, key=lambda c: (c.ultimo_login or "", c.criada_em), reverse=True)

    def obter(self, conta_id: str) -> Conta:
        self._exigir_desbloqueado()
        with _conectar(self.caminho) as con:
            linha = con.execute("SELECT dados FROM contas WHERE id = ?", (conta_id,)).fetchone()
        if linha is None:
            raise KeyError("Conta não encontrada no cofre.")
        return self._decifrar(conta_id, linha[0])

    def buscar_por_email(self, email: str) -> Conta | None:
        """Busca pelo índice cego — o e-mail nunca é comparado em texto claro no banco."""
        self._exigir_desbloqueado()
        with _conectar(self.caminho) as con:
            linha = con.execute("SELECT id, dados FROM contas WHERE indice = ?", (self._indice(email),)).fetchone()
        return self._decifrar(*linha) if linha else None

    def salvar_conta(self, email: str, senha: str, apelido: str = "") -> Conta:
        """Adiciona a conta — ou, se o e-mail já estiver no cofre, atualiza a senha."""
        self._exigir_desbloqueado()
        email = email.strip()
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            raise ValueError("Informe um e-mail válido.")
        if not senha:
            raise ValueError("A senha da conta não pode ficar vazia.")

        indice = self._indice(email)
        with _conectar(self.caminho) as con:
            linha = con.execute("SELECT id, dados FROM contas WHERE indice = ?", (indice,)).fetchone()
            if linha:
                conta = self._decifrar(*linha)
                conta.email, conta.senha = email, senha
                conta.apelido = apelido.strip() or conta.apelido
            else:
                conta = Conta(id=secrets.token_hex(16), email=email, senha=senha,
                              apelido=apelido.strip(), criada_em=_agora())
            con.execute("INSERT OR REPLACE INTO contas (id, indice, dados) VALUES (?, ?, ?)",
                        (conta.id, indice, self._cifrar(conta)))
        return conta

    def registrar_login(self, conta_id: str, resultado: str, detalhe: str = "") -> Conta:
        """Grava um acesso no histórico cifrado. resultado: 'login' | 'cadastro' | 'falha'."""
        self._exigir_desbloqueado()
        with _conectar(self.caminho) as con:
            linha = con.execute("SELECT dados FROM contas WHERE id = ?", (conta_id,)).fetchone()
            if linha is None:
                raise KeyError("Conta não encontrada no cofre.")
            conta = self._decifrar(conta_id, linha[0])
            agora = _agora()
            conta.historico = ([{"quando": agora, "resultado": resultado, "detalhe": detalhe[:MAX_DETALHE]}]
                               + conta.historico)[:MAX_HISTORICO]
            if resultado in ("login", "cadastro"):
                conta.status = "ativa"
                conta.total_logins += 1
                conta.ultimo_login = agora
            else:
                conta.status = "falhou"
            con.execute("UPDATE contas SET dados = ? WHERE id = ?", (self._cifrar(conta), conta_id))
        return conta

    def remover(self, conta_id: str) -> None:
        self._exigir_desbloqueado()
        with _conectar(self.caminho) as con:
            con.execute("DELETE FROM contas WHERE id = ?", (conta_id,))


def relatorio_invasor(caminho: Path | str | None = None) -> str:
    """Tudo o que alguém consegue ler abrindo o banco SEM a senha-mestra."""
    caminho = _caminho(caminho)
    if not Cofre.existe(caminho):
        return "Nenhum cofre criado ainda."
    with _conectar(caminho) as con:
        meta = con.execute("SELECT chave, valor FROM meta ORDER BY chave").fetchall()
        contas = con.execute("SELECT id, indice, dados FROM contas").fetchall()

    tamanho = f"{caminho.stat().st_size:,}".replace(",", ".")
    linhas = [
        f"$ sqlite3 {caminho.name}        ({tamanho} bytes)",
        "Isto é TUDO o que alguém lê abrindo o banco sem a senha-mestra:",
        "",
        "TABELA meta  (parâmetros públicos + chave dos dados cifrada)",
    ]
    for chave, valor in meta:
        if isinstance(valor, bytes):
            mostrado = f"{valor[:20].hex()}…  [{len(valor)} bytes cifrados]"
        else:
            mostrado = str(valor)
        linhas.append(f"  {chave:<7} {mostrado}")

    linhas += ["", f"TABELA contas  ({len(contas)} registro{'s' if len(contas) != 1 else ''})",
               f"  {'id':<13} {'indice (HMAC)':<21} dados (AES-256-GCM)"]
    for conta_id, indice, dados in contas:
        dados = bytes(dados)
        linhas.append(f"  {conta_id[:10]}…  {indice[:18]}…  {dados[:16].hex()}…  [{len(dados)} bytes]")

    linhas += [
        "",
        "✗ nenhum e-mail   ✗ nenhuma senha   ✗ nenhuma data   ✗ nenhum nº de logins",
        "✗ tamanhos iguais (preenchimento)   ✗ ordem das linhas aleatória",
    ]
    return "\n".join(linhas)
