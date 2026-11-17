# Vocabulario controlado del observatorio

**Estado: provisorio (Sprint 2).** Las categorías deben validarse con la arqueóloga antes de publicar métricas.

| Archivo | Contenido |
|---|---|
| `categorias.csv` | Categorías comparables por campo, con una descripción (va al prompt del LLM) y palabras clave (detección de conflictos con la descripción, sin acentos, separadas por `;`). |
| `terminos.csv` | Términos que aparecen en las fichas, con su fuente (`aat`, `tesauro_regional` u `observatorio` para términos sin enlace), ID, sinónimos y categoría. Se cargan en la tabla `vocabulario`. |

Cómo se usa (`pipeline/normalize/reglas.py`):

1. **Regla por ID:** si el valor de la ficha enlaza a un término AAT o del Tesauro Regional que está en `terminos.csv`, se usa su categoría.
2. **Sinónimo:** si no hay ID conocido, se busca el texto (sin mayúsculas ni acentos) entre el término preferido y los sinónimos.
3. **LLM:** lo que no resuelven las reglas va al modelo local, que solo puede elegir una categoría de `categorias.csv`.

Decisiones abiertas para revisar con la arqueóloga:

- **Fibra vegetal / textil:** los tres modelos probados en el Sprint 0 clasificaron un canasto de junquillo como "textil". Aquí "textil" es fibra animal o tela y "fibra vegetal" incluye la cestería; la técnica (tejido) se registra aparte.
- **Términos sin regla a propósito:** Guaica, Disco (arqueológico), Lito geométrico, Piedra perforada, "Piedra" como objeto, Instrumento y Lana. Su categoría depende de la descripción o de criterio experto, así que pasan por el LLM y la revisión.
- **Tipo de objeto:** las categorías son funcionales (proyectil y arma, boleadora, herramienta, contenedor, adorno y vestuario, embarcación, fragmento). Conviene contrastarlas con la tipología que use la disciplina.
