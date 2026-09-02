# Diseño del módulo de catálogo de servicios

## Objetivo

Implementar `services_catalog` como el segundo módulo veterinario ejecutable del
monolito modular. El módulo responderá consultas públicas de sólo lectura sobre
servicios activos, categorías, precios y duración usando al backend .NET como
fuente oficial, y podrá complementar la respuesta con contenido descriptivo
autorizado recuperado desde Qdrant.

Sedes y horarios quedan fuera de este incremento porque el backend todavía no
expone un contrato que sea fuente oficial de esos datos.

## Decisiones

- La integración será híbrida y determinista.
- .NET será la única fuente de nombre, categoría, precio, duración y estado.
- Qdrant sólo aportará descripciones autorizadas de documentos etiquetados para
  `services_catalog`.
- El módulo no utilizará al LLM para seleccionar, alterar o completar datos
  dinámicos.
- El catálogo estará disponible para identidades vinculadas y para el rol
  interno `TelegramGuest` porque no contiene información personal.
- El acceso invitado se declarará como capacidad del manifiesto; no se agregarán
  excepciones específicas de servicios al grafo principal.
- El módulo será de sólo lectura y no tendrá confirmaciones ni mutaciones.

## Arquitectura

```text
Mensaje autenticado
        |
Router determinista
        |
ServicesCatalogModuleExecutor
   |                         |
ServicesCatalogGateway       ServiceKnowledgeGateway
   |                         |
HTTP + JWT                   embeddings + Qdrant
   |                         |
.NET /api/services/available documentos con tag services_catalog
        \                   /
          ModuleResult uniforme
```

Los contratos del módulo y sus puertos permanecerán neutrales. El subgrafo no
importará FastAPI, `httpx`, SDKs de embeddings, Qdrant ni adaptadores. Los
clientes concretos se construirán exclusivamente desde `bootstrap`.

## Contrato del backend .NET

Se agregará `GET /api/services/available` sin alterar los endpoints
administrativos actuales. El endpoint:

- exigirá un JWT válido mediante la política autenticada general;
- aceptará identidades reales y la identidad interna firmada `TelegramGuest`;
- devolverá únicamente servicios activos;
- incluirá `id`, `typeServiceId`, `typeServiceName`, `name`, `durationMinutes` y
  `price`;
- no expondrá capacidades de creación, actualización o eliminación;
- conservará Domain, Application, Infrastructure y API como capas separadas.

El filtrado de activos ocurrirá en .NET. El agente no recibirá registros
inactivos para descartarlos posteriormente.

## Manifiesto y acceso invitado

`ModuleManifest` incorporará la propiedad inmutable
`guest_accessible: bool = False`. El valor predeterminado preservará la
protección de todos los módulos existentes y futuros. El manifiesto de
`services_catalog` declarará `guest_accessible=True`.

Después del routing, el grafo permitirá la ejecución de un módulo para
`TelegramGuest` únicamente cuando el manifiesto seleccionado lo autorice. En
cualquier otro caso conservará el fallback `guest_link_required`. Una
conversación escalada continuará terminando antes del routing y de cualquier
consulta externa.

## Intenciones y routing

El módulo declarará tres intenciones:

- `services.list`: listar los servicios activos disponibles;
- `services.search`: buscar servicios por nombre o categoría;
- `services.detail`: consultar datos concretos como precio o duración.

Las frases y reglas pertenecerán a `services_catalog/routing.py`. El router
determinista recibirá las reglas de todos los módulos habilitados desde la raíz
de composición, sin incluir reglas veterinarias dentro de `main_graph.py`.

Ante una frase ambigua, la coincidencia más específica tendrá prioridad. Si no
existe una regla suficiente, se mantiene el fallback general existente.

## Ejecución y formato de respuesta

El ejecutor consultará primero el catálogo oficial:

1. Para `services.list`, devolverá una lista breve de nombre, categoría, precio
   y duración.
