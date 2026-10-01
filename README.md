# RISK METER DASHBOARD — Análisis Cuantitativo de Riesgo Financiero

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/fastapi-0.120%2B-brightgreen?logo=fastapi)
![Chart.js](https://img.shields.io/badge/chart.js-4.4%2B-ff6384?logo=chartdotjs)
![Plotly](https://img.shields.io/badge/plotly-5.20%2B-3f4f75?logo=plotly)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

**Autores:** Daniel Avila Otalora & Jhon Alexander Ocampo Gómez | **Profesor:** Javier Mauricio Sierra | **Versión:** 3.0 (Estabilizada & Pulida)

RISK METER DASHBOARD es una plataforma avanzada de análisis de riesgo financiero que combina un **backend robusto en FastAPI** con un **dashboard Single Page Application (SPA)** de alta fidelidad. Utiliza modelos econométricos, simulaciones de Monte Carlo y algoritmos de Machine Learning para proporcionar una visión profunda de la volatilidad, optimización y predicción de activos financieros.

---

## ✨ Características Principales

### 📊 Dashboard SPA (HTML5 + Chart.js + Plotly)
- **Visualización de Renta Fija:** Modelado de la Curva de Rendimientos (Yield Curve) mediante el algoritmo de **Nelson-Siegel**, con visualización dinámica de datos de mercado (FRED API) vs. curva teórica.
- **Superficies de Volatilidad (Black-Scholes):** Renderizado en 3D interactivo de superficies de precios de opciones, permitiendo visualizar la relación entre el precio del subyacente, el tiempo a vencimiento y el valor de la prima.
- **IA Predictiva (Machine Learning):** Módulo de predicción de precios basado en modelos XGBoost/Random Forest, con selector dinámico de activos del portafolio y mecanismo de interrupción (*AbortController*) para procesos largos.
- **Optimización Interactiva:** Frontera Eficiente con mapa de calor por Ratio de Sharpe y diseño **"Verde Ferxxo"** para portafolios de mínima varianza.
- **Análisis de Volatilidad MLE:** Modelos ARCH, GARCH y EGARCH con tablas de diagnóstico y pronósticos de varianza.

### ⚙️ Motor Matemático (Python Core)
- **Curvas de Rendimiento:** Implementación de Nelson-Siegel para el análisis de tasas de interés y spreads crediticios.
- **Valuación de Derivados:** Implementación analítica de Black-Scholes para opciones Europeas (Calls/Puts) y generación de mallas de datos para superficies 3D.
- **Value at Risk (VaR):** Cálculo Paramétrico, Histórico y Monte Carlo (10k sims) con Test de Backtesting de Kupiec.

---

## 🏗️ Arquitectura del Proyecto

```
RISK METER DASHBOARD/
├── backend/                    # Servidor API & Frontend SPA
│   ├── app/
│   │   ├── main.py            # Orquestación de Endpoints
│   │   ├── services/          # Lógica de negocio (Renta Fija, Derivados, ML)
│   │   └── static/            # Frontend (index.html con tema Verde Ferxxo)
│   └── requirements.txt        # Dependencias (FastAPI, SQLAlchemy, Arch)
├── data/                       # Almacenamiento local (SQLite, Modelos Serializados)
├── src/                        # Módulos matemáticos independientes
│   ├── garch_models.py        # Modelizado de volatilidad
│   ├── fixed_income.py        # Algoritmo Nelson-Siegel
│   └── markowitz.py           # Optimización de carteras
├── iniciar_dashboard.bat       # Script de arranque rápido (Windows)
└── README.md                   # Esta guía
```

---

## 📦 Instalación y Uso

### 1. Prerrequisitos
- **Local:** Python 3.11+ (Recomendado 3.13) y acceso a terminal.
- **API Key:** FRED API Key (Obtenla gratis en [fred.stlouisfed.org](https://fred.stlouisfed.org/))

### 2. Configuración (.env)
1. Clona el repositorio.
2. Asegúrate de tener un archivo `.env` en la raíz o en `backend/` con tu clave:
   ```env
   FRED_API_KEY=tu_clave_real_aqui
   ```

---

## 🚀 Ejecución en Windows (Recomendado)

El proyecto incluye un script automatizado que gestiona el entorno virtual y lanza el servidor:

1. Haz doble clic en `iniciar_dashboard.bat`.
2. El dashboard se abrirá automáticamente en: [http://localhost:8000](http://localhost:8000)

---

## 🐳 Ejecución con Docker (Alternativa Multiplataforma)

El proyecto incluye soporte completo para **Docker** y **Docker Compose**, lo que facilita su ejecución en Windows, macOS o Linux sin necesidad de configurar entornos de Python locales ni compilar extensiones manuales.

### 1. Prerrequisitos
* Tener instalado y ejecutándose **Docker Desktop** (o Docker Engine).

### 2. Instrucciones para Ejecutar
1. Asegúrate de tener configurada tu clave en el archivo `.env` en la raíz o en `backend/`:
   ```env
   FRED_API_KEY=tu_clave_real_aqui
   ```
2. Abre una terminal en la raíz del proyecto (donde está el archivo `docker-compose.yml`) y ejecuta:
   ```bash
   docker-compose up -d --build
   ```
   *Nota: La primera vez tomará unos minutos compilando las dependencias matemáticas (como `arch` para GARCH).*
3. Abre tu navegador e ingresa a:
   * **Dashboard y API:** [http://localhost:8000](http://localhost:8000)
   * **Swagger UI (Docs interactiva):** [http://localhost:8000/docs](http://localhost:8000/docs)

### 3. Comandos Útiles
* **Ver logs en tiempo real:**
  ```bash
  docker-compose logs -f
  ```
* **Detener y limpiar contenedores:**
  ```bash
  docker-compose down
  ```

---

## 📄 Licencia
Este proyecto está bajo la licencia **MIT**. Eres libre de usarlo y modificarlo con la debida atribución.

⭐ **Si este proyecto te ha sido útil, ¡considera darle una estrella!**

# Consultoria
