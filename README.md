# Huellitas ChatBot — Servicio de automatización veterinaria

Monolito modular de automatización conversacional para una plataforma veterinaria.

El repositorio se encuentra en la fase de definición arquitectónica. Todavía no contiene implementación ejecutable del bot.

## Límites principales

- El backend .NET controla los canales, las reglas de negocio y la persistencia en Oracle Database 26ai.
- .NET conserva el historial canónico y el estado de escalamiento de cada conversación.
- El servicio Python coordinará conversación, módulos, modelos y RAG.
- Qdrant será la base vectorial del conocimiento autorizado.
- Redis se reservará para caché, idempotencia, bloqueos y checkpoints temporales.
- Python nunca accederá directamente a Oracle Database 26ai.

## Documentación

- [Arquitectura maestra](docs/Distribución%20de%20la%20arquitectura%20del%20servicio%20de%20automatización.md)
- [Diseño arquitectónico aprobado](docs/plans/2026-08-25-veterinary-chatbot-architecture-design.md)
- [Plan del scaffold arquitectónico](docs/superpowers/plans/2026-08-25-veterinary-chatbot-architecture-scaffold.md)
