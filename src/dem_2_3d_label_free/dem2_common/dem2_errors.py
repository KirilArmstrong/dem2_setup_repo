"""Dem2 errors."""


class Dem2Errors:
    """Collection of all Dem2 errors."""

    def __init__(self) -> None:
        """Do not use. This class is only used as a namespace and cannot be instantiated."""
        raise Exception("This class is only used as a namespace and cannot be instantiated.")

    class GenericError(Exception):
        """Generic/All USB3-DAq board error."""

    class StageError(GenericError):
        """Stage failure."""

        def __init__(self, reason: str) -> None:
            """Create a new Mirror error.

            :param reason: An optional reason for the mirror failure, if known.
            """
            super().__init__(f"Stage failure: {reason}")

    class PropertyNotSetError(GenericError):
        """Stage failure."""

        def __init__(self, reason: str) -> None:
            """Create a new Mirror error.

            :param reason: An optional reason for the mirror failure, if known.
            """
            super().__init__(f"Property was never set: {reason}")

    class LaserError(GenericError):
        """Stage failure."""

        def __init__(self, reason: str) -> None:
            """Create a new Mirror error.

            :param reason: An optional reason for the mirror failure, if known.
            """
            super().__init__(f"Laser failure: {reason}")

    class CameraError(GenericError):
        """Stage failure."""

        def __init__(self, reason: str) -> None:
            """Create a new Mirror error.

            :param reason: An optional reason for the mirror failure, if known.
            """
            super().__init__(f"Camera failure: {reason}")

    class ControllerError(GenericError):
        """Stage failure."""

        def __init__(self, reason: str) -> None:
            """Create a new Mirror error.

            :param reason: An optional reason for the mirror failure, if known.
            """
            super().__init__(f"Controller failure: {reason}")
