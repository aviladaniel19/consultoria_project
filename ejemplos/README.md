# Datos de ejemplo

Archivos y una API pequeños para probar la plataforma en segundos, desde
**Cargar datos** en la web (<http://localhost:8000/cargar>).

| Archivo | Qué prueba |
| --- | --- |
| `iris.csv` | El caso más simple: CSV con comas y punto decimal |
| `iris_excel_colombia.csv` | Un CSV como lo exporta Excel en español: punto y coma, coma decimal, encabezados con tildes y codificación Latin-1. La plataforma lo detecta sola |
| `iris.xlsx` | Un archivo de Excel |

Los tres tienen los mismos 150 registros del conjunto de datos Iris (Fisher, 1936;
UCI Machine Learning Repository, CC BY 4.0), un clásico de la enseñanza de la
estadística: medidas del sépalo y del pétalo de tres especies de flores.

Ideas para probar:

- Publicar `iris.csv` **sin llave**: cada actualización reemplaza todos los datos.
- En la ficha, revisar la pestaña **Columnas** (medias, medianas, histogramas) y
  filtrar en **Explorar**, por ejemplo `species es igual a setosa`.
- Desde **Salud**, usar **Reemplazar archivo** para subir una versión nueva y ver
  cómo cambia el historial de cargas.

## API de ejemplo: DIVIPOLA del DANE

Los 1.122 municipios de Colombia con sus códigos, publicados por el DANE en
datos.gov.co (CC BY-SA 4.0). En **Cargar datos → Conectar una API**:

| Campo | Valor |
| --- | --- |
| Título | Municipios de Colombia (DIVIPOLA) |
| Dirección | `https://www.datos.gov.co/resource/gdxc-w37w.json` |
| Botón | «Es de datos.gov.co: configurar paginación» |
| Llave (en la revisión) | `cod_mpio` |

Las coordenadas vienen como texto con coma decimal (`-75,581775`), así que la
plataforma las publica como texto.
