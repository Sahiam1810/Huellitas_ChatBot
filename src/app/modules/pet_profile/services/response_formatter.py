from app.ports.pet_profile_gateway import PetProfile


def format_pet_list(profiles: tuple[PetProfile, ...]) -> str:
    if not profiles:
        return (
            "Tu cuenta está vinculada correctamente, pero no encontré mascotas "
            "asociadas a ella. Registra una mascota en Huellitas o solicita ayuda "
            "a la veterinaria."
        )
    rows = [
        f"- {pet.name}: {pet.species_name}, {pet.race_name}, {pet.age} años, {pet.weight:g} kg"
        for pet in profiles
    ]
    return "Estas son tus mascotas:\n" + "\n".join(rows)


def format_pet_detail(pet: PetProfile) -> str:
    gender = "hembra" if pet.gender.casefold() == "f" else "macho"
    observations = pet.observations or "Sin observaciones"
    return (
        f"{pet.name}: {pet.species_name}, raza {pet.race_name}, {pet.age} años, "
        f"{gender}, {pet.weight:g} kg. Observaciones: {observations}."
    )
