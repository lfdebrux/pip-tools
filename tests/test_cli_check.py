import sys

import pytest

from .utils import invoke

from piptools.scripts.check import cli


def test_run_as_module_check():
    """piptools can be run as ``python -m piptools ...``."""

    status, output = invoke([sys.executable, "-m", "piptools", "check", "--help"])

    # Should have run pip-check successfully.
    output = output.decode("utf-8")
    assert output.startswith("Usage:")
    assert "Checks whether requirements" in output
    assert status == 0


def test_quiet_option(runner):
    """check command can be run with `--quiet` or `-q` flag."""

    with open("requirements.in", "w") as req_in:
        req_in.write("six")

    with open("requirements.txt", "w") as req:
        req.write("six==1.10.0")

    out = runner.invoke(cli, ["-q"])
    assert not out.stderr_bytes
    assert out.exit_code == 0


def test_quiet_option_when_errors(runner):
    """
    Check should output nothing when there are errors and quiet option is set.
    """

    with open("requirements.in", "w") as req_in:
        req_in.write("six==1.10.0")

    with open("requirements.txt", "w") as req:
        req.write("six=1.9.0")

    out = runner.invoke(cli, ["-q"])
    assert not out.stderr_bytes
    assert out.exit_code == 1


def test_no_requirements_file(runner):
    """
    It should raise an error if there are no input files
    or a requirements.txt file does not exist.
    """
    out = runner.invoke(cli)

    assert "No requirement file given" in out.stderr
    assert out.exit_code == 2


def test_requirements_file_with_dot_in_extension(runner):
    """
    It should raise an error if some of the input files have .in extension.
    """
    with open("requirements.in", "w") as req_in:
        req_in.write("six==1.10.0")

    out = runner.invoke(cli, ["requirements.in"])

    assert "req_file has the .in extension" in out.stderr
    assert out.exit_code == 2


def test_stdin_without_source_file(runner):
    """
    The --source-file option is required for STDIN if requirements.in is not present.
    """
    out = runner.invoke(cli, ["-"])

    assert out.exit_code == 2
    assert "If input is from stdin, the default is requirements.in" in out.stderr


def test_stdin_with_default_source_file(runner):
    """
    It can check requirements from STDIN if requirements.in is present.
    """
    with open("requirements.in", "w") as req_in:
        req_in.write("six")

    out = runner.invoke(cli, ["-"], input="six==1.10.0")

    assert out.exit_code == 0


def test_stdin_with_source_file(runner):
    """
    It can check requirements from STDIN with a specified source file.
    """
    with open("reqs.in", "w") as req_in:
        req_in.write("six")

    out = runner.invoke(cli, ["-", "--source-file", "reqs.in"], input="six==1.10.0")

    assert out.exit_code == 0


def test_multiple_source_files_without_requirements_file(runner):
    """
    The req_file parameter is required for multiple requiement source files.
    """

    with open("src_file1.in", "w") as req_in:
        req_in.write("six==1.10.0")

    with open("src_file2.in", "w") as req_in:
        req_in.write("django==2.1")

    with open("src_file1.txt", "w") as req:
        req.write("six==1.10.0")

    out = runner.invoke(
        cli, ["--source-file", "src_file1.in", "--source-file", "src_file2.in"]
    )

    assert "REQ_FILE is required if two or more source files are given" in out.stderr
    assert out.exit_code == 2


def test_multiple_source_files(runner):
    """
    It can check a requirements file compiled from multiple input files.
    """

    with open("src_file1.in", "w") as req_in:
        req_in.write("six==1.10.0")

    with open("src_file2.in", "w") as req_in:
        req_in.write("django==2.1")

    with open("requirements.txt", "w") as req:
        req.write("django==2.1\n")
        req.write("six==1.10.0")

    out = runner.invoke(
        cli,
        [
            "--source-file",
            "src_file1.in",
            "--source-file",
            "src_file2.in",
            "requirements.txt",
        ],
    )

    assert out.exit_code == 0


@pytest.mark.skip
def test_package_not_found_error(runner):
    """
    It fails if a requirement is a path that is not a project.
    """
    with open("requirements.in", "w"):
        pass

    with open("requirements.txt", "w") as req:
        req.write("/path/to/not/project")

    out = runner.invoke(cli)

    assert out.exit_code == 1
    assert "pip could not find local project /path/to/not/project" in out.stderr
    assert "0 errors and 1 warnings" in out.stderr


def test_unpinned_warning(runner):
    """
    It warns if a requirement is unpinned.
    """
    with open("requirements.in", "w"):
        pass

    with open("requirements.txt", "w") as req:
        req.write("six")

    out = runner.invoke(cli)

    assert out.exit_code == 0
    assert "six is unpinned" in out.stderr
    assert "0 errors and 1 warnings" in out.stderr


def test_duplicate_error(runner):
    """
    It fails if a requirement is duplicated.
    """
    with open("requirements.in", "w"):
        pass

    with open("requirements.txt", "w") as req:
        req.write("six==1.9.0\n")
        req.write("six==1.10.0")

    out = runner.invoke(cli)

    assert out.exit_code == 1
    assert "six==1.10.0 is a duplicate of six==1.9.0" in out.stderr
    assert "1 errors and 0 warnings" in out.stderr


def test_missing_error(runner):
    """
    It fails if a requirement is in the input file but not in the file being checked.
    """
    with open("requirements.in", "w") as req_in:
        req_in.write("django\n")
        req_in.write("six\n")

    with open("requirements.txt", "w") as req:
        req.write("six==1.10.0")

    out = runner.invoke(cli)

    assert out.exit_code == 1
    assert "missing requirement django" in out.stderr
    assert "1 errors and 0 warnings" in out.stderr


def test_incompatible_error(runner):
    """
    It fails if a requirement is not compatible with the input requirements.
    """
    with open("requirements.in", "w") as req_in:
        req_in.write("six==1.10.0")

    with open("requirements.txt", "w") as req:
        req.write("six==1.9.0")

    out = runner.invoke(cli)

    assert out.exit_code == 1
    assert "six==1.9.0 violates constraint six==1.10.0" in out.stderr
    assert "1 errors and 0 warnings" in out.stderr


def test_incompatible_error_with_constraints(runner):
    """
    It fails if a requirement is not compatible
    with the input requirements and constraints.
    """
    with open("constraints.txt", "w") as constraints:
        constraints.write("six>=1.10.0")

    with open("requirements.in", "w") as req_in:
        req_in.write("-c constraints.txt\n")
        req_in.write("six")

    with open("requirements.txt", "w") as req:
        req.write("six==1.9.0")

    out = runner.invoke(cli)

    assert out.exit_code == 1
    assert "six==1.9.0 violates constraint six>=1.10.0" in out.stderr
    assert "1 errors and 0 warnings" in out.stderr


def test_orphaned_warning(runner):
    """
    It warns if a requirement is in the requirements file
    but is not specified as a dependency or sub-dependency
    in the input files.
    """

    with open("requirements.in", "w") as req_in:
        req_in.write("six")

    with open("requirements.txt", "w") as req:
        req.write("gnureadline==6.6.3\n")  # gnureadline is not required by six
        req.write("six==1.9.0")

    out = runner.invoke(cli)

    assert out.exit_code == 0
    assert "0 errors and 1 warnings" in out.stderr
    assert (
        "gnureadline==6.6.3 is present but not required by any input requirements"
        in out.stderr
    )
