"""Lectura segura de paquetes ZIP HOMEX y verificación SHA-256 de manifiestos."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from apps.proformas.importador_homex.excepciones import ErrorIntegridadPaquete

MAX_ENTRADAS_ZIP = 1000
MAX_TAMANO_ARCHIVO_BYTES = 25 * 1024 * 1024
MAX_TAMANO_TOTAL_BYTES = 100 * 1024 * 1024
RAIZ_PAQUETE = "HOMEX_DATA_MASTER"

ARCHIVOS_OBLIGATORIOS_DOCUMENTAL_BASE = {
    "01_catalogo/imagenes_mapeo.json",
}
ARCHIVOS_OBLIGATORIOS_DOCUMENTAL_RESOLUCION = {
    "reglas_importacion.json",
    "incidencias_decisiones.json",
    "productos_decisiones.json",
    "clientes_decisiones.json",
    "proformas_decisiones.json",
    "notas_decisiones.json",
}
ARCHIVOS_OBLIGATORIOS_ESCENARIO = {
    "catalogo_escenario.json",
    "clientes_ficticios.json",
    "plantillas_mueble.json",
    "proformas.json",
    "eventos_cronologicos.json",
    "pedidos_objetivo.json",
    "ordenes_trabajo_objetivo.json",
    "recibos_objetivo.json",
    "notas_entrega_objetivo.json",
    "movimientos_esperados.json",
    "conciliacion_stock.json",
    "resumen_validacion.json",
}


def _validar_ruta_zip(nombre: str) -> PurePosixPath:
    if not nombre or "\\" in nombre or "\x00" in nombre:
        raise ErrorIntegridadPaquete(f"Ruta ZIP inválida: {nombre!r}")
    ruta = PurePosixPath(nombre)
    if ruta.is_absolute() or ".." in ruta.parts:
        raise ErrorIntegridadPaquete(f"Ruta ZIP insegura (path traversal): {nombre!r}")
    return ruta


def _es_symlink(info: zipfile.ZipInfo) -> bool:
    modo = (info.external_attr >> 16) & 0o170000
    return modo == stat.S_IFLNK


def _sha256_bytes(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


class PaqueteMaestroHomex:
    """Acceso en memoria, seguro y verificado, al paquete HOMEX_DATA_MASTER."""

    def __init__(self, archivos: dict[str, bytes]) -> None:
        self._archivos = archivos

    @classmethod
    def desde_ruta(cls, ruta: str | Path) -> PaqueteMaestroHomex:
        path = Path(ruta)
        if not path.exists():
            raise ErrorIntegridadPaquete(f"No existe el paquete: {path}")

        if path.is_dir():
            return cls._desde_directorio(path)

        if not zipfile.is_zipfile(path):
            raise ErrorIntegridadPaquete(f"El archivo no es un ZIP válido: {path}")

        archivos: dict[str, bytes] = {}
        rutas_crudas: set[str] = set()
        total_bytes = 0
        with zipfile.ZipFile(path, "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ENTRADAS_ZIP:
                raise ErrorIntegridadPaquete(
                    f"El ZIP excede el máximo de entradas permitidas ({MAX_ENTRADAS_ZIP})."
                )
            for info in infos:
                if info.filename in rutas_crudas:
                    raise ErrorIntegridadPaquete(f"Entrada duplicada en ZIP: {info.filename!r}")
                rutas_crudas.add(info.filename)
                ruta_posix = _validar_ruta_zip(info.filename)
                if _es_symlink(info):
                    raise ErrorIntegridadPaquete(
                        f"El ZIP contiene un enlace simbólico prohibido: {info.filename}"
                    )
                if info.is_dir():
                    continue
                if info.file_size > MAX_TAMANO_ARCHIVO_BYTES:
                    raise ErrorIntegridadPaquete(
                        f"Archivo demasiado grande en ZIP: {info.filename}"
                    )
                total_bytes += info.file_size
                if total_bytes > MAX_TAMANO_TOTAL_BYTES:
                    raise ErrorIntegridadPaquete("El ZIP excede el tamaño total máximo permitido.")

                with zf.open(info, "r") as fh:
                    contenido = fh.read(MAX_TAMANO_ARCHIVO_BYTES + 1)
                if len(contenido) > MAX_TAMANO_ARCHIVO_BYTES:
                    raise ErrorIntegridadPaquete(
                        f"Archivo comprimido excede el límite real: {info.filename}"
                    )

                clave = ruta_posix.as_posix()
                if clave.startswith(f"{RAIZ_PAQUETE}/"):
                    clave = clave[len(RAIZ_PAQUETE) + 1 :]
                if clave in archivos:
                    raise ErrorIntegridadPaquete(
                        f"Colisión de ruta normalizada en ZIP: {info.filename!r} -> {clave!r}"
                    )
                archivos[clave] = contenido

        return cls(archivos)

    @classmethod
    def _desde_directorio(cls, root: Path) -> PaqueteMaestroHomex:
        base = root / RAIZ_PAQUETE if (root / RAIZ_PAQUETE).is_dir() else root
        archivos: dict[str, bytes] = {}
        total_bytes = 0
        for item in sorted(base.rglob("*")):
            if item.is_symlink():
                raise ErrorIntegridadPaquete(f"Enlace simbólico prohibido en paquete: {item}")
            if item.is_dir():
                continue
            rel = item.relative_to(base).as_posix()
            data = item.read_bytes()
            if len(data) > MAX_TAMANO_ARCHIVO_BYTES:
                raise ErrorIntegridadPaquete(f"Archivo demasiado grande: {rel}")
            total_bytes += len(data)
            if total_bytes > MAX_TAMANO_TOTAL_BYTES:
                raise ErrorIntegridadPaquete("El paquete excede el tamaño total máximo permitido.")
            archivos[rel] = data
        return cls(archivos)

    def existe(self, ruta_relativa: str) -> bool:
        return ruta_relativa in self._archivos

    def leer_bytes(self, ruta_relativa: str) -> bytes:
        if ruta_relativa not in self._archivos:
            raise ErrorIntegridadPaquete(
                f"Falta el archivo requerido en el paquete: {ruta_relativa}"
            )
        return self._archivos[ruta_relativa]

    def leer_json(self, ruta_relativa: str):
        raw = self.leer_bytes(ruta_relativa)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErrorIntegridadPaquete(f"JSON inválido en {ruta_relativa}: {exc}") from exc

    def sha256(self, ruta_relativa: str) -> str:
        return _sha256_bytes(self.leer_bytes(ruta_relativa))

    def verificar_manifiestos(self, *, perfil: str) -> dict:
        """Verifica SHA-256 de los manifiestos aplicables al perfil."""
        resumen: dict[str, int | str] = {}

        if perfil == "documental":
            resumen["manifiesto_base"] = self._verificar_manifiesto_lista(
                manifiesto_ruta="manifiesto.json",
                prefijo="",
                clave_lista="archivos",
                obligatorios=ARCHIVOS_OBLIGATORIOS_DOCUMENTAL_BASE,
            )
            resumen["manifiesto_resolucion"] = self._verificar_manifiesto_mapa(
                manifiesto_ruta="11_resolucion/manifiesto_resolucion.json",
                prefijo="11_resolucion/",
                clave_mapa="archivos_resolucion",
                obligatorios=ARCHIVOS_OBLIGATORIOS_DOCUMENTAL_RESOLUCION,
            )
        elif perfil == "escenario":
            resumen["manifiesto_escenario"] = self._verificar_manifiesto_lista(
                manifiesto_ruta="12_escenario_evaluacion/manifiesto_escenario.json",
                prefijo="12_escenario_evaluacion/",
                clave_lista="archivos",
                obligatorios=ARCHIVOS_OBLIGATORIOS_ESCENARIO,
            )
        else:
            raise ErrorIntegridadPaquete(f"Perfil no soportado: {perfil}")

        return resumen

    def _verificar_manifiesto_lista(
        self,
        *,
        manifiesto_ruta: str,
        prefijo: str,
        clave_lista: str,
        obligatorios: set[str] | None = None,
    ) -> int:
        manifiesto = self.leer_json(manifiesto_ruta)
        if not isinstance(manifiesto, dict) or not isinstance(manifiesto.get(clave_lista), list):
            raise ErrorIntegridadPaquete(
                f"{manifiesto_ruta} no contiene una lista '{clave_lista}'."
            )

        verificados = 0
        rutas_cubiertas: set[str] = set()
        for entrada in manifiesto[clave_lista]:
            if not isinstance(entrada, dict):
                raise ErrorIntegridadPaquete(f"Entrada inválida en {manifiesto_ruta}.")
            ruta_rel = entrada.get("ruta")
            sha_esperado = entrada.get("sha256")
            if not ruta_rel or not sha_esperado:
                raise ErrorIntegridadPaquete(f"Entrada incompleta en {manifiesto_ruta}: {entrada}")
            if ruta_rel in rutas_cubiertas:
                raise ErrorIntegridadPaquete(
                    f"Ruta duplicada en manifiesto {manifiesto_ruta}: {ruta_rel}"
                )
            rutas_cubiertas.add(ruta_rel)
            ruta_completa = f"{prefijo}{ruta_rel}" if prefijo else ruta_rel
            sha_actual = self.sha256(ruta_completa)
            if sha_actual != sha_esperado:
                raise ErrorIntegridadPaquete(
                    f"SHA-256 inválido para {ruta_completa}: {sha_actual} != {sha_esperado}"
                )
            verificados += 1
        if obligatorios:
            faltantes = sorted(obligatorios - rutas_cubiertas)
            if faltantes:
                raise ErrorIntegridadPaquete(
                    f"Archivos obligatorios sin cobertura en {manifiesto_ruta}: "
                    f"{', '.join(faltantes)}"
                )
        return verificados

    def _verificar_manifiesto_mapa(
        self,
        *,
        manifiesto_ruta: str,
        prefijo: str,
        clave_mapa: str,
        obligatorios: set[str] | None = None,
    ) -> int:
        manifiesto = self.leer_json(manifiesto_ruta)
        mapa = manifiesto.get(clave_mapa) if isinstance(manifiesto, dict) else None
        if not isinstance(mapa, dict):
            raise ErrorIntegridadPaquete(
                f"{manifiesto_ruta} no contiene un diccionario '{clave_mapa}'."
            )
        verificados = 0
        for ruta_rel, sha_esperado in mapa.items():
            if not ruta_rel or not sha_esperado:
                raise ErrorIntegridadPaquete(
                    f"Entrada incompleta en {manifiesto_ruta}: {ruta_rel!r}"
                )
            ruta_completa = f"{prefijo}{ruta_rel}" if prefijo else ruta_rel
            sha_actual = self.sha256(ruta_completa)
            if sha_actual != sha_esperado:
                raise ErrorIntegridadPaquete(
                    f"SHA-256 inválido para {ruta_completa}: {sha_actual} != {sha_esperado}"
                )
            verificados += 1
        if obligatorios:
            faltantes = sorted(obligatorios - set(mapa.keys()))
            if faltantes:
                raise ErrorIntegridadPaquete(
                    f"Archivos obligatorios sin cobertura en {manifiesto_ruta}: "
                    f"{', '.join(faltantes)}"
                )
        return verificados
