# CLAUDE.md

## Project Overview

Bottle is a lightweight WSGI micro web-framework for Python. The entire framework is distributed as a **single file** (`bottle.py`, ~3,700 lines) with zero dependencies beyond the Python standard library. Version: 0.13-dev. License: MIT.

Homepage: http://bottlepy.org/

## Repository Structure

```
bottle.py              # The entire framework (single-file distribution)
setup.py               # Package setup (setuptools/distutils)
setup.cfg              # Wheel config (universal py2/py3)
Makefile               # Build, test, release automation
tox.ini                # Multi-version test configuration
.travis.yml            # CI configuration
.coveragerc            # Coverage settings (report targets bottle.py only)
test/
  testall.py           # Test runner entry point
  tools.py             # Test utilities (ServerTestBase, helpers)
  test_*.py            # 20+ test modules (unittest-based)
  views/               # Template files for template engine tests (.tpl)
docs/                  # Sphinx documentation source
  conf.py              # Sphinx config
  *.rst                # Documentation pages
```

## Key Architecture

`bottle.py` contains everything in a single file, organized into these sections:

- **Utilities**: `tob()`, `touni()`, `tonat()` for Python 2/3 string handling; `cached_property`, `DictProperty` descriptors
- **Exceptions**: `BottleException`, `HTTPError`, `HTTPResponse`, `RouteError`
- **Router**: `Router` class for URL pattern matching; `Route` class for route definitions
- **Bottle app**: `Bottle` class — the main WSGI application with routing, plugins, hooks, and mounting
- **Request/Response**: `BaseRequest`, `BaseResponse`, `LocalRequest`, `LocalResponse` (thread-local wrappers)
- **Data structures**: `MultiDict`, `FormsDict`, `HeaderDict`, `ConfigDict`, `AppStack`
- **Templates**: `SimpleTemplate` (STPL — built-in engine), plus adapters for Mako, Jinja2, Cheetah
- **Plugins**: `JSONPlugin`, `TemplatePlugin` built-in; plugin API for extensions
- **Server adapters**: WSGIRef, Paste, CherryPy, Twisted, Tornado, Gevent, Eventlet, Waitress, etc.
- **Globals**: `request`, `response` (thread-locals), `default_app()`, `route()`, `run()`, `template()`, `static_file()`

## Running Tests

Tests use Python `unittest`. No external test runner required.

```bash
# Run all tests
python test/testall.py

# Skip server adapter tests (faster)
python test/testall.py fast

# Verbose output
python test/testall.py verbose

# Via Makefile
make test              # Default Python
make test_27           # Specific version (test_25, test_26, test_27, test_31, test_32, test_33, test_34)
make test_all          # All Python versions
```

## Code Coverage

```bash
make coverage
```

Coverage config in `.coveragerc`: data stored in `build/.coverage`, HTML report in `build/coverage/`, only `bottle.py` is measured.

## Building and Installing

```bash
python setup.py install          # Install locally
python setup.py sdist bdist_wheel  # Build distributions
```

No external dependencies are required at runtime.

## Documentation

```bash
# Build HTML docs
make docs
# Or directly:
sphinx-build -b html -d build/docs/doctrees docs build/docs/html
```

Requires `sphinx` to be installed.

## Coding Conventions

- **Single-file architecture**: All framework code lives in `bottle.py`. Do not split it into multiple modules.
- **Python 2/3 compatibility**: The codebase supports Python 2.5+ and Python 3.x. Use the compatibility helpers (`tob`, `touni`, `tonat`, `py3k` flag) rather than version-specific syntax. Conditional imports are common.
- **No type hints**: Not used, to maintain older Python compatibility.
- **Section separators**: Major code sections are delimited by `###############################################################################` comment blocks.
- **Docstrings**: Present on classes and public functions. Follow existing style.
- **Import style**: Standard library imports grouped on one line with backslash continuation at the top of `bottle.py`. Conditional/fallback imports for optional dependencies (simplejson, json, django.utils.simplejson).
- **Thread-local globals**: `request` and `response` are thread-local objects providing per-request context. Use `bottle.app.push()`/`pop()` in tests.

## Testing Conventions

- All tests are `unittest.TestCase` subclasses.
- Test files are named `test_*.py` in the `test/` directory.
- `ServerTestBase` (in `test/tools.py`) provides a WSGI test harness with `urlopen()`, `assertStatus()`, `assertBody()`, `assertHeader()`, and `assertInBody()` helpers. It wraps the app with `wsgiref.validate.validator`.
- `setUp()` pushes a new `Bottle` app; `tearDown()` pops it.
- The `api()` decorator in `test/tools.py` filters tests based on version (introduced/deprecated/removed).
- Template test fixtures live in `test/views/`.

## Plugin Architecture

Plugins wrap route callbacks using a decorator pattern:

```python
class MyPlugin(object):
    name = 'myplugin'
    api = 2                            # Plugin API version (2 = Route object context)

    def setup(self, app): pass         # Called on install
    def apply(self, callback, route):  # Wrap route callbacks
        def wrapper(*args, **kwargs):
            return callback(*args, **kwargs)
        return wrapper
    def close(self): pass              # Called on uninstall
```

Install with `app.install(plugin)`. Built-in plugins: `JSONPlugin`, `TemplatePlugin`.

## Multi-Version Testing

- **Tox** (`tox.ini`): Tests across py25, py26, py27, py32, py33 with Mako/Jinja2 deps. `py27-most` adds eventlet, cherrypy, paste, twisted, tornado.
- **Travis CI** (`.travis.yml`): Python 2.6, 2.7, 3.2, 3.3, 3.4. Uses `test/testall.py fast` (skips server tests).

## Common Development Tasks

| Task | Command |
|------|---------|
| Run tests | `python test/testall.py` |
| Run fast tests | `python test/testall.py fast` |
| Run coverage | `make coverage` |
| Build docs | `make docs` |
| Clean build artifacts | `make clean` |
| Install locally | `make install` |

## Important Notes for AI Assistants

- **Single-file constraint**: `bottle.py` is the entire framework. All changes to framework code go in this one file. This is intentional — it enables zero-dependency deployment by copying a single file.
- **No external dependencies**: The framework must work with only the Python standard library. Optional dependencies (template engines, server adapters) must be gracefully handled with try/except imports.
- **Backward compatibility**: Changes must consider Python 2.5+ and 3.x. Test across versions when possible.
- **WSGI compliance**: Bottle is a WSGI framework. All request/response handling must conform to PEP 3333.
- **Test before committing**: Run `python test/testall.py` to verify changes don't break existing functionality.
- **Focused patches**: One feature or bug fix per change. Keep changes minimal and targeted.
