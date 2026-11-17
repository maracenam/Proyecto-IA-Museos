"""Reglas antes que IA: ID de término → sinónimo. Lo que no se resuelve aquí va al LLM.

Para material, además, se compara con la descripción: si la ficha declara un material
pero la descripción solo habla de otro (ej. 16-872, "fragmento cerámico" con material
"Madera"), se baja la confianza para que el valor pase por revisión humana."""

from dataclasses import dataclass, field

from pipeline.normalize.vocabulario import Vocabulario

CONFIANZA_ID = 0.99
CONFIANZA_SINONIMO = 0.95
CONFIANZA_CONFLICTO = 0.5


@dataclass(frozen=True)
class Caso:
    """Un valor a normalizar: (ficha, campo, orden) más el contexto de la ficha."""

    surdoc_id: str
    campo: str
    orden: int
    origen: str  # termino | campo | descripcion
    entrada: str
    fuente: str | None = None
    id_termino: str | None = None
    contexto: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def clave(self) -> tuple[str, str, int]:
        return (self.surdoc_id, self.campo, self.orden)


@dataclass(frozen=True)
class Propuesta:
    valor: str
    metodo: str  # regla_id | sinonimo | llm
    confianza: float
    justificacion: str
    modelo: str | None = None


def aplicar_reglas(caso: Caso, vocab: Vocabulario) -> Propuesta | None:
    if caso.origen == "descripcion":
        return None
    termino = vocab.por_id(caso.campo, caso.fuente, caso.id_termino)
    if termino is not None:
        metodo, confianza = "regla_id", CONFIANZA_ID
        motivo = f"{caso.fuente} {caso.id_termino} ({termino.preferido})"
    else:
        termino = vocab.por_texto(caso.campo, caso.entrada)
        if termino is None:
            return None
        metodo, confianza = "sinonimo", CONFIANZA_SINONIMO
        motivo = f"sinónimo de «{termino.preferido}»"
    justificacion = f"{motivo} → {termino.categoria}"

    if caso.campo == "material":
        # Conflicto solo si la descripción no menciona NINGUNO de los materiales declarados
        # en la ficha: 16-919 declara Piedra y Cuero; que la descripción hable de cuero no es error.
        declarados = {termino.categoria}
        for texto, fuente, id_termino in caso.contexto.get("materiales_declarados", ()):
            otro = vocab.por_id("material", fuente, id_termino) or vocab.por_texto(
                "material", texto
            )
            if otro:
                declarados.add(otro.categoria)
        en_descripcion = vocab.categorias_en_texto("material", caso.contexto.get("descripcion", ""))
        if en_descripcion and not (en_descripcion & declarados):
            confianza = CONFIANZA_CONFLICTO
            justificacion += (
                f". La descripción sugiere {', '.join(sorted(en_descripcion))}: revisar"
            )
    return Propuesta(termino.categoria, metodo, confianza, justificacion)
