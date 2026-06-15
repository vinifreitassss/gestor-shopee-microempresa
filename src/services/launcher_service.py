import os
import socket
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManagedApp:
    key: str
    nome: str
    pasta: str
    comando: str
    url: str = ""
    porta: int | None = None


APPS: list[ManagedApp] = [
    ManagedApp(
        key="pedidohub",
        nome="PedidoHub / pedidos online",
        pasta=r"C:\Users\Meu Computador\Downloads\app de pedido online\PedidoHub",
        comando="npm run dev",
        url="http://localhost:3000",
        porta=3000,
    ),
    ManagedApp(
        key="expedicao_bot",
        nome="Expedição / notas e etiquetas",
        pasta=r"C:\Users\Meu Computador\Downloads\apps nota e etiqueta\geração nota fiscais automatica\expedicao-bot",
        comando="npm start",
    ),
    ManagedApp(
        key="lista_corte",
        nome="Lista de corte",
        pasta=r"C:\Users\Meu Computador\Downloads\app de lista de corte etc",
        comando="npm run dev",
        url="http://localhost:5173",
        porta=5173,
    ),
    ManagedApp(
        key="zebraweb",
        nome="Zebraweb / etiquetas",
        pasta=r"C:\Users\Meu Computador\Downloads\Zebraweb\central",
        comando="py -m uvicorn main:app --host 0.0.0.0 --port 8757",
        url="http://localhost:8757",
        porta=8757,
    ),
]

_processes: dict[str, subprocess.Popen] = {}


def list_managed_apps() -> list[ManagedApp]:
    return APPS


def get_app(key: str) -> ManagedApp | None:
    for app in APPS:
        if app.key == key:
            return app
    return None


def start_app(key: str) -> tuple[bool, str]:
    app = get_app(key)
    if not app:
        return False, "Aplicativo não encontrado."

    existing = _processes.get(key)
    if existing and existing.poll() is None:
        return True, "Já iniciado por esta central."

    folder = Path(app.pasta)
    if not folder.exists():
        return False, f"Pasta não encontrada: {app.pasta}"

    try:
        process = subprocess.Popen(
            ["cmd", "/k", f"title {app.nome} && {app.comando}"],
            cwd=str(folder),
            creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, "CREATE_NEW_CONSOLE") else 0,
        )
    except Exception as exc:
        return False, f"Erro ao iniciar: {exc}"

    _processes[key] = process
    return True, f"Iniciado: {app.nome}"


def start_all() -> list[tuple[str, bool, str]]:
    results = []
    for app in APPS:
        ok, message = start_app(app.key)
        results.append((app.key, ok, message))
    return results


def stop_app(key: str) -> tuple[bool, str]:
    app = get_app(key)
    if not app:
        return False, "Aplicativo não encontrado."

    process = _processes.get(key)
    if not process or process.poll() is not None:
        return False, "Este app não foi iniciado por esta central nesta sessão."

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            process.terminate()
    except Exception as exc:
        return False, f"Erro ao encerrar: {exc}"

    return True, f"Encerrado: {app.nome}"


def stop_all() -> list[tuple[str, bool, str]]:
    results = []
    for app in APPS:
        ok, message = stop_app(app.key)
        results.append((app.key, ok, message))
    return results


def open_app_url(key: str) -> tuple[bool, str]:
    app = get_app(key)
    if not app:
        return False, "Aplicativo não encontrado."
    if not app.url:
        return False, "Este app não tem link local configurado."
    webbrowser.open(app.url)
    return True, f"Abrindo: {app.url}"


def open_app_folder(key: str) -> tuple[bool, str]:
    app = get_app(key)
    if not app:
        return False, "Aplicativo não encontrado."
    folder = Path(app.pasta)
    if not folder.exists():
        return False, f"Pasta não encontrada: {app.pasta}"
    if os.name == "nt":
        os.startfile(str(folder))
    else:
        subprocess.Popen(["xdg-open", str(folder)])
    return True, f"Abrindo pasta: {app.pasta}"


def get_status(key: str) -> str:
    app = get_app(key)
    if not app:
        return "Não encontrado"

    process = _processes.get(key)
    if process and process.poll() is None:
        return "Rodando pela central"

    if app.porta and _is_port_open(app.porta):
        return f"Rodando na porta {app.porta}"

    return "Parado / não detectado"


def get_status_rows() -> list[dict]:
    rows = []
    for app in APPS:
        rows.append(
            {
                "key": app.key,
                "nome": app.nome,
                "status": get_status(app.key),
                "porta": app.porta or "-",
                "url": app.url or "-",
                "comando": app.comando,
                "pasta": app.pasta,
            }
        )
    return rows


def _is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.35):
            return True
    except OSError:
        return False
