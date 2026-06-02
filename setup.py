# SPDX-License-Identifier: LGPL-2.1-or-later

# Copyright (C) 2020, 2021 igo95862
# Copyright (C) 2025, Alan Dragomirecký

# This file is part of aiodbus, a fork of python-sdbus.

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
from __future__ import annotations

from os import environ
from subprocess import DEVNULL, PIPE
from subprocess import run as subprocess_run
from typing import List, Optional, Tuple

from setuptools import Extension, setup

c_macros: List[Tuple[str, Optional[str]]] = []
compile_arguments: List[str] = ["-flto"]


def _pkg_config(pkg: str, *args: str) -> str:
    process = subprocess_run(
        args=("pkg-config", *args, pkg),
        stderr=DEVNULL,
        stdout=PIPE,
        check=True,
        text=True,
    )
    return process.stdout.strip()


def _pkg_config_exists(pkg: str) -> bool:
    return (
        subprocess_run(
            args=("pkg-config", "--exists", pkg),
            stderr=DEVNULL,
            stdout=DEVNULL,
        ).returncode
        == 0
    )


link_arguments: List[str] = []


def _configure_basu_from_wheel() -> None:
    """Build against the ``basu`` wheel: ``import basu`` for paths, no pkg-config.

    basu (a standalone sd-bus) ships its headers and ``libbasu`` inside the
    installed Python package, so projects can build sd-bus extensions on macOS
    without a system install. basu predates several newer sd-bus APIs, so the
    corresponding fallback macros are always defined.
    """
    import basu

    c_macros.append(("PYTHON_SDBUS_USE_BASU", None))
    c_macros.append(("LIBSYSTEMD_NO_MESSAGE_DUMP", None))
    c_macros.append(("LIBSYSTEMD_NO_VALIDATION_FUNCS", None))
    c_macros.append(("LIBSYSTEMD_NO_OPEN_USER_MACHINE", None))

    libdir = basu.get_library_dir()
    compile_arguments.append("-I" + basu.get_include())
    link_arguments.extend(["-L" + libdir, "-lbasu"])
    # Two rpaths so libbasu (install_name @rpath/libbasu.dylib) resolves either way:
    #  - non-editable install: _sdbus*.so sits in <site-packages> next to the
    #    basu package, so this relative path is stable across environments;
    #  - editable install: _sdbus*.so stays in the source tree, so fall back to
    #    the absolute path of the basu package this was built against.
    link_arguments.append("-Wl,-rpath,@loader_path/basu/lib")
    link_arguments.append("-Wl,-rpath," + libdir)


def _configure_from_pkgconfig() -> None:
    """Fallback: locate sd-bus via pkg-config (libsystemd on Linux, else basu)."""
    if _pkg_config_exists("libsystemd"):
        pkg = "libsystemd"
    elif _pkg_config_exists("basu"):
        pkg = "basu"
    else:
        raise RuntimeError(
            "No sd-bus implementation found. Install the 'basu' wheel "
            "(macOS) or libsystemd/basu discoverable via pkg-config."
        )

    if pkg == "basu":
        c_macros.append(("PYTHON_SDBUS_USE_BASU", None))
        c_macros.append(("LIBSYSTEMD_NO_MESSAGE_DUMP", None))
        cflags = _pkg_config(pkg, "--cflags")
        if cflags:
            compile_arguments.extend(cflags.split())

    if not environ.get("PYTHON_SDBUS_USE_IGNORE_SYSTEMD_VERSION"):
        version = int(_pkg_config(pkg, "--modversion").split(".")[0])
        if version < 246:
            c_macros.append(("LIBSYSTEMD_NO_VALIDATION_FUNCS", None))
        if version < 248:
            c_macros.append(("LIBSYSTEMD_NO_OPEN_USER_MACHINE", None))

    link_arguments.extend(_pkg_config(pkg, "--libs").split())


try:
    # AttributeError guards against an importable-but-stale basu wheel that
    # predates the get_include()/get_library_dir() locator API.
    _configure_basu_from_wheel()
except (ImportError, AttributeError):
    _configure_from_pkgconfig()

link_arguments.append("-flto")

use_limited_api = False

if environ.get("PYTHON_SDBUS_USE_LIMITED_API"):
    c_macros.append(("Py_LIMITED_API", "0x03070000"))
    use_limited_api = True


if __name__ == "__main__":
    with open("./README.md") as f:
        long_description = f.read()

    setup(
        ext_modules=[
            Extension(
                "_sdbus",
                [
                    "src/_sdbus/_sdbus.c",
                    "src/_sdbus/_sdbus_bus.c",
                    "src/_sdbus/_sdbus_funcs.c",
                    "src/_sdbus/_sdbus_interface.c",
                    "src/_sdbus/_sdbus_message.c",
                ],
                extra_compile_args=compile_arguments,
                extra_link_args=link_arguments,
                define_macros=c_macros,
                py_limited_api=use_limited_api,
            )
        ],
    )
