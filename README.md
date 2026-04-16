# Post-OCR Invoice Resolution Service — README del repositorio

## Descripción general

Este repositorio contiene el material necesario para realizar una prueba técnica orientada a evaluar tres capacidades principales:

- diseño de **APIs backend**
- manejo, normalización y persistencia de **datos post-OCR**
- integración de un **agente basado en LLM** que use contexto histórico y datos de referencia para resolver campos de negocio simplificados

La prueba está pensada para simular un flujo realista donde una etapa previa de OCR/parsing ya ha extraído información de facturas y el sistema candidato debe trabajar **a partir de esos datos ya estructurados**.

## Objetivo de la prueba

El objetivo es construir un servicio que:

1. reciba payloads post-OCR de nuevas facturas
2. los valide y normalice
3. los almacene en una capa operacional
4. utilice un componente basado en LLM para resolver campos de negocio simplificados
5. exponga los resultados por API
6. exporte los registros resueltos de forma incremental a una segunda capa analítica

El detalle completo del ejercicio se encuentra en el PDF incluido en la raíz del proyecto.

## Estructura esperada del repositorio

Este repositorio está organizado alrededor de dos elementos principales:

### 1. Enunciado en la raíz

En la raíz del proyecto se encuentra el documento PDF con el enunciado completo de la prueba:

- `post_ocr_invoice_resolution_service.pdf`

Ese documento describe:

- el problema a resolver
- los requisitos funcionales
- los entregables esperados
- los bonus opcionales
- los criterios de evaluación

## 2. Carpeta `data/`

En la carpeta `data/` se incluye la semilla de datos necesaria para desarrollar y validar la prueba.

Dentro de esa carpeta se encuentra:

- un README específico explicando el propósito de cada fichero
- los datos sintéticos de entrada
- el histórico resuelto
- los datos de referencia
- un fichero interno con resoluciones esperadas para evaluación

### Contenido de `data/`

Los ficheros incluidos son:

- `README.md`
- `new_post_ocr_inputs.json`
- `new_post_ocr_inputs.csv`
- `historical_resolutions.json`
- `historical_resolutions.csv`
- `reference_data.json`

### Qué uso tiene cada grupo de datos

#### `new_post_ocr_inputs.*`
Contienen las nuevas entradas que el sistema debe recibir y procesar.

Representan la salida de OCR/parsing de facturas nuevas aún no resueltas.

#### `historical_resolutions.*`
Contienen el histórico de resoluciones previas.

Este fichero actúa como memoria operativa del sistema y puede ser utilizado por el agente o por herramientas internas para:

- relacionar proveedores similares
- detectar patrones previos
- sugerir categorías
- sugerir business units
- ayudar a decidir si un caso debe autoaprobarse o pasar a revisión

#### `reference_data.json`
Contiene datos de referencia para facilitar la resolución. Por ejemplo:

- proveedores canónicos conocidos
- categorías válidas
- business units válidas
- reglas simples de revisión

## Qué se espera que construya el candidato

A partir del material de este repositorio, se espera que el candidato implemente una solución capaz de:

- ingerir nuevas facturas post-OCR
- normalizar datos relevantes
- persistir input, estado y resultado
- usar un LLM para inferir:
  - `canonical_supplier`
  - `predicted_spend_category`
  - `predicted_business_unit` o `predicted_cost_center`
  - `review_decision`
  - `confidence`
  - `decision_explanation`
- consultar al menos una herramienta interna basada en histórico o referencia
- exponer la información por API
- exportar resultados a una capa analítica

## Alcance del agente

El uso del LLM debe centrarse en **resolver incertidumbre de negocio**, no en tareas puramente deterministas.

Ejemplos de tareas adecuadas para el agente:

- unificación de variantes de proveedor
- clasificación de gasto en una categoría cerrada
- inferencia de business unit
- decisión de `auto_approve` frente a `needs_review`
- explicación breve de la decisión

Ejemplos de tareas que deberían resolverse fuera del agente:

- parsing de fechas
- limpieza de nulos
- conversión de strings a números
- validaciones aritméticas básicas
- validación de esquema

## Recomendación sobre uso de APIs de modelos

Para implementar la parte agentic, se recomienda usar una API de modelos que disponga de una modalidad gratuita, free tier o créditos iniciales.

Opciones razonables pueden ser:

- **Google AI Studio / Gemini API**, que suele ofrecer una forma sencilla de probar modelos con cuota gratuita o limitada
- algún **proveedor cloud con créditos gratuitos iniciales**
- cualquier otra API de LLM equivalente, siempre que quede bien documentado en el README del candidato

Lo importante no es el proveedor concreto, sino que la solución:

- sea reproducible
- esté bien documentada
- use el modelo con sentido
- deje claro cómo configurar las credenciales o variables de entorno

Si el candidato no quiere depender de un proveedor externo, también puede plantear una implementación desacoplada que permita cambiar fácilmente de proveedor o mockear el componente LLM. Lo más importante es como se organiza el código, si no se consigue la utilización de ningún LLM gratuito no es lo más importante, se valorará mucho más como resuelve el código y como se organiza.

## Recomendación de entrega al candidato

Si esta prueba se entrega a una persona candidata, lo más recomendable es compartir:

- el PDF del enunciado en la raíz
- la carpeta `data/` con:
  - `README.md`
  - `new_post_ocr_inputs.json`
  - `historical_resolutions.json`
  - `reference_data.json`


## Nota final

La intención de este repositorio no es evaluar OCR, visión por computador ni conocimiento profundo de contabilidad, sino la capacidad de construir una solución clara y razonable donde confluyan:

- backend
- datos
- APIs
- integración con LLMs
- uso de contexto histórico y herramientas internas

