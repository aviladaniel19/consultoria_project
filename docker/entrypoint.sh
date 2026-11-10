#!/bin/sh
# Arranque del contenedor: la aplicación corre como el usuario sin privilegios `plataforma`.
#
# Las carpetas que se montan desde el equipo (data/, sources/, transform/) pueden traer
# archivos creados por root, por ejemplo por una versión anterior que corría como root.
# Ese usuario no podría escribir en ellos (PermissionError al cargar un archivo). Por eso
# el contenedor arranca como root solo para corregir los dueños y luego cede el control.
set -e

if [ "$(id -u)" = "0" ]; then
    for carpeta in /app/data /app/sources /app/transform; do
        if [ -d "$carpeta" ]; then
            # solo lo que no es del usuario; en montajes de solo lectura no hace nada
            find "$carpeta" ! -user plataforma -exec chown plataforma:plataforma {} + 2>/dev/null || true
        fi
    done
    mkdir -p /app/data/landing && chown plataforma:plataforma /app/data /app/data/landing 2>/dev/null || true
    exec setpriv --reuid=plataforma --regid=plataforma --init-groups "$@"
fi

exec "$@"
