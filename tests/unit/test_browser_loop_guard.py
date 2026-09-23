"""The root conftest refuses browser tests that would hang.

The shared ``browser`` fixtures run on pytest-asyncio's module event loop,
and a test that awaits one from any other loop waits forever instead of
failing. tests/conftest.py turns that into a usage error at collection.
These tests collect a throwaway suite under the real root conftest, with a
stand-in ``browser`` that launches nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ("pytester",)

# The inner runs share this suite's settings, and with them pytest-asyncio's
# warning about the unset fixture loop scope, which is not what is under test.
pytestmark = pytest.mark.filterwarnings(
    'ignore:The configuration option "asyncio_default_fixture_loop_scope" is unset'
)

_ROOT_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"

_BROWSER = """
import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def browser():
    yield object()


@pytest_asyncio.fixture(loop_scope="module")
async def page(browser):
    yield browser
"""


@pytest.fixture
def suite(pytester: pytest.Pytester) -> pytest.Pytester:
    pytester.makeini("[pytest]\nasyncio_mode = auto\n")
    pytester.makeconftest(_ROOT_CONFTEST.read_text(encoding="utf-8"))
    return pytester


def test_browser_tests_on_the_module_loop_collect(suite: pytest.Pytester) -> None:
    suite.makepyfile(
        test_module_mark=_BROWSER
        + """
pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_takes_browser(browser):
    pass


async def test_takes_page(page):
    pass
""",
        test_per_test_marks=_BROWSER
        + """
@pytest.mark.asyncio(loop_scope="module")
async def test_marked_itself(page):
    pass


@pytest.mark.asyncio
async def test_bare_mark_without_the_browser():
    pass


def test_synchronous(browser):
    pass
""",
    )

    result = suite.runpytest("--collect-only", "-q", "-p", "no:cacheprovider")

    assert result.ret == pytest.ExitCode.OK
    result.stdout.fnmatch_lines(["5 tests collected*"])


def test_a_browser_test_off_the_module_loop_is_refused(suite: pytest.Pytester) -> None:
    suite.makepyfile(
        test_stray=_BROWSER
        + """
pytestmark = pytest.mark.asyncio(loop_scope="module")


async def test_on_the_module_loop(page):
    pass


@pytest.mark.asyncio
async def test_bare_mark(page):
    pass


@pytest.mark.asyncio(loop_scope="function")
async def test_function_loop(browser):
    pass
""",
        test_unmarked=_BROWSER
        + """
async def test_on_the_default_loop(browser):
    pass
""",
    )

    # Deselecting the strays does not let them through: CI's "not browser"
    # job would otherwise never see one.
    result = suite.runpytest("-q", "-p", "no:cacheprovider", "-k", "module_loop")

    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(
        [
            "ERROR: These tests use the shared browser but would not run on its event loop*",
            "  test_stray.py::test_bare_mark",
            "  test_stray.py::test_function_loop",
            "  test_unmarked.py::test_on_the_default_loop",
        ]
    )
    assert "test_on_the_module_loop" not in result.stderr.str()
