# Design

Add one shared character-reference collector at the story boundary. Collect typed IDs in stable order from source_basis.character_ids, start_state.characters, event_sequence participants/character_ids, and end_state.characters. State character lists accept existing string IDs and records with character_id. Keep lifecycle prose untouched. The direct character_ids field is a derived index, never an independent identity source.

Bind the index during scene binding, including every regeneration and field patch, and inject story_metadata.scene_character_binding_contract. The existing story validator enforces the index and registry under the new contract. Missing keys in older cached model responses can be deterministically reconstructed from explicit references; malformed reference data is rejected. Schemas/prompts and workflow documentation agree on this boundary.
