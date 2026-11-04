from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsOperadorOrdenTrabajo, EsVendedor, es_jefe_taller
from apps.documentos.gallery import bloquear
from apps.documentos.models import ArchivoAdjunto, GaleriaBorrador
from apps.media.gallery import limite, modificar, subir
from apps.media.serializers import (
    CargaGaleriaSerializer,
    GaleriaRespuestaSerializer,
    IdentificadorGaleriaSerializer,
    ModificarGaleriaSerializer,
)
from apps.media.storage import privado
from apps.proformas.services import _exigir_proforma_editable, _proforma_bloqueada


class CrearGaleriaSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    origen = serializers.UUIDField(required=False)
    sesion = serializers.UUIDField()
    detalle = serializers.IntegerField(required=False)

    def validate(self, attrs):
        if attrs.get("detalle") and attrs.get("origen"):
            raise serializers.ValidationError("No puedes clonar sobre una línea existente.")
        return attrs


class GaleriaViewSet(viewsets.GenericViewSet):
    lookup_value_regex = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    permission_classes = [EsVendedor]
    queryset = GaleriaBorrador.objects.none()
    serializer_class = CrearGaleriaSerializer

    @extend_schema(request=CrearGaleriaSerializer, responses=IdentificadorGaleriaSerializer)
    @transaction.atomic
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("id"):
            existente = GaleriaBorrador.objects.filter(
                pk=data["id"], propietario=request.user, sesion=data["sesion"]
            ).first()
            if existente:
                return Response({"id": str(existente.pk)})
        detalle = None
        if data.get("detalle"):
            from apps.proformas.models import DetalleProforma

            detalle = get_object_or_404(DetalleProforma, pk=data["detalle"])
            proforma = _proforma_bloqueada(detalle.proforma_id, request.user)
            _exigir_proforma_editable(proforma)
            if detalle.tipo_item.codigo != "MUEBLE_MEDIDA":
                raise serializers.ValidationError({"detalle": "Sólo para muebles a pedido."})
            existente = GaleriaBorrador.objects.filter(detalle=detalle).first()
            if existente:
                return Response({"id": str(existente.pk)})
        galeria = GaleriaBorrador.objects.create(
            propietario=request.user,
            sesion=data["sesion"],
            detalle=detalle,
            **({"id": data["id"]} if data.get("id") else {}),
        )
        if data.get("origen"):
            origen = bloquear(data["origen"], request.user)
            if origen.imagenes.count() > limite():
                raise serializers.ValidationError(
                    {"origen": "La galería de origen supera el límite configurado."}
                )
            from uuid import uuid4

            from django.core.files.base import ContentFile

            nuevos = []
            try:
                for imagen in origen.imagenes.all():
                    source = privado() if imagen.privado else default_storage

                    def copiar(key):
                        with source.open(key, "rb") as stream:
                            result = privado().save(
                                f"galerias/{uuid4()}.webp", ContentFile(stream.read())
                            )
                        nuevos.append(result)
                        return result

                    key = copiar(imagen.ruta_storage)
                    variantes = {w: copiar(k) for w, k in imagen.variantes.items()}
                    galeria.imagenes.create(
                        nombre=imagen.nombre,
                        nombre_storage=key.split("/")[-1],
                        ruta_storage=key,
                        variantes=variantes,
                        dimensiones=imagen.dimensiones,
                        posicion=imagen.posicion,
                        principal=imagen.principal,
                        sha256=imagen.sha256,
                        privado=True,
                        created_by=request.user,
                        mime_type=imagen.mime_type,
                        tamano_bytes=imagen.tamano_bytes,
                    )
            except Exception:
                for key in nuevos:
                    privado().delete(key)
                raise
        if detalle:
            ArchivoAdjunto.objects.filter(proforma_detalle=detalle).update(galeria=galeria)
        return Response({"id": str(galeria.pk)}, status=201)

    @extend_schema(methods=["GET"], responses=GaleriaRespuestaSerializer)
    @extend_schema(
        methods=["POST"], request=CargaGaleriaSerializer, responses=GaleriaRespuestaSerializer
    )
    @extend_schema(
        methods=["PATCH"], request=ModificarGaleriaSerializer, responses=GaleriaRespuestaSerializer
    )
    @action(detail=True, methods=["get", "post", "patch"], url_path="imagenes")
    @transaction.atomic
    def imagenes(self, request, pk=None):
        from apps.documentos.services import adjunto_publico

        galeria = bloquear(pk, request.user, editar=request.method != "GET")
        qs = galeria.imagenes.all()
        if request.method == "POST":
            archivo = request.FILES.get("archivo")
            if not archivo:
                raise serializers.ValidationError({"archivo": "Selecciona una imagen."})

            def crear(**kw):
                mime, size = kw.pop("mime"), kw.pop("size")
                return qs.create(
                    **kw,
                    galeria=galeria,
                    nombre_storage=kw["ruta_storage"].split("/")[-1],
                    mime_type=mime,
                    tamano_bytes=size,
                    privado=True,
                    created_by=request.user,
                    updated_by=request.user,
                    proforma_detalle=galeria.detalle,
                    proforma=galeria.detalle.proforma if galeria.detalle else None,
                )

            subir(qs, archivo, crear, storage=privado(), prefijo="galerias/")
        elif request.method == "PATCH":
            modificar(qs, request.data)
        galeria.save(update_fields=["actualizado"])
        return Response({"imagenes": [adjunto_publico(i) for i in qs], "limite": limite()})


