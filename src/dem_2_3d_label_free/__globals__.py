"""Global variables for the project."""

import os

from zeiss_helpers.common import ConfigurationFile

__root__ = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
__configpath__ = os.path.join(__root__, "config")
__datapath__ = os.path.join(__root__, "data")
__template_path__ = os.path.join(__root__, "templates")

__config__ = (
    ConfigurationFile(path=os.path.join(__configpath__, "config.yml"))
    .with_defaults_from_file(os.path.join(__template_path__, "config.template.yml"))
    .with_copy_defaults_if_missing()
    .parse()
)
