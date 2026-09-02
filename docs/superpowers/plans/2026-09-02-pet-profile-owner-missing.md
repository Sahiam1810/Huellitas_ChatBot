# Pet Profile Owner Missing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Explicar de forma segura cuando una cuenta vinculada todavía no tiene perfil de cliente.

**Architecture:** El adaptador .NET conserva la traducción HTTP y emite un error específico solamente para `list_owned`. El grafo del módulo transforma ese error en una respuesta de negocio sin crear datos ni acoplarse a Oracle.

**Tech Stack:** Python 3.12, FastAPI, httpx, LangGraph, pytest.

## Global Constraints

- El backend .NET conserva la propiedad de clientes y mascotas.
- No registrar ni devolver JWT, payloads o datos personales.
- Ejecutar únicamente pruebas dirigidas.

---

### Task 1: Contrato y respuesta de perfil propietario ausente

**Files:**
- Modify: `src/app/ports/pet_profile_gateway.py`
- Modify: `src/app/adapters/dotnet/pet_profile.py`
- Modify: `src/app/modules/pet_profile/graph.py`
- Test: `tests/unit/adapters/dotnet/test_pet_profile_gateway.py`
- Test: `tests/unit/modules/pet_profile/test_pet_profile_module.py`

**Interfaces:**
- Consumes: `DotNetPetProfileGateway.list_owned(bearer_token: str)`.
- Produces: `PetProfileOwnerProfileNotFoundError` y una respuesta `ModuleResult` explicativa.

- [ ] **Step 1: Escribir pruebas fallidas**

```python
with pytest.raises(PetProfileOwnerProfileNotFoundError):
    await gateway.list_owned("jwt-secret")

assert "perfil de cliente" in result.message.casefold()
```

- [ ] **Step 2: Confirmar el fallo**

Run: `uv run pytest tests/unit/adapters/dotnet/test_pet_profile_gateway.py tests/unit/modules/pet_profile/test_pet_profile_module.py -q`

Expected: FAIL porque el error específico y su respuesta todavía no existen.

- [ ] **Step 3: Implementar el cambio mínimo**

```python
class PetProfileOwnerProfileNotFoundError(PetProfileGatewayError):
    pass
```

`list_owned` debe convertir únicamente su `PetProfileNotFoundError` en el nuevo error. El grafo debe capturarlo antes de `PetProfileGatewayError` y devolver una explicación sobre completar el perfil de cliente.

- [ ] **Step 4: Verificar pruebas y contenedor**

Run: `uv run pytest tests/unit/adapters/dotnet/test_pet_profile_gateway.py tests/unit/modules/pet_profile/test_pet_profile_module.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/app/ports/pet_profile_gateway.py src/app/adapters/dotnet/pet_profile.py src/app/modules/pet_profile/graph.py tests/unit/adapters/dotnet/test_pet_profile_gateway.py tests/unit/modules/pet_profile/test_pet_profile_module.py docs
git commit -m "fix(pet-profile): 🐛 explain missing client profiles"
```