class ImagenPrivadaViewSet(viewsets.GenericViewSet):
    pagination_class = None
    filter_backends = []
    lookup_value_regex = r"\d+"
    permission_classes = [EsOperadorOrdenTrabajo]
    queryset = ArchivoAdjunto.objects.none()
    serializer_class = CrearGaleriaSerializer

    @extend_schema(
        responses=GaleriaRespuestaSerializer,
        parameters=[OpenApiParameter("detalle", OpenApiTypes.INT, required=True)],
    )
    @transaction.atomic
    def list(self, request):
        from apps.documentos.services import adjunto_publico
        from apps.proformas.models import DetalleProforma

        try:
            detalle_id = int(request.query_params.get("detalle", ""))
        except (ValueError, TypeError):
            raise serializers.ValidationError({"detalle": "Indica una línea válida."})
        detalle = get_object_or_404(DetalleProforma, pk=detalle_id)
        exigir_lectura(detalle.proforma_id, request.user)
        return Response(
            {
                "imagenes": [
                    adjunto_publico(i)
                    for i in ArchivoAdjunto.objects.filter(proforma_detalle=detalle)
                ],
                "limite": limite(),
            }
        )

    @extend_schema(
        responses={
            (200, "image/webp"): OpenApiTypes.BINARY,
            (200, "image/jpeg"): OpenApiTypes.BINARY,
            (200, "image/png"): OpenApiTypes.BINARY,
        }
    )
    @transaction.atomic
    def retrieve(self, request, pk=None):
        imagen = get_object_or_404(
            ArchivoAdjunto.objects.select_related("proforma_detalle__proforma", "galeria"), pk=pk
        )
        if imagen.proforma_id:
            exigir_lectura(imagen.proforma_id, request.user)
        elif not imagen.galeria_id or imagen.galeria.propietario_id != request.user.id:
            from rest_framework.exceptions import NotFound

            raise NotFound()
        storage = privado() if imagen.privado else default_storage
        key = imagen.variantes.get(request.query_params.get("ancho"), imagen.ruta_storage)
        from botocore.exceptions import ClientError
        from rest_framework.exceptions import NotFound

        try:
            stream = storage.open(key, "rb")
        except FileNotFoundError as exc:
            raise NotFound("La imagen no está disponible.") from exc
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                raise NotFound("La imagen no está disponible.") from exc
            raise
        response = FileResponse(stream, content_type=imagen.mime_type or "image/webp")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


def exigir_lectura(proforma_id, actor):
    if es_jefe_taller(actor) and not (actor.is_staff or actor.is_superuser):
        from apps.ordenes_trabajo.models import OrdenTrabajo

        if not OrdenTrabajo.objects.filter(pedido__proforma_id=proforma_id).exists():
            from rest_framework.exceptions import NotFound

            raise NotFound()
    else:
        from apps.proformas.models import Proforma

        qs = Proforma.objects.all()
        if not (actor.is_staff or actor.is_superuser):
            qs = qs.filter(vendedor=actor)
        get_object_or_404(qs, pk=proforma_id)
        _proforma_bloqueada(proforma_id, actor)
