import time

from tamagotchi import art, pet as pet_logic, storage


def main():
    now = time.time()
    # Merging over new_pet fills in any field an older save file doesn't have.
    pet = {**pet_logic.new_pet(now), **(storage.load() or {})}
    pet_logic.decay(pet, now)
    storage.save(pet)
    print(art.render(pet, pet_logic.feeling(pet, now)))
