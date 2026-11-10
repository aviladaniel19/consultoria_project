FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[transform]"

COPY sources ./sources
COPY transform ./transform

# La aplicación no corre como root. uid 1000 coincide con el primer usuario de la mayoría de
# servidores Linux. El contenedor arranca como root solo para corregir los dueños de las
# carpetas montadas (sources/, data/, transform/) y enseguida pasa a ese usuario: ver
# docker/entrypoint.sh. sed quita los CR por si git convirtió el script a finales de Windows.
RUN useradd --uid 1000 --create-home plataforma \
    && mkdir -p data/landing \
    && chown -R plataforma:plataforma /app
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod 755 /usr/local/bin/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["entrypoint.sh"]
CMD ["uvicorn", "plataforma.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
