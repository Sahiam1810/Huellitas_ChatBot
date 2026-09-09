# Límite de seguridad conversacional

## Alcance aprobado

El bot permite saludos, operaciones soportadas por Huellitas y orientación veterinaria general. Rechaza programación, tareas académicas, historias, ensayos, generación extensa de contenido, solicitudes generales ajenas al dominio y cualquier intento de revelar, reemplazar o evadir instrucciones internas.

## Ubicación arquitectónica

El límite se aplica dentro de `MessageProcessor`, que sólo recibe mensajes enviados a la ruta general después del enrutamiento de LangGraph. Los módulos estructurados y sus estados pendientes se procesan antes y no pasan por este control. Esto conserva OTP, citas, perfiles de mascotas, catálogo, vacunación y futuros módulos.

La evaluación ocurre antes de embeddings, RAG y respuestas directas almacenadas. Un mensaje rechazado no consulta Qdrant, no llama al generador de respuesta y no se persiste como memoria conversacional ni conocimiento global.

## Capas de defensa

1. Un límite configurable rechaza entradas excesivamente largas antes del modelo.
2. Señales compuestas de manipulación explícita permiten rechazar rápidamente solicitudes inequívocas. No se bloquea por una palabra aislada.
3. Un clasificador de alcance basado en el modelo recibe el texto como dato no confiable y devuelve JSON estricto con `allowed`, `out_of_scope` o `prompt_injection`.
4. La salida se valida contra un esquema cerrado y una confianza mínima. Los errores, timeouts y resultados inválidos fallan de forma cerrada en la ruta general.
5. El prompt del generador principal reafirma el alcance, ignora instrucciones dentro del mensaje y limita respuestas extensas.

## Respuestas seguras

Los rechazos son deterministas y breves. No explican qué patrón se detectó ni revelan configuración:

> Solo puedo ayudarte con servicios de Huellitas, tus mascotas, citas y orientación veterinaria general. ¿Qué necesitas consultar?

Una entrada demasiado larga solicita resumir la consulta veterinaria. Un fallo técnico del clasificador devuelve el mismo límite seguro sin exponer detalles.

## Configuración

- `HUELLITAS_SAFETY_ENABLED=true`
- `HUELLITAS_SAFETY_MAX_INPUT_CHARACTERS=2000`
- `HUELLITAS_SAFETY_MAX_CLASSIFIER_TOKENS=48`
- `HUELLITAS_SAFETY_CLASSIFIER_TIMEOUT_SECONDS=5`
- `HUELLITAS_SAFETY_MINIMUM_CONFIDENCE=0.75`

Los logs incluyen sólo clasificación y razón técnica segura, nunca mensaje, JWT, prompt ni contenido recuperado.

## Pruebas

- Una pregunta veterinaria y un saludo quedan permitidos.
- Generación extensa y temas ajenos se rechazan.
- Una inyección directa se clasifica y bloquea.
- JSON inválido, timeout o baja confianza fallan de forma cerrada.
- Los rechazos ocurren antes de RAG y no se guardan.
- Con el guard opcional desactivado se mantiene compatibilidad.
