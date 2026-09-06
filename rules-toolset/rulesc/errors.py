# errors.py - the two exceptions, in a module of their own.
#
# They live here rather than in compile.py so that profile.py and
# lookup.py can raise them without importing the compiler, which would
# import the profile back. Both names are re-exported from compile.py
# and from the package, so nothing that catches them has to change.


class RuleError(Exception):
    pass


class IncludeCycleError(RuleError):
    """Raised when the include graph contains a loop. Carries the full
    path so the message shows exactly which chain closed on itself,
    rather than just naming one document."""

    def __init__(self, cycle_path):
        self.cycle_path = cycle_path
        chain = " -> ".join(cycle_path)
        super().__init__(
            f"include cycle detected: {chain}\n"
            f"  '{cycle_path[-1]}' is already being included further up this chain, "
            "so expanding it would never terminate."
        )
