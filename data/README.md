# Semilla de datos — Post-OCR Invoice Resolution Service

Este directorio contiene una **semilla sintética** pensada para ejecutar la prueba técnica descrita en el enunciado del servicio **Post-OCR Invoice Resolution Service**.

La semilla está diseñada para que el candidato pueda construir una solución completa sin tener que inventar los datos de partida. El objetivo no es evaluar OCR, sino evaluar cómo el sistema:

- ingesta payloads post-OCR,
- normaliza datos,
- consulta histórico y datos de referencia,
- utiliza un agente basado en LLM para resolver campos de negocio simplificados,
- expone resultados por API,
- y exporta resoluciones a una segunda capa analítica.

---

## Qué contiene este paquete

La semilla se divide en **cuatro ficheros principales** y dos exportaciones auxiliares en CSV.

### 1. `new_post_ocr_inputs.json`
Es el fichero principal de **entrada** para la prueba.

Contiene facturas nuevas, todavía **sin resolver**, en un formato que simula la salida de un sistema OCR/parsing documental.

Estos registros son los que la solución del candidato debería:

1. recibir por API o por un mecanismo equivalente,
2. validar,
3. normalizar,
4. persistir,
5. enviar al componente agentic para su resolución.

#### Qué representa cada registro
Cada objeto representa una factura nueva con información ya extraída del documento, por ejemplo:

- `document_id`: identificador técnico del documento
- `supplier_name`: nombre detectado del proveedor
- `supplier_tax_id`: tax ID detectado, si existe
- `invoice_number`: número de factura
- `invoice_date`: fecha extraída
- `currency`: moneda detectada
- `base_amount`, `tax_amount`, `total_amount`: importes extraídos
- `description`: descripción o concepto detectado
- `country`: país asociado al documento o proveedor
- `raw_ocr_text`: texto OCR bruto opcional
- `field_confidence`: confianza de extracción por campo

#### Qué tipo de casos incluye
Este fichero incluye casos deliberadamente variados para que el agente tenga que usar contexto:

- proveedores conocidos con variantes de nombre
- proveedores con errores típicos de OCR
- proveedores nuevos no vistos antes
- casos claros de clasificación
- casos ambiguos que deberían acabar en revisión manual
- tax IDs ausentes o inconsistentes
- descripciones demasiado genéricas
- niveles bajos de confianza en algunos campos clave

#### Para qué sirve en la prueba
Sirve para evaluar si la solución sabe trabajar sobre entradas **post-OCR reales o plausibles**, en vez de asumir datos perfectos.

---

### 2. `historical_resolutions.json`
Es el fichero de **histórico resuelto**.

Contiene facturas ya procesadas previamente y actúa como la **memoria operativa** del sistema. Es la principal fuente de contexto para que el agente pueda tomar decisiones razonadas.

#### Qué representa cada registro
Cada objeto representa una factura histórica con resolución ya conocida. Puede incluir campos como:

- `supplier_name_raw`: nombre original del proveedor tal y como llegó
- `supplier_tax_id`: tax ID observado en ese caso
- `canonical_supplier`: proveedor canónico resuelto
- `predicted_spend_category`: categoría asociada
- `predicted_business_unit`: business unit o área sugerida
- `review_decision`: si se aprobó automáticamente o requirió revisión
- `confidence`: confianza asignada en esa resolución
- `resolved_at`: fecha en la que se resolvió

#### Para qué sirve en la prueba
Este fichero está pensado para que el candidato pueda implementarlo como una herramienta interna del sistema, por ejemplo para:

- buscar facturas históricas del mismo proveedor,
- resolver variantes de nombres,
- recuperar patrones por proveedor,
- sugerir categorías frecuentes,
- sugerir business units frecuentes,
- detectar incoherencias respecto al comportamiento histórico.

#### Qué patrones contiene
El histórico ha sido construido para que haya relaciones aprovechables. Por ejemplo:

- varios aliases del mismo proveedor canónico,
- proveedores con una categoría muy estable,
- proveedores con una business unit dominante,
- algunos casos con más ambigüedad,
- diferentes países,
- ejemplos que pueden motivar `needs_review`.

En otras palabras: **no es una tabla de respuestas directas**, sino un contexto útil para apoyar inferencias.

---

### 3. `reference_data.json`
Es el fichero de **datos de referencia**.

Contiene información cerrada o semi-estructurada para ayudar al sistema a resolver las facturas nuevas sin requerir conocimiento previo de contabilidad.

#### Qué incluye
Puede incluir, según la versión del dataset:

- lista de `spend_categories` válidas,
- lista de `business_units` válidas,
- lista de proveedores canónicos conocidos,
- aliases de proveedor,
- reglas simples de revisión,
- reglas básicas por país,
- pistas o restricciones que ayuden a resolver mejor los casos.

#### Para qué sirve en la prueba
Este fichero permite implementar herramientas internas como:

- validación de etiquetas permitidas,
- matching de proveedores conocidos,
- apoyo a la clasificación,
- reglas simples para decidir `auto_approve` vs `needs_review`.

También ayuda a que el problema quede **cerrado y evaluable**, sin depender de conocimiento de negocio externo.

---

## Ficheros CSV

Además de los JSON, se incluyen exportaciones auxiliares en CSV:

- `new_post_ocr_inputs.csv`
- `historical_resolutions.csv`

Su objetivo es facilitar:

- inspección manual rápida,
- carga en hojas de cálculo,
- uso por candidatos que prefieran CSV,
- pruebas adicionales de importación.

La fuente principal del dataset sigue siendo el formato JSON.

---

## Qué se espera que relacione el agente

La semilla ha sido diseñada para que el agente pueda encontrar relaciones útiles entre nuevos documentos e histórico. Por ejemplo:

- variantes del mismo proveedor (`Orange Espana`, `Orange Espagne SA`, `ORANGE ES`)
- errores OCR realistas (`Micr0soft`, `StapIes`, `Ende5a`, `Google C1oud`)
- patrones repetidos de categoría por proveedor
- patrones repetidos de business unit por proveedor
- casos sin suficiente evidencia que deberían marcarse para revisión
- proveedores nuevos que no deben resolverse con falsa confianza

Esto permite evaluar si el sistema usa el contexto de forma razonable y si sabe manejar incertidumbre.

---

## Campos de negocio que esta semilla ayuda a inferir

La semilla está alineada con el enunciado y está pensada para ayudar a resolver, como mínimo:

- `canonical_supplier`
- `predicted_spend_category`
- `predicted_business_unit`
- `review_decision`
- `confidence`
- `decision_explanation`

No hace falta conocimiento contable para usar esta semilla. La tarea se ha simplificado para que el foco esté en:

- diseño del sistema,
- calidad de datos,
- uso de herramientas,
- integración con LLMs,
- y criterio técnico.
