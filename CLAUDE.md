# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

aiodbus is an async D-Bus library for Python, forked from python-sdbus. It provides a high-level interface for defining D-Bus services and clients using Python decorators and type annotations.

## Build & Development Commands

```bash
# Install with dev dependencies (using uv)
uv sync

# Build the C extension (required for the _sdbus module)
uv run python setup.py build_ext --inplace

# Run all tests
uv run pytest tests/

# Run a single test
uv run pytest tests/test_sdbus_async.py::TestCase::test_method

# Type checking
uv run pyright

# Formatting
uv run black src/ tests/
uv run isort src/ tests/
```

## Architecture

### Layer Structure

1. **C Extension (`src/_sdbus/`)**: Low-level bindings to libsystemd's sd-bus library. Provides `_sdbus` Python module with bus operations, message handling, and interface building.

2. **Bus Abstraction (`src/aiodbus/bus/`)**:
   - `any.py`: Protocol definition for `Dbus` interface
   - `sdbus.py`: Implementation using the C extension
   - `connection.py`: Connection management, default bus handling

3. **Interface System (`src/aiodbus/interface/`)**:
   - `base.py`: `DbusInterface` base class with metaclass `DbusInterfaceMeta` that collects D-Bus members
   - `common.py`: `DbusInterfaceCommon` with standard D-Bus interfaces (Introspectable, Peer)
   - `properties.py`: Properties interface implementation
   - `object_manager.py`: ObjectManager interface

4. **Member Descriptors (`src/aiodbus/member/`)**: Python descriptors for D-Bus members
   - `method.py`: `@dbus_method` decorator and `DbusMethod` descriptor
   - `property.py`: `@dbus_property` decorator and `DbusProperty` descriptor
   - `signal.py`: `DbusSignal` class for signals

5. **Signature System (`src/aiodbus/signature.py`)**: Type conversion between Python types and D-Bus signatures using `DbusConvertible` protocol. Supports:
   - Automatic signature inference from type annotations
   - Custom conversions via `Annotated[T, WithConversion(...)]`
   - Named parameters via `Annotated[T, WithName("name")]`

### Key Patterns

**Defining a D-Bus Interface:**
```python
class MyInterface(
    DbusInterfaceCommon,
    interface_name="org.example.MyInterface",
):
    @dbus_method()
    async def my_method(self, arg: str) -> int:
        return len(arg)

    @dbus_property()
    def my_prop(self) -> str:
        return self._value

    my_signal = DbusSignal[str]()
```

**Local vs Proxy Objects:**
- Local objects: Created normally, exported via `obj.export_to_dbus(path)`
- Proxy objects: Created via `MyInterface.new_proxy(service_name, path)` to call remote services

**Descriptor Binding:**
Members are descriptors that return different bound types based on context:
- On class access: `DbusClassMember` (for class-level operations like `catch_anywhere`)
- On local instance: `DbusLocalMember` (handles incoming D-Bus calls)
- On proxy instance: `DbusProxyMember` (makes outgoing D-Bus calls)

### Code Generator

The `aiodbus` CLI generates Python interface classes from D-Bus introspection XML:

```bash
# From XML file
aiodbus gen-from-file interface.xml > generated.py

# From running service
aiodbus gen-from-connection org.freedesktop.systemd1 /org/freedesktop/systemd1 --system
```

## Dependencies

- libsystemd (system library, required for C extension)
- Python 3.11+ (uses modern type syntax: `type` aliases, `[T]` generics)

## Creating commits

- Always first format the code, run type checks and tests before creating a commit.
- Write short commit messages.
- Do not mention Claude in the commit messages.
