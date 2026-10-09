# Design

Add a source-driven cut planner used for scenes with authored event sequences.
Each visible beat supplies one cut by default. Optional `cut_transitions` supply
ordered, named subdivisions with explicit first-frame and motion fields. Keep
the research IDs alongside the beat and transition IDs through the final cut
contract. The historical legacy path remains for artifacts without authored
beats. No reviewer or provider calls are added.
