"""Transformaciones de datos de la app, sin Streamlit (se prueban con pytest)."""

import pandas as pd

ESTADOS = {
    "revisado": "Revisado por persona",
    "propuesto": "Propuesto por el sistema",
    "en_revision": "En revisión",
}
ORDEN_ESTADOS = list(ESTADOS.values())
CAMPOS_TABLA = {"objeto": "tipo", "material": "material", "estado_conservacion": "conservacion"}
NOMBRES_CAMPO = {
    "objeto": "Tipo de objeto",
    "material": "Material",
    "tecnica": "Técnica",
    "estado_conservacion": "Estado de conservación",
}
SIN_DATO = "Sin normalizar"


def tabla_fichas(fichas: list[dict], valores: list[dict]) -> pd.DataFrame:
    """Una fila por ficha con el valor vigente principal (orden 0) de cada campo normalizado."""
    df = pd.DataFrame(fichas)
    if df.empty:
        return df
    v = pd.DataFrame(valores)
    for campo, columna in CAMPOS_TABLA.items():
        if v.empty:
            df[columna], df[f"{columna}_estado"] = SIN_DATO, SIN_DATO
            continue
        principal = v[(v["campo"] == campo) & (v["orden"] == 0)][["surdoc_id", "valor", "estado"]]
        principal = principal.rename(columns={"valor": columna, "estado": f"{columna}_estado"})
        df = df.merge(principal, on="surdoc_id", how="left")
        df[columna] = df[columna].fillna(SIN_DATO)
        df[f"{columna}_estado"] = df[f"{columna}_estado"].map(ESTADOS).fillna(SIN_DATO)
    df["numero"] = df["surdoc_id"].str.split("-").str[1].astype(int)
    return df.sort_values("numero").drop(columns="numero").reset_index(drop=True)


def indicadores(fichas: list[dict], valores: list[dict]) -> dict:
    estados = pd.Series([v["estado"] for v in valores], dtype="object")
    total = len(estados)
    return {
        "fichas": len(fichas),
        "valores": total,
        "revisados": int((estados == "revisado").sum()),
        "propuestos": int((estados == "propuesto").sum()),
        "en_revision": int((estados == "en_revision").sum()),
        "resueltos_por_reglas": sum(
            1 for v in valores if v.get("metodo") in ("regla_id", "sinonimo")
        ),
    }


def filtrar(
    df: pd.DataFrame,
    texto: str = "",
    tipos: list[str] | None = None,
    materiales: list[str] | None = None,
    conservacion: list[str] | None = None,
    colecciones: list[str] | None = None,
    validacion: list[str] | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    filtro = pd.Series(True, index=df.index)
    for columna, elegidos in (
        ("tipo", tipos), ("material", materiales), ("conservacion", conservacion),
        ("coleccion", colecciones),
    ):  # fmt: skip
        if elegidos:
            filtro &= df[columna].isin(elegidos)
    if validacion:
        estados = df[[f"{c}_estado" for c in CAMPOS_TABLA.values()]]
        filtro &= estados.isin(validacion).any(axis=1)
    if texto.strip():
        buscado = texto.strip().lower()
        unido = (
            df[["surdoc_id", "objeto", "descripcion", "coleccion", "tipo", "material"]]
            .fillna("").astype(str).agg(" ".join, axis=1).str.lower()
        )  # fmt: skip
        filtro &= unido.str.contains(buscado, regex=False)
    return df[filtro]


def conteo_por_estado(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    """Conteo por valor y estado de validación, para gráficos de barras apiladas."""
    if df.empty:
        return pd.DataFrame(columns=[columna, "Validación", "Fichas"])
    conteo = (
        df.groupby([columna, f"{columna}_estado"]).size().reset_index(name="Fichas")
        .rename(columns={f"{columna}_estado": "Validación"})
    )  # fmt: skip
    totales = conteo.groupby(columna)["Fichas"].transform("sum")
    return conteo.assign(_total=totales).sort_values(["_total", columna]).drop(columns="_total")


def valores_de_ficha(valores: list[dict], surdoc_id: str) -> pd.DataFrame:
    filas = [v for v in valores if v["surdoc_id"] == surdoc_id]
    if not filas:
        return pd.DataFrame()
    df = pd.DataFrame(filas)
    df["Campo"] = df["campo"].map(NOMBRES_CAMPO).fillna(df["campo"])
    df["Validación"] = df["estado"].map(ESTADOS)
    orden = list(NOMBRES_CAMPO)
    df["_o"] = df["campo"].map(orden.index)
    return df.sort_values(["_o", "orden"]).drop(columns="_o").reset_index(drop=True)
