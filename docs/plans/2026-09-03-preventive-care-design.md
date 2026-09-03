# Diseño: módulo `preventive_care`

Fecha: 2026-09-03  
Estado: aprobado  
Rama: `feature/preventive-care`  
Alcance: consulta de vacunas oficiales + orientación preventiva con RAG

## Objetivo

Permitir que un cliente vinculado consulte el historial de vacunas de sus mascotas desde .NET y reciba orientación preventiva (desparasitación, nutrición, calendarios generales) basada en contenido autorizado en Qdrant. Sin diagnóstico, sin prescripción, sin mutaciones.

## Decisiones

### Enfoque B: historial .NET + RAG preventivo

- **.NET:** `GET /api/vaccinations` filtrado por dueño; mascotas vía `GET /api/pets/mine` para cruzar nombres.
- **RAG:** tag `preventive_care` en `knowledge_global`, hasta 3 extractos.
- **Sin LLM clínico:** plantillas fijas en español.
- **`guest_accessible=False`:** requiere cuenta vinculada con JWT Cliente.

### Intenciones

| Intención | Uso |
|---|---|
| `preventive.vaccines` | Historial de vacunas por mascota |
| `preventive.vaccines.upcoming` | Próximas dosis registradas |
| `preventive.ask` | Desparasitación, nutrición, cuidados generales (RAG + contexto de mascota si se identifica) |

### Componentes

- `ports/vaccinations_gateway.py` + `adapters/dotnet/vaccinations.py`
- `ports/preventive_knowledge_gateway.py` + `adapters/knowledge/preventive_knowledge.py`
- `modules/preventive_care/` — dominio, nodos, graph, manifest, routing

### Fuera de alcance

- Registrar o editar vacunas desde el chat.
- Invitados (`TelegramGuest`).
- `human_handoff` (último módulo pendiente).
