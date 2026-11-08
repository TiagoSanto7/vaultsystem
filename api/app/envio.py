"""Entrada HTTP comum para o painel e a CLI."""
import zipfile

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from vault_system import envios


async def receber(request, tag, por, modo=None, origem=None):
    pacote = bytearray()
    async for parte in request.stream():
        if len(pacote) + len(parte) > envios.MAXIMO:
            raise HTTPException(413, "O pacote excede 10 MB.")
        pacote.extend(parte)
    try:
        return await run_in_threadpool(envios.gravar, tag, pacote, por, modo, origem)
    except (ValueError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(409, str(exc)) from exc
