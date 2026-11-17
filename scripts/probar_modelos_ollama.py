"""Sprint 0, ítem 7: compara modelos locales de Ollama sobre 10 valores reales de SURDOC.

Se ejecuta en el PC propio (no en GitHub Actions ni en la nube), con Ollama corriendo:

    ollama pull qwen2.5:3b && ollama pull llama3.2:3b && ollama pull gemma2:2b
    uv run python scripts/probar_modelos_ollama.py qwen2.5:3b llama3.2:3b gemma2:2b

Para cada modelo mide aciertos, tiempo por valor y si el modelo quedó cargado en GPU
(campo size_vram de /api/ps). Imprime una tabla Markdown lista para pegar en docs/sprint0.md.

Las categorías son PROVISORIAS: la lista definitiva se define con la arqueóloga en el Sprint 2.
Esto es solo una prueba de factibilidad; no es el normalizador del pipeline.
"""

import json
import os
import statistics
import sys
import time

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

CATEGORIAS = [
    "cerámica",
    "lítico",
    "óseo",
    "metal",
    "vidrio",
    "madera",
    "textil",
    "fibra vegetal",
    "malacológico",
    "cuero",
    "otro",
]

# (surdoc_id, objeto, técnica/material declarado, descripción, categoría esperada)
CASOS = [
    (
        "16-1771",
        "Arpón",
        "",
        "Fragmento presumiblemente de un arpón por su morfología y formas "
        "de desgaste. Objeto hecho de huesos de ballena, con un extremo puntiagudo.",
        "óseo",
    ),
    (
        "16-1073",
        "Canasto",
        "",
        "Contenedor de forma cónica con tapa y tirante. De forma cónica "
        "con una base más ancha y una boca de menor sección. Tejida con junquillo.",
        "fibra vegetal",
    ),
    (
        "16-3366",
        "Sombrero",
        "",
        "Sombrero de terciopelo verde. Posee forma circular con malla "
        "negra en el frente. En su interior tiene armazón de alambre.",
        "textil",
    ),
    (
        "16-2089",
        "Boleadora",
        "",
        "Objeto lítico, de forma esférica con una ranura por todo el "
        "contorno. De color gris. Formaba parte de una boleadora.",
        "lítico",
    ),
    (
        "16-910",
        "Disco (arqueológico)",
        "Metal",
        "Fragmento circular de metal color oscuro con "
        "manchas verdosas y blancas de superficie irregular.",
        "metal",
    ),
    (
        "16-1002",
        "Lito geométrico",
        "Piedra",
        "Elemento lítico de forma subcircular e irregular, "
        "elaborado en piedra de color café oscuro.",
        "lítico",
    ),
    (
        "16-924",
        "Lana",
        "",
        "Objeto de color beige, compuesto por multiples fibras de animal "
        "enredadas y, en forma de madeja, con extremos sueltos.",
        "textil",
    ),
    # Caso trampa: la ficha declara "Madera", pero la descripción es claramente cerámica.
    (
        "16-872",
        "Fragmento (cerámica)",
        "Madera",
        "Fragmento cerámico monocromático, pasta uniforme con diferente coloración en el interior.",
        "cerámica",
    ),
    (
        "16-1770",
        "Fragmento de hueso",
        "",
        "Fósil de forma casi rectangular. Presenta apariencia "
        "ósea, con superficie alargada y bordes irregulares.",
        "óseo",
    ),
    (
        "16-844",
        "Botella",
        "Vidrio",
        "Objeto cilíndrico, angosto en su parte superior con "
        "abertura circular y hueco, de color negro.",
        "vidrio",
    ),
]

ESQUEMA = {
    "type": "object",
    "properties": {
        "valor": {"type": "string", "enum": CATEGORIAS},
        "confianza": {"type": "number"},
        "justificacion": {"type": "string"},
    },
    "required": ["valor", "confianza", "justificacion"],
}

INSTRUCCIONES = (
    "Eres un asistente de registro de colecciones arqueológicas. Clasifica el MATERIAL principal "
    "del objeto en exactamente una de estas categorías: " + ", ".join(CATEGORIAS) + ". "
    "Si el material declarado contradice la descripción, confía en la descripción y baja la "
    "confianza. Responde solo JSON con 'valor', 'confianza' (0 a 1) y 'justificacion' breve."
)


def clasificar(cliente: httpx.Client, modelo: str, caso: tuple) -> tuple[dict | None, float]:
    _, objeto, declarado, descripcion, _ = caso
    mensaje = (
        f"Objeto: {objeto}\nTécnica/Material declarado: {declarado or '(vacío)'}\n"
        f"Descripción: {descripcion}"
    )
    inicio = time.perf_counter()
    respuesta = cliente.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": modelo,
            "messages": [
                {"role": "system", "content": INSTRUCCIONES},
                {"role": "user", "content": mensaje},
            ],
            "format": ESQUEMA,
            "stream": False,
            "options": {"temperature": 0},
        },
    )
    duracion = time.perf_counter() - inicio
    respuesta.raise_for_status()
    try:
        return json.loads(respuesta.json()["message"]["content"]), duracion
    except (json.JSONDecodeError, KeyError):
        return None, duracion


def usa_gpu(cliente: httpx.Client, modelo: str) -> str:
    for m in cliente.get(f"{OLLAMA_URL}/api/ps").json().get("models", []):
        if m.get("name", "").startswith(modelo) or m.get("model", "").startswith(modelo):
            vram, total = m.get("size_vram", 0), m.get("size", 0) or 1
            return f"{100 * vram / total:.0f}% en GPU"
    return "desconocido"


def main(modelos: list[str]) -> None:
    filas = []
    with httpx.Client(timeout=300) as cliente:
        for modelo in modelos:
            print(f"\n== {modelo}")
            clasificar(cliente, modelo, CASOS[0])  # calentamiento: carga el modelo en memoria
            tiempos, aciertos, invalidos = [], 0, 0
            for caso in CASOS:
                salida, duracion = clasificar(cliente, modelo, caso)
                tiempos.append(duracion)
                if salida is None:
                    invalidos += 1
                    print(f"  {caso[0]:8} JSON inválido ({duracion:.1f} s)")
                    continue
                ok = salida["valor"] == caso[4]
                aciertos += ok
                print(
                    f"  {caso[0]:8} {'OK ' if ok else 'MAL'} {salida['valor']:14} "
                    f"(esperado {caso[4]}, conf {salida['confianza']}, {duracion:.1f} s)"
                )
            filas.append(
                (
                    modelo,
                    aciertos,
                    invalidos,
                    statistics.median(tiempos),
                    max(tiempos),
                    usa_gpu(cliente, modelo),
                )
            )

    print("\n| Modelo | Aciertos | JSON inválido | Tiempo mediano / valor | Máximo | GPU |")
    print("|---|---|---|---|---|---|")
    for modelo, aciertos, invalidos, mediana, maximo, gpu in filas:
        print(
            f"| {modelo} | {aciertos}/{len(CASOS)} | {invalidos} | {mediana:.1f} s | "
            f"{maximo:.1f} s | {gpu} |"
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Uso: python scripts/probar_modelos_ollama.py MODELO [MODELO ...]")
    main(sys.argv[1:])
