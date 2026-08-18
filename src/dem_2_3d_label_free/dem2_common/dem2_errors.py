"""Dem2 errors."""

from src.dem_2_3d_label_free.dem2_common.dem2_laser_defs import LS_ERROR_CODES


class Dem2Errors:
    """Collection of all Dem2 errors."""

    def __init__(self) -> None:
        """Do not use. This class is only used as a namespace and cannot be instantiated."""
        raise Exception(
            "This class is only used as a namespace and cannot be instantiated."
        )

    class GenericError(Exception):
        """Generic/All USB3-DAq board error."""

    class StageError(GenericError):
        """Stage error."""

        def __init__(self, reason: str) -> None:
            """Create a new Stage error.

            :param reason: An optional reason for the stage error, if known.
            """
            super().__init__(f"Stage error: {reason}")

    class BScanPatternError(GenericError):
        """Stage error."""

        def __init__(self, reason: str) -> None:
            """Create a new B Scan Pattern error.

            :param reason: An optional reason for the b scan pattern error, if known.
            """
            super().__init__(f"B Scan pattern error: {reason}")

    class PropertyNotSetError(GenericError):
        """Stage error."""

        def __init__(self, reason: str) -> None:
            """Create a new PropertyNotSet error.

            :param reason: An optional reason for the property error, if known.
            """
            super().__init__(f"Property was never set: {reason}")

    class LaserError(GenericError):
        """Stage error."""

        def __init__(
            self, code: int | None = None, reason: str | int | None = ""
        ) -> None:
            """Create a new Laser error.

            :param code: Error code. None
            :param reason: An optional reason (or error code) for the laser error, if known.
            """
            err = "" if code is None else LS_ERROR_CODES[code]
            err += (
                ""
                if reason is None
                else (
                    (": " + reason)
                    if isinstance(reason, str)
                    else (": " + LS_ERROR_CODES[reason])
                )
            )
            super().__init__(f"Laser error: {err}")

    class CameraError(GenericError):
        """Stage error."""

        def __init__(self, reason: str) -> None:
            """Create a new Camera error.

            :param reason: An optional reason for the camera error, if known.
            """
            super().__init__(f"Camera error: {reason}")

    class ControllerError(GenericError):
        """Stage error."""

        def __init__(self, reason: str) -> None:
            """Create a new Controller error.

            :param reason: An optional reason for the controller error, if known.
            """
            super().__init__(f"Controller error: {reason}")