2. Para `services.search`, normalizará la consulta y filtrará de forma
   determinista por nombre o categoría.
3. Para `services.detail`, resolverá el servicio mencionado. Si existe una sola
   coincidencia, presentará sus datos oficiales; si existen varias, solicitará
   al usuario escoger una.
4. Para una coincidencia concreta, el puerto de conocimiento podrá buscar una
   descripción usando la pregunta y el nombre oficial del servicio.

Los precios se formatearán como COP sin reinterpretarlos. Las duraciones se
expresarán en minutos. El contenido descriptivo tendrá un límite estricto de
longitud y nunca reemplazará campos de .NET.

## RAG específico del módulo

`ServiceKnowledgeGateway` ocultará embeddings y almacenamiento vectorial. Su
adaptador consultará conocimiento global activo con la etiqueta exacta
`services_catalog`, un límite pequeño de coincidencias y el umbral configurado.

- Coincidencias válidas: se agrega descripción autorizada y se reporta RAG
  `used`.
- Sin coincidencias: se responde sólo con .NET y se reporta RAG `empty`.
- Embeddings o Qdrant indisponibles: se responde sólo con .NET y se reporta RAG
  `degraded`.
- RAG deshabilitado: se responde sólo con .NET y se reporta RAG `disabled`.

El JWT, el mensaje completo y los datos dinámicos de .NET no se almacenarán en
Qdrant por ejecutar este módulo.

## Errores y fallbacks

- `401`: respuesta segura indicando que no fue posible validar la sesión.
- `403`: respuesta segura de acceso no autorizado sin filtrar detalles del
  backend.
- Respuesta inválida de .NET: fallback técnico del módulo.
- Timeout, red o error 5xx de .NET: informar indisponibilidad temporal sin
  inventar servicios ni precios.
- Cero servicios activos: informar que no hay servicios publicados.
- Cero coincidencias de búsqueda: indicar que no aparece un servicio activo con
  ese nombre o categoría.
- Fallo de RAG: degradar únicamente la descripción; conservar los datos
  oficiales recuperados.

Los logs no incluirán JWT, mensaje del usuario, respuesta completa, IDs de
usuario ni contenido recuperado.

## Composición y ciclo de vida

Cuando `HUELLITAS_BACKEND_ENABLED=true`, `bootstrap` construirá un único
`DotNetServicesCatalogGateway` y registrará el módulo. El adaptador de
conocimiento se construirá sólo cuando RAG, embeddings y almacenamiento global
estén disponibles. Su ausencia no impedirá registrar el catálogo.

Los clientes compartidos respetarán el cierre ordenado existente. Los módulos
no crearán ni cerrarán conexiones concretas.

## Pruebas dirigidas

Se usarán pruebas acotadas mediante TDD:

- validación del manifiesto y acceso invitado cerrado por defecto;
- routing de listado, búsqueda y detalle;
- invitado autorizado para `services_catalog` y rechazado para `pet_profile`;
- conversación escalada sin llamadas al módulo, .NET, embeddings o Qdrant;
- parsing estricto del contrato .NET;
- filtrado server-side de servicios activos;
- listado, coincidencia única, múltiples coincidencias y ninguna coincidencia;
- precio y duración conservados desde .NET;
- RAG utilizado, vacío, deshabilitado y degradado;
- errores 401, 403, timeout, red, 5xx y JSON inválido;
- endpoint .NET autenticado y accesible por identidad `TelegramGuest`;
- no regresión dirigida de `pet_profile`.

No se ejecutarán llamadas reales facturables a modelos o embeddings durante las
pruebas automatizadas.

## Fuera de alcance

- Sedes, horarios o disponibilidad de citas.
- Creación, modificación o eliminación de servicios.
- Recomendaciones clínicas o selección médica personalizada.
- Agendamiento desde este módulo.
- Uso del LLM para alterar información oficial.
- Sincronización automática del catálogo hacia Qdrant.
- Caché distribuida del catálogo.
