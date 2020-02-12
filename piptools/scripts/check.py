# coding: utf-8
from __future__ import absolute_import, print_function, unicode_literals

import os
import sys
import tempfile

from .. import click
from .._compat import parse_requirements
from ..logging import log
from ..utils import (
    is_pinned_requirement,
    is_url_requirement,
    format_requirement,
    get_compile_command,
    key_from_req,
    key_from_ireq,
)

DEFAULT_REQUIREMENTS_SOURCE_FILE = "requirements.in"
DEFAULT_REQUIREMENTS_FILE = "requirements.txt"


def format_comes_from(ireq):
    """
    Formatter for pretty printing the comes from part of
    InstallRequirements to the terminal.
    """
    comes_from = ireq.comes_from
    if comes_from.startswith("-r "):
        comes_from = comes_from[3:]
    return comes_from


def format_constraint(ireq):
    """
    Formatter for pretty printing InstallRequirements to the terminal
    with the comes from part.
    """
    requirement = format_requirement(ireq)
    comes_from = ireq.comes_from
    # strip out the pip flags
    if comes_from.startswith(("-r ", "-c ")):
        comes_from = comes_from[3:]
    return "{} from {}".format(requirement, comes_from)


class ErrorCounter:
    def __init__(self, *, logger, quiet=False):
        self.errors = 0
        self.warnings = 0

        self.logger = logger
        self.verbose = (not quiet)

    def __bool__(self):
        return bool(self.errors or self.warnings)

    def error(self, msg):
        if self.verbose:
            self.logger.error(msg)
        self.errors += 1

    def warning(self, msg):
        if self.verbose:
            self.logger.warning(msg)
        self.warnings += 1


@click.command()
@click.version_option()
@click.pass_context
@click.option("-v", "--verbose", count=True, help="Show more output")
@click.option("-q", "--quiet", count=True, help="Give less output")
@click.option(
    "-s",
    "--source-file",
    multiple=True,
    nargs=1,
    default=None,
    type=click.Path(exists=True),
    help=(
        "Source spec file name(s) as used to compile requirements file. "
        "Required if more than one source file was used. "
        "Will be derived from requirements file otherwise."
    ),
)
@click.argument("req_file", required=False, type=click.Path(exists=True, allow_dash=True))
def cli(
    ctx,
    verbose,
    quiet,
    source_file,
    req_file,
):
    """Checks whether requirements.txt aligns with requirements.in."""
    log.verbosity = verbose - quiet

    if not req_file:
        if len(source_file) > 1:
            raise click.BadParameter("REQ_FILE is required if two or more source files are given")
        elif os.path.exists(DEFAULT_REQUIREMENTS_FILE):
            req_file = DEFAULT_REQUIREMENTS_FILE
        else:
            raise click.BadParameter(
                (
                    "No requirement file given and no {} found in the current directory"
                ).format(DEFAULT_REQUIREMENTS_FILE)
            )

    if req_file.endswith(".in"):
        raise click.BadParameter(
            "req_file has the .in extensions, which is most likely an error "
            "and will most likely fail the checks. You probably meant to use "
            "the corresponding *.txt file?"
        )

    if len(source_file) == 0:
        if req_file == "-":
            if os.path.exists(DEFAULT_REQUIREMENTS_SOURCE_FILE):
                source_files = (DEFAULT_REQUIREMENTS_SOURCE_FILE,)
            elif os.path.exists("setup.py"):
                source_files = ("setup.py",)
            else:
                raise click.BadParameter(
                    (
                        "If input is from stdin, "
                        "the default is {} or setup.py"
                    ).format(DEFAULT_REQUIREMENTS_SOURCE_FILE)
                )
        # Otherwise try deriving the source file from the requirements file
        else:
            base_name = req_file.rsplit(".", 1)[0]
            file_name = base_name + ".in"
            if os.path.exists(file_name):
                source_file = (file_name,)
            elif os.path.exists("setup.py"):
                source_file = ("setup.py",)
            else:
                raise click.BadParameter(
                    (
                        "If you do not specify a source file, "
                        "the default is {} or setup.py"
                    ).format(file_name)
                )

    ###
    # Start checking the requirements file
    ###

    failures = ErrorCounter(logger=log, quiet=quiet)

    ###
    # Parsing/collecting requirements to check
    ###
    if req_file == "-":
        # pip requires filenames and not files. Since we want to support
        # piping from stdin, we need to briefly save the input from stdin
        # to a temporary file and have pip read that.
        tmpfile = tempfile.NamedTemporaryFile(mode="wt", delete=False)
        tmpfile.write(sys.stdin.read())
        tmpfile.flush()

        ireqs = parse_requirements(
            tmpfile.name,
            session=True,
        )
    else:
        ireqs = parse_requirements(
            req_file,
            session=True,
        )

    existing_pins = {}
    for ireq in ireqs:
        if ireq.editable:
            if ireq.name:
                failures.warning("{} is editable".format(format_requirement(ireq)))
        elif ireq.req is None:
            continue
        key = key_from_ireq(ireq)
        if not is_pinned_requirement(ireq) and not is_url_requirement(ireq):
            failures.warning("{} is unpinned".format(format_requirement(ireq)))
        if key in existing_pins:
            failures.error("{} is a duplicate of {}".format(format_requirement(ireq), format_requirement(existing_pins[key])))
        existing_pins[key] = ireq

    ###
    # Parsing/collecting source requirements
    ###

    constraints = []
    for src_file in source_file:
        is_setup_file = os.path.basename(src_file) == "setup.py"
        if is_setup_file:
            # To read requirements from install_requires in setup.py.
            # we need to briefly save the input from stdin
            # to a temporary file and have pip read that.
            tmpfile = tempfile.NamedTemporaryFile(mode="wt", delete=False)
            from distutils.core import run_setup

            dist = run_setup(src_file)
            tmpfile.write("\n".join(dist.install_requires))
            tmpfile.flush()
            constraints.extend(
                parse_requirements(
                    tmpfile.name,
                    session=True,
                )
            )
        else:
            constraints.extend(
                parse_requirements(
                    src_file,
                    session=True,
                )
            )

    primary_packages = {
        key_from_ireq(ireq) for ireq in constraints if not ireq.constraint
    }

    # Filter out pip environment markers which do not match (PEP496)
    constraints = [
        req for req in constraints if req.markers is None or req.markers.evaluate()
    ]

    for ireq in constraints:
        key = key_from_ireq(ireq)
        if not ireq.constraint and key not in existing_pins:
            failures.error("missing requirement {}".format(format_constraint(ireq)))
            continue
        pin = existing_pins[key]
        if ireq.req and ireq.req.specifier:
            _, version = next(iter(pin.specifier._specs))._spec
            if not ireq.specifier.contains(version):
                failures.error("incompatible requirements found, {} violates constraint {}".format(format_requirement(pin), format_constraint(ireq)))

    msg = "pip-check found {} errors and {} warnings in {}".format(failures.errors, failures.warnings, req_file)
    if failures:
        log.info(msg)
        compile_command = os.environ.get("CUSTOM_COMPILE_COMMAND", "pip-compile")
        log.info("Use {} to fix these".format(compile_command))
        if failures.errors:
            sys.exit(1)
    else:
        log.debug(msg)
