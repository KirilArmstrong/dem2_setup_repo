"""Demonstrator 2 Stage b-scan pattern."""

import logging
import os
from contextlib import suppress

import yaml
from zeiss_helpers.common import expect_or_raise


class Dem2BScanPattern:
    """Demonstrator 2 Stage b-scan pattern class."""

    def __init__(self, dem2_bsp_filepath: str = ""):
        self.description: str = ""
        self._log = logging.getLogger(self.__class__.__name__)
        self.a_scans_b_scan = 0 # No of a-scans per b-scan
        self._a_scans: dict = {
            "focus_positions": [],
            "x_positions": [],
            "y_positions": [],
        }

        self.filepath = dem2_bsp_filepath

        if dem2_bsp_filepath:
            self.from_file(filepath=dem2_bsp_filepath)

    def __str__(self) -> str:
        """As string."""
        return f"Description: '{self.description}', no_of_a_scans={self.a_scans_b_scan}"

    # Functions

    def as_dict(self) -> dict:
        """Return as dictionary."""
        return {
            "description": self.description,
            "no_of_a_scans": self.a_scans_b_scan,
            "x_positions": self.x_positions,
            "y_positions": self.y_positions,
            "focus_positions": self.focus_positions,
        }

    def as_file(self, filename: str) -> None:
        self._log.info(
            "Saving Dem2BScanPattern '%s' to file '%s'...", self.description, filename
        )

        self.filepath = filename

        dict_to_save = self.as_dict()

        with open(self.filepath, "w", encoding="utf-8") as yml_file:
            yaml.safe_dump(dict_to_save, yml_file, default_style=False)

        self._log.info(
            "Saved Dem2BScanPattern '%s' to file '%s'.", self.description, filename
        )

    def from_dict(self, sp_dict: dict) -> None:
        """Read from dictionary.

        :param sp_dict: Source dict.
        """

        def read_values(value: str | list) -> list:
            """Read from separate file or directly as list."""
            # It's already a list of values
            if isinstance(value, list):
                return value

            _filedir = os.path.split(self.filepath)[0]
            _filename = os.path.join(_filedir, value)

            # Open and read the values from file
            with open(_filename, encoding="utf-8") as value_file:
                # todo what datatype does stage accept?
                values = [int(x) for x in value_file.readline().split(",")]
                self._log.info(
                    "Scan pattern 'values' loaded from file '%s'.", _filename
                )
                return values

        with suppress(KeyError):
            self.description = sp_dict["description"]
            self.a_scans_b_scan = sp_dict["no_of_a_scans"]

            self.x_positions = read_values(value=sp_dict["x_positions"])
            self.y_positions = read_values(value=sp_dict["y_positions"])
            self.focus_positions = read_values(value=sp_dict["focus_positions"])

    def from_file(self, filepath: str) -> None:
        """Load Dem2 b-scan pattern from file.

        :param filepath: Filename including the path
        """
        self._log.info("Load Dem2 b-scan pattern from file '%s'...", filepath)

        # Save filename
        self.filepath = filepath

        # Open and read file
        with open(filepath, encoding="utf-8") as yml_file:
            _dict = yaml.safe_load(yml_file)

        self.from_dict(sp_dict=_dict)

        self._log.info(
            "Dem2 b-scan pattern %s loaded from file '%s'.",
            f"'{self.description}'" if self.description else "",
            filepath,
        )

    # Properties

    @property
    def x_positions(self) -> list[int]:
        """X-Position list."""
        return self._a_scans["x_positions"]

    @x_positions.setter
    def x_positions(self, value: list[int]) -> None:
        """Set x-position list.

        Length of the list must match the number of samples! Empty lists are always ok.

        :param value: List of x-positions [len(value) == no_of_a_scans]
        :raises AssertionError: Out of range
        """
        # Set no of a-scans if not done yet
        if self.a_scans_b_scan == 0:
            self.a_scans_b_scan = len(value)

        expect_or_raise(
            len(value) == 0 or len(value) == self.a_scans_b_scan,
            AssertionError(
                f"Number of x-positions '{len(value)}' does not match the "
                f"number of samples '{self.a_scans_b_scan}'!"
            ),
        )
        self._a_scans["x_positions"] = value

    @property
    def y_positions(self) -> list[int]:
        """Y-Position list."""
        return self._a_scans["y_positions"]

    @y_positions.setter
    def y_positions(self, value: list[int]) -> None:
        """Set y-position list.

        Length of the list must match the number of samples! Empty lists are always ok.

        :param value: List of y-positions [len(value) == no_of_a_scans]
        :raises AssertionError: Out of range
        """
        # Set no of a-scans if not done yet
        if self.a_scans_b_scan == 0:
            self.a_scans_b_scan = len(value)

        expect_or_raise(
            len(value) == 0 or len(value) == self.a_scans_b_scan,
            AssertionError(
                f"Number of y-positions '{len(value)}' does not match the "
                f"number of samples '{self.a_scans_b_scan}'!"
            ),
        )
        self._a_scans["y_positions"] = value

    @property
    def focus_positions(self) -> list[int]:
        """Focus Position list."""
        return self._a_scans["focus_positions"]

    @focus_positions.setter
    def focus_positions(self, value: list[int]) -> None:
        """Set focus position list.

        Length of the list must match the number of samples! Empty lists are always ok.

        :param value: List of focus positions [len(value) == no_of_a_scans]
        :raises AssertionError: Out of range
        """
        # Set no of a-scans if not done yet
        if self.a_scans_b_scan == 0:
            self.a_scans_b_scan = len(value)

        expect_or_raise(
            len(value) == 0 or len(value) == self.a_scans_b_scan,
            AssertionError(
                f"Number of focus_positions '{len(value)}' does not match the "
                f"number of samples '{self.a_scans_b_scan}'!"
            ),
        )
        self._a_scans["focus_positions"] = value